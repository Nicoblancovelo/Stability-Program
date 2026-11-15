import copy
import html
import json
from datetime import datetime, timezone
from pathlib import Path
import pandas as pd
import streamlit as st
from model import default_condition, normalize, calculate, tank_weight

BASE = Path(__file__).resolve().parent
st.set_page_config(page_title="OAG Responder | Stability", layout="wide")
@st.cache_data
def load_data():
    return (json.loads((BASE/"data/tanks.json").read_text()),
            json.loads((BASE/"labels.json").read_text()),
            pd.read_csv(BASE/"data/hydrostatics.csv").sort_values("disp_lt"),
            pd.read_csv(BASE/"data/allowable_vcg.csv").sort_values("draft_ft"))
tanks, labels, hs, vcg = load_data()
ss = st.session_state
if "current" not in ss:
    ss.current = default_condition(tanks)
    ss.epoch = 0
    ss.history = []
if "pending" in ss:
    ss.current = ss.pop("pending")
    ss.epoch += 1
    ss.pop("cargo_seed", None)
    ss.skip_history = True
c = copy.deepcopy(ss.current)
def key(s):
    return f"{s}_{ss.epoch}"
st.markdown("""<style>
/* Keep colors under Streamlit's theme so light and dark stay consistent. */
[data-testid="stMetric"]{
    border:1px solid rgba(128,128,128,0.35);
    border-radius:10px;
    padding:12px;
}
[data-testid="stMetricValue"]{font-size:1.5rem}
[data-testid="stCaptionContainer"]{color:inherit;opacity:0.85}
</style>""", unsafe_allow_html=True)
brand, title = st.columns([1,9])
brand.image(str(BASE/"assets/oag-logo.jpeg"),width=75)
title.title("OAG Responder | Stability")
title.caption("Loading condition workspace")
st.warning("Development version · Vessel data unverified · Not for operational loading decisions")
a,b = st.columns([3,1])
c["name"] = a.text_input("Condition name",value=c["name"],key=key("name"))
c["operator"] = b.text_input("Prepared by (optional)",value=c["operator"],key=key("operator"))
toolbar, summary = st.container(), st.container()

with st.sidebar:
    st.header("Tank quantities")
    st.caption("Decimal feet: 3 ft 6 in = 3.50 ft. Bars use quantity, not sounding height.")
    for group in ("Fuel","Ballast","Water","Other"):
        with st.expander(group,expanded=group=="Fuel"):
            for n in sorted((n for n in tanks if tanks[n].get("group","Other")==group),key=lambda n:labels[n]):
                td=tanks[n]
                st.markdown(f"**{labels[n]}**")
                c["tank_empty"][n]=st.checkbox("Confirmed empty",value=c["tank_empty"][n],key=key("empty_"+n),
                    help="Check only if the tank is confirmed to contain no liquid.")
                c["tank_soundings"][n]=st.number_input("Sounding (ft)",value=float(c["tank_soundings"][n]),
                    key=key("snd_"+n),disabled=c["tank_empty"][n],step=0.01,format="%.2f")
                try:
                    weight=tank_weight(td,c["tank_soundings"][n],c["tank_empty"][n])
                    cap=max(td["weight_lt"])
                    st.progress(min(1.0,max(0.0,weight/cap)) if cap else 0.0)
                    st.caption(f"{weight:.2f} / {cap:.2f} LT · {weight/cap:.0%} of table capacity" if cap else "No capacity available")
                except ValueError:
                    st.caption("Quantity unavailable — check sounding or empty status.")
                st.caption(f"Table range: {td['sounding_ft'][0]:.2f}–{td['sounding_ft'][-1]:.2f} ft")
    with st.expander("Lightship baseline"):
        for field,label in (("ls_disp","Displacement (LT)"),("ls_lcg","LCG (ft)"),("ls_kg","KG (ft)")):
            c[field]=st.number_input(label,value=float(c[field]),key=key(field))
        st.caption("Lightship TCG is assumed zero. No hidden weight adjustments.")
    with st.expander("Reference settings"):
        c["min_gm"]=st.number_input("Reference GM threshold (ft)",value=float(c["min_gm"]),key=key("min_gm"))
        st.caption("Existing threshold and source data are unverified.")
    with st.expander("Import condition"):
        upload=st.file_uploader("Condition JSON file",type=["json"],key=key("upload"))
        if st.button("Load uploaded file",disabled=upload is None):
            try:
                if upload.size>1_000_000:
                    raise ValueError("Maximum file size is 1 MB.")
                imported=normalize(json.loads(upload.getvalue()),tanks)
                ss.history.append(copy.deepcopy(ss.current))
                ss.pending=imported
                st.rerun()
            except (ValueError,TypeError,KeyError) as e:
                st.error(f"File not loaded: {e}")
        st.caption("Legacy files are accepted. Missing empty flags stay unchecked.")

side,astern=st.columns([1.7,1])
with side:
    with st.container(border=True):
        st.subheader("Trim · Side view")
        st.info("Responder drawing pending photographs")
        st.caption("Reserved for the vessel, waterline and forward/aft draft labels.")
with astern:
    with st.container(border=True):
        st.subheader("List · Viewed from astern")
        st.info("Astern drawing pending photographs")
        st.caption("Port/starboard labels and actual/exaggerated scale will accompany the drawing.")

st.subheader("Cargo / Deck loads")
st.caption("Long tons and feet. Positive TCG is starboard. Longitudinal and vertical reference points must be verified against the vessel book.")
columns=["Name","Weight (LT)","LCG (ft)","VCG (ft)","TCG (ft)"]
if "cargo_seed" not in ss:
    ss.cargo_seed=pd.DataFrame([[c["cargo_names"][i],*row] for i,row in enumerate(c["cargo"])],columns=columns)
    for col in columns[1:]:
        ss.cargo_seed[col]=ss.cargo_seed[col].astype(float)
edited=st.data_editor(ss.cargo_seed,num_rows="dynamic",hide_index=True,use_container_width=True,key=key("cargo"),
    column_config={"Name":st.column_config.TextColumn("Name (optional)"),
        "Weight (LT)":st.column_config.NumberColumn(min_value=0.0,default=0.0,format="%.2f"),
        **{col:st.column_config.NumberColumn(default=0.0,format="%.2f") for col in columns[2:]}})
c["cargo"],c["cargo_names"]=[],[]
for row in edited.to_dict("records"):
    if all(pd.isna(v) or v=="" for v in row.values()):
        continue
    c["cargo_names"].append("" if pd.isna(row["Name"]) else str(row["Name"]))
    c["cargo"].append([0.0 if pd.isna(row[col]) else float(row[col]) for col in columns[1:]])
st.caption("Use the bottom row to add cargo; select a row to delete it. Maximum 20 items.")

comparison,rolling,drafts=st.columns([1.3,1,1.2])
with rolling:
    with st.container(border=True):
        st.subheader("Estimated rolling period")
        st.metric("Natural period","—")
        st.caption("Pending verified dimensions and estimation method. No invented estimate or animation.")
with drafts:
    with st.container(border=True):
        st.subheader("Draft readings")
        record=st.checkbox("Enter observed drafts",value=c["observed_fwd"] is not None,key=key("record"))
        for field,label in (("observed_fwd","Observed forward (ft)"),("observed_aft","Observed aft (ft)")):
            c[field]=st.number_input(label,value=float(c[field] or 0),min_value=0.0,key=key(field)) if record else None
        draft_output=st.empty()
        st.caption("Compare a common datum and corrected draft-mark positions. Readings never adjust the model.")

input_errors=[]
try:
    c=normalize(c,tanks)
    results,errors,warnings=calculate(c,tanks,hs,vcg,labels)
except ValueError as e:
    input_errors=[str(e)]
    results,errors,warnings={},input_errors,[]
def display(k,unit=""):
    if k not in results:
        return "—"
    v=results[k]
    if k=="list":
        return "Upright" if abs(v)<.05 else f"{abs(v):.2f}° {'stbd' if v>0 else 'port'}"
    if k=="trim":
        return "Even keel" if abs(v)<.01 else f"{abs(v):.2f} ft {'stern' if v>0 else 'bow'}"
    return f"{v:,.2f}{unit}"
with summary:
    items=[("Displacement","displacement"," LT"),("Forward draft","fwd"," ft"),("Aft draft","aft"," ft"),
           ("List","list",""),("Trim","trim",""),("Corrected GM","gm"," ft")]
    for col,(label,k,unit) in zip(st.columns(6),items):
        col.metric(label,display(k,unit))
    st.caption("Preliminary estimates from existing tables. Compliance not assessed.")
if not input_errors:
    if c!=ss.current and not ss.get("skip_history",False):
        ss.history.append(copy.deepcopy(ss.current))
    ss.current=copy.deepcopy(c)
ss.history=ss.history[-20:]
ss.skip_history=False

def table(rows,headings):
    return pd.DataFrame(rows,columns=headings).to_html(index=False,escape=True)
report='<!doctype html><html><head><meta charset="utf-8"><title>Responder condition report</title><style>body{font:15px sans-serif;max-width:1000px;margin:35px auto}table{border-collapse:collapse;width:100%;margin:15px 0}td,th{border:1px solid #ccc;padding:8px;text-align:left}@media print{button{display:none}}</style></head><body>'
report+='<button onclick="window.print()">Print / Save as PDF</button><h1>OAG Responder — Condition report</h1>'
report+='<p>Development version — unverified vessel data. Not for operational loading decisions.</p>'
report+=f'<h2>{html.escape(c["name"])}</h2><p>Prepared by: {html.escape(c["operator"])}</p><p>Exported: {datetime.now(timezone.utc).isoformat()} (UTC)</p>'
report+=table([[label,display(k,unit)] for label,k,unit in items],["Result","Value"])
report+=table([["Displacement (LT)",c["ls_disp"]],["LCG (ft)",c["ls_lcg"]],["KG (ft)",c["ls_kg"]],["TCG (ft)","0.00 assumed"]],["Lightship baseline","Value"])
report+='<h2>Tank soundings</h2>'+table([[labels[n],c["tank_soundings"][n],c["tank_empty"][n]] for n in tanks],["Tank","Sounding (ft)","Confirmed empty"])
report+='<h2>Cargo</h2>'+table([[c["cargo_names"][i],*row] for i,row in enumerate(c["cargo"])],columns)
report+='<p>Vessel data revision pending. Fixed free-surface allowances retained, including empty tanks. Existing no-trim VCG curve remains unverified.</p>'
report+=''.join(f'<p>{html.escape(e)}</p>' for e in errors+warnings)+'</body></html>'
with toolbar:
    a,b,d,e,f=st.columns(5)
    if a.button("Duplicate condition",disabled=bool(input_errors),use_container_width=True):
        ss.history.append(copy.deepcopy(c))
        ss.pending=copy.deepcopy(c)
        ss.pending["name"]=(c["name"] or "Condition")+" — copy"
        st.rerun()
    if b.button("Undo",disabled=not ss.history,use_container_width=True):
        ss.pending=ss.history.pop()
        st.rerun()
    d.download_button("Export condition",json.dumps(c,indent=2,allow_nan=False) if not input_errors else "{}",
        "responder-condition.json","application/json",disabled=bool(input_errors),use_container_width=True)
    e.download_button("Download report",report,"responder-report.html","text/html",
        disabled=bool(input_errors),use_container_width=True)
    if f.button("Set comparison",disabled=bool(errors),use_container_width=True):
        ss.comparison=dict(condition=copy.deepcopy(c),results=copy.deepcopy(results))
    st.caption("Import from the sidebar. Export saves to your device. Open a downloaded report to print. Undo and comparison last for this browser session.")
with comparison:
    with st.container(border=True):
        st.subheader("Condition comparison")
        if "comparison" not in ss:
            st.caption("Set a comparison reference, then edit a proposed condition.")
        else:
            reference=ss.comparison
            st.caption("Reference: "+reference["condition"]["name"])
            rows=[]
            for label,k in (("Displacement (LT)","displacement"),("Trim (ft, +stern)","trim"),("List (°, +stbd)","list"),("GM (ft)","gm")):
                old,new=reference["results"].get(k),results.get(k)
                rows.append([label,f"{old:.2f}" if old is not None else "—",f"{new:.2f}" if new is not None else "—",
                             f"{new-old:+.2f}" if old is not None and new is not None else "—"])
            st.dataframe(pd.DataFrame(rows,columns=["Value","Reference","Now","Change"]),hide_index=True,use_container_width=True)
if record:
    with draft_output.container():
        for label,obs,k in (("Forward",c["observed_fwd"],"fwd"),("Aft",c["observed_aft"],"aft")):
            if k in results:
                st.caption(f"{label}: calculated {results[k]:.2f} ft · observed minus calculated {obs-results[k]:+.2f} ft")
if errors:
    st.warning(f"{len(errors)} items need attention. Affected results are unavailable.")
    with st.expander("Show errors"):
        for error in errors:
            st.error(error)
if warnings:
    st.warning("Source-data issues remain. All displayed results are preliminary.")
    with st.expander("Show data warnings"):
        for warning in warnings:
            st.write(warning)
with st.expander("Detailed calculations and assumptions"):
    def detail(label, field, unit="ft"):
        value = results.get(field)
        text = "Unavailable" if value is None else f"{value:,.2f} {unit}"
        st.write(f"{label}: {text}")

    st.subheader("Weight and centers of gravity")
    detail("Total displacement", "displacement", "LT")
    detail("Longitudinal center of gravity (LCG)", "lcg")
    detail("Vertical center of gravity (KG)", "kg")
    st.caption("LCG and KG use the existing model reference points, pending verification.")

    st.subheader("Tank quantities")
    totals = results.get("totals", {})
    for group in ("Fuel", "Ballast", "Water", "Other"):
        value = totals.get(group)
        text = "Unavailable" if value is None else f"{value:,.2f} LT"
        st.write(f"{group}: {text}")

    st.subheader("Draft, trim and list")
    detail("Reference draft from hydrostatic table", "draft")
    detail("Forward draft", "fwd")
    detail("Aft draft", "aft")
    trim = results.get("trim")
    if trim is None:
        st.write("Trim: Unavailable")
    elif abs(trim) < 0.01:
        st.write("Trim: Even keel")
    else:
        direction = "stern" if trim > 0 else "bow"
        st.write(f"Trim: {abs(trim):.2f} ft down by {direction}")
    heel = results.get("list")
    if heel is None:
        st.write("List: Unavailable")
    elif abs(heel) < 0.05:
        st.write("List: Upright")
    else:
        direction = "starboard" if heel > 0 else "port"
        st.write(f"List: {abs(heel):.2f}° to {direction}")

    st.subheader("Stability values")
    detail("Transverse metacentric height above keel (KMt)", "kmt")
    detail("Free-surface correction (FSC)", "fsc")
    detail("Corrected metacentric height (GM)", "gm")
    detail("Allowable KG from existing curve (unverified)", "allow_kg")
    detail("KG margin against existing curve (unverified)", "margin")
    st.write(f"Reference GM threshold: {c['min_gm']:.2f} ft (unverified).")

    st.subheader("Assumptions and limitations")
    st.write("The existing free-surface allowances are applied to every tank, including tanks marked empty.")
    st.write("Each tank uses a fixed center of gravity at every fill level.")
    st.write("The existing no-trim VCG curve is compared with KG before adding the free-surface correction. This method requires review against the stability book.")
    st.write("These results do not establish compliance with the vessel's stability requirements.")
    st.write("The hydrostatic and tank source data have not been revised. Vessel drawings and the rolling-period calculation are pending.")
