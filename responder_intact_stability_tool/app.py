import streamlit as st
import pandas as pd
import numpy as np
import json
from pathlib import Path

LBP_FT = 200.0
MAX_ALLOWABLE_DRAFT = 16.0
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SAVE_FILE = BASE_DIR / "saved_condition.json"


# Display labels only; original tank IDs remain in saved conditions.
TANK_DISPLAY_NAMES = {
    "FO_1_STBD Max 4.75": "No. 1 Fuel Oil — Starboard",
    "FO_1_PORT Max 4.75": "No. 1 Fuel Oil — Port",
    "FO_2_STBD Max 15.75": "No. 2 Fuel Oil — Starboard",
    "FO_2_PORT Max 15.75": "No. 2 Fuel Oil — Port",
    "FO_3_STBD Max 4.75": "No. 3 Fuel Oil — Starboard",
    "FO_3_PORT Max 4.75": "No. 3 Fuel Oil — Port",
    "FO_4_STBD Max 15.75": "No. 4 Fuel Oil — Starboard",
    "FO_4_PORT Max 15.75": "No. 4 Fuel Oil — Port",
    "FO_DAY_STBD Max 15.25": "Fuel Oil Day Tank — Starboard",
    "FO_DAY_PORT Max 15.25": "Fuel Oil Day Tank — Port",
    "FO_BOW_THRUSTER_DAY_STBD Max 15.50": "Bow Thruster Fuel Day Tank — Starboard",
    "FP_BALLAST Max 16.00": "Forepeak Ballast",
    "BALLAST_1_STBD Max 17.00": "No. 1 Ballast — Starboard",
    "BALLAST_1_PORT Max 17.00": "No. 1 Ballast — Port",
    "BALLAST_CENTER_2 Max 6.00": "No. 2 Ballast — Center",
    "BALLAST_3_STBD Max 16.00": "No. 3 Ballast — Starboard",
    "BALLAST_3_PORT Max 16.00": "No. 3 Ballast — Port",
    "BALLAST_4_STBD Max 14.25": "No. 4 Ballast — Starboard",
    "BALLAST_4_PORT Max 14.25": "No. 4 Ballast — Port",
    "BALLAST_AFTPEAK_STBD Max 7.25": "Aft Peak Ballast — Starboard",
    "BALLAST_AFTPEAK_PORT Max 7.25": "Aft Peak Ballast — Port",
    "DIRTY_OIL_STBD Max 5.25": "Dirty Oil — Starboard",
    "SLOP_TANK_PORT Max 5.25": "Slop Tank — Port",
    "LUBE_OIL_PORT Max 9.50": "Lubricating Oil — Port",
    "GEAR_OIL_PORT Max 15.50": "Gear Oil — Port",
    "HYDRAULIC_OIL_STBD Max 15.50": "Hydraulic Oil — Starboard",
    "HYDRAULIC_CENTER Max 4.25": "Hydraulic Oil — Center",
    "POTABLE_WATER_STBD Max 14.50": "Potable Water — Starboard",
    "POTABLE_WATER_PORT Max 14.50": "Potable Water — Port",
    "SEWAGE_PORT Max 10.25": "Sewage — Port"
}


def lin_interp(x, xs, ys):
    return float(np.interp(x, xs, ys))

def fwd_aft_from_trim(mean_draft, trim, lcf_from_fp, lpp=LBP_FT):
    dist_fp = lcf_from_fp
    dist_ap = lpp - lcf_from_fp
    aft = mean_draft + trim * (dist_ap / lpp)
    fwd = mean_draft - trim * (dist_fp / lpp)
    return fwd, aft

@st.cache_data
def load_data():
    hs = pd.read_csv(DATA_DIR / "hydrostatics.csv").sort_values("disp_lt")
    vcg = pd.read_csv(DATA_DIR / "allowable_vcg.csv").sort_values("draft_ft")
    with open(DATA_DIR / "tanks.json") as f:
        tanks = json.load(f)
    return hs, vcg, tanks

hs, vcg_curve, tanks = load_data()

#st.write("Loaded tanks:", list(tanks.keys()))

st.warning(
    "Development version — vessel data pending update. "
    "Not for operational loading decisions."
)
# ---------------- Lightship Corrections ----------------
# Use documented lightship values without additional adjustments.
Lightship_Corrections = []


# ---------------- LOAD CONDITION ----------------
if SAVE_FILE.exists():
    if st.sidebar.button("Load Saved Condition"):
        saved = json.loads(SAVE_FILE.read_text())

        # Lightship
        if "ls_disp" in saved:
            st.session_state["ls_disp"] = saved["ls_disp"]
        if "ls_lcg" in saved:
            st.session_state["ls_lcg"] = saved["ls_lcg"]
        if "ls_kg" in saved:
            st.session_state["ls_kg"] = saved["ls_kg"]

        # Tanks
        if "tank_soundings" in saved:
            for t in tanks:
                key = f"snd_{t}"
                if t in saved["tank_soundings"]:
                    st.session_state[key] = saved["tank_soundings"][t]

           # Restore confirmed-empty settings.
        # Older saved files do not establish that any tank is empty.
        saved_empty = saved.get("tank_empty", {})
        for t in tanks:
            st.session_state[f"empty_{t}"] = (
                saved_empty.get(t, False) is True
            )
        # Cargo
        if "cargo" in saved:
            if len(saved["cargo"]) > 20:
                st.error("Saved condition contains more than 20 cargo items.")
                st.stop()
            st.session_state["num_cargo"] = len(saved["cargo"])
            saved_names = saved.get("cargo_names", [])
            for i in range(20):
                st.session_state[f"cn{i}"] = (
                    saved_names[i]
                    if i < len(saved["cargo"]) and i < len(saved_names)
                    else ""
                )
            for i, (w, l, v, t) in enumerate(saved["cargo"]):
                st.session_state[f"cw{i}"] = w
                st.session_state[f"cl{i}"] = l
                st.session_state[f"cv{i}"] = v
                st.session_state[f"ct{i}"] = t

        st.sidebar.success("Condition loaded")
        st.rerun()



# ---------------- LIGHTSHIP ----------------
st.sidebar.header("Lightship")

ls_disp = st.sidebar.number_input("Lightship Displacement (LT)", value=1166.86, key="ls_disp")
ls_lcg  = st.sidebar.number_input("Lightship LCG (ft)", value=96.55, key="ls_lcg")
ls_kg   = st.sidebar.number_input("Lightship KG (ft)", value=17.07, key="ls_kg")

# ---------------- GM LIMIT ----------------
st.sidebar.header("Stability Limits")
min_gm = st.sidebar.number_input("Minimum GM (ft)", value=0.50)

# ---------------- TANK SOUNDINGS ----------------
st.sidebar.header("Tank Soundings (ft)")
st.sidebar.caption(
    "Check 'Confirmed empty' only when the tank has no liquid contents. "
    "A zero sounding alone does not confirm an empty tank."
)

tank_soundings = {}
tank_empty = {}

for t in tanks:
    tank_empty[t] = st.sidebar.checkbox(
        f"Confirmed empty: {TANK_DISPLAY_NAMES.get(t, t)}",
        value=False,
        key=f"empty_{t}",
    )

    tank_soundings[t] = st.sidebar.number_input(
        TANK_DISPLAY_NAMES.get(t, t),
        value=0.0,
        key=f"snd_{t}",
        disabled=tank_empty[t],
    )
    st.sidebar.caption(
        f"Maximum table sounding: {max(tanks[t]['sounding_ft']):.2f} ft"
    )

# ---------------- CARGO INPUT ----------------
st.sidebar.header("Cargo / Deck Loads")

cargo = []
cargo_names = []
num_cargo = st.sidebar.number_input(
    "Number of cargo items", min_value=0, max_value=20, value=3,
    key="num_cargo",
)

for i in range(num_cargo):
    cargo_names.append(st.sidebar.text_input(
        f"Cargo {i+1} Name (optional)",
        value="",
        placeholder="e.g. Blue container",
        key=f"cn{i}",
    ))
    w = st.sidebar.number_input(f"Cargo {i+1} Weight (LT)", value=0.0, key=f"cw{i}")
    l = st.sidebar.number_input(f"Cargo {i+1} LCG (ft)", value=0.0, key=f"cl{i}")
    v = st.sidebar.number_input(f"Cargo {i+1} VCG (ft)", value=0.0, key=f"cv{i}")
    t = st.sidebar.number_input(f"Cargo {i+1} TCG (ft, +stbd)", value=0.0, key=f"ct{i}")
    cargo.append((w, l, v, t))


# ---------------- SAVE CONDITION ----------------
if st.sidebar.button("Save Current Condition"):
    save_data = {}

    # Lightship
    save_data["ls_disp"] = ls_disp
    save_data["ls_lcg"] = ls_lcg
    save_data["ls_kg"] = ls_kg

    # Tank soundings
    save_data["tank_soundings"] = tank_soundings
    save_data["tank_empty"] = tank_empty

    # Cargo
    save_data["cargo"] = cargo
    save_data["cargo_names"] = cargo_names

    SAVE_FILE.write_text(json.dumps(save_data, indent=2))
    st.sidebar.success("Condition saved")


# ---------------- WEIGHT SUMMATION ----------------
# ---------------- WEIGHT SUMMATION ----------------
if ls_disp <= 0:
    st.error("Entered lightship displacement must be greater than zero.")
    st.stop()

disp = ls_disp
mx = ls_disp * ls_lcg
mz = ls_disp * ls_kg

# The existing model assumes entered lightship TCG is zero.
tm = 0.0
fsm_total = 0.0

adjustment_rows = []

for w, l, v, t in Lightship_Corrections:
    disp += w
    mx += w * l
    mz += w * v
    tm += w * t

    if w != 0:
        adjustment_rows.append({
            "Description": "Unverified Adjustment - Removal of Davit and Addition of A-Frame",
            "Weight (LT)": w,
            "LCG (ft)": l,
            "VCG (ft)": v,
            "TCG (ft, +starboard)": t,
        })

if disp <= 0:
    st.error(
        "Lightship adjustments produce zero or negative displacement. "
        "Check the entered lightship and adjustments."
    )
    st.stop()

# Display lightship before adding tanks or cargo.
st.header("Lightship Breakdown")

st.subheader("Entered Lightship")
st.write(f"Displacement: {ls_disp:.2f} LT")
st.write(f"LCG: {ls_lcg:.2f} ft")
st.write(f"KG: {ls_kg:.2f} ft")
st.caption("Entered lightship TCG is currently assumed to be 0.00 ft.")

st.subheader("Lightship Adjustments")

if adjustment_rows:
    st.table(pd.DataFrame(adjustment_rows))
    st.warning(
        "An unverified legacy adjustment is included in these calculations. "
        "Its purpose must be checked against the lightship records."
    )
else:
    st.write("No lightship adjustments are applied.")

adjustment_total = sum(w for w, l, v, t in Lightship_Corrections)
st.write(f"Total adjustment: {adjustment_total:+.2f} LT")

st.subheader("Adjusted Lightship")
st.write(f"Displacement: {disp:.2f} LT")
st.write(f"LCG: {mx / disp:.2f} ft")
st.write(f"KG: {mz / disp:.2f} ft")
st.write(f"TCG: {tm / disp:+.2f} ft (+starboard)")
st.caption(
    "These totals include lightship adjustments. "
    "Tank contents and cargo have not yet been added."
)

st.divider()

tank_totals = {"Fuel": 0.0, "Ballast": 0.0, "Other": 0.0}

for w, l, v, t in cargo:
    disp += w
    mx += w * l
    mz += w * v
    tm += w * t

# ---- TANK TABLE VALIDATION (TEMP) ----
# ---------------- VALIDATE TANK TABLES AND INPUTS ----------------
tank_errors = []

for name, td in tanks.items():
    xs = np.asarray(td["sounding_ft"], dtype=float)
    ys = np.asarray(td["weight_lt"], dtype=float)

    if len(xs) < 2 or len(xs) != len(ys):
        tank_errors.append(
            f"{TANK_DISPLAY_NAMES.get(name, name)}: sounding and weight tables must have matching "
            "lengths and at least two entries."
        )
        continue

    if not np.all(np.isfinite(xs)) or not np.all(np.isfinite(ys)):
        tank_errors.append(f"{TANK_DISPLAY_NAMES.get(name, name)}: table contains invalid numbers.")
        continue

    if np.any(np.diff(xs) <= 0):
        tank_errors.append(
            f"{TANK_DISPLAY_NAMES.get(name, name)}: sounding values must increase without duplicates."
        )
        continue

    if np.any(ys < 0) or np.any(np.diff(ys) < 0):
        tank_errors.append(
            f"{TANK_DISPLAY_NAMES.get(name, name)}: tank weights must be nonnegative and must not "
            "decrease as sounding increases."
        )
        continue

    if not tank_empty[name]:
        snd = tank_soundings[name]

        if not np.isfinite(snd) or not xs[0] <= snd <= xs[-1]:
            tank_errors.append(
                f"{TANK_DISPLAY_NAMES.get(name, name)}: enter a sounding from "
                f"{xs[0]:.2f} to {xs[-1]:.2f} ft, "
                "or mark the tank confirmed empty if it has no contents."
            )

if tank_errors:
    st.warning(
        f"Calculation paused: {len(tank_errors)} tank entries need attention."
    )
    with st.expander("Show errors", expanded=False):
        for message in tank_errors:
            st.error(message)
    st.stop()

# ---------------- CALCULATE TANK WEIGHTS ----------------
for t, snd in tank_soundings.items():
    td = tanks[t]

    if tank_empty[t]:
        wt = 0.0
    else:
        wt = lin_interp(snd, td["sounding_ft"], td["weight_lt"])

    disp += wt
    mx += wt * td["lcg_ft"]
    mz += wt * td["vcg_ft"]
    tm += wt * td.get("tcg_ft", 0.0)

    # Retain the existing free-surface allowance pending book review.
    fsm_total += td.get("fsm_ftlt", 0.0)

    group = td.get("group", "Other")
    tank_totals[group] = tank_totals.get(group, 0.0) + wt

st.caption(
    "Confirmed-empty tanks contribute zero liquid weight. "
    "The existing fixed free-surface allowances remain applied "
    "pending review against the stability book."
)

lcg = mx / disp
kg = mz / disp
fsc = fsm_total / disp

# ---------------- HYDROSTATICS INTERPOLATION ----------------
draft = lin_interp(disp, hs["disp_lt"], hs["draft_ft"])
kmt   = lin_interp(disp, hs["disp_lt"], hs["kmt_ft"])
lcb   = lin_interp(disp, hs["disp_lt"], hs["lcb_ft"])
lcf   = lin_interp(disp, hs["disp_lt"], hs["lcf_ft"])

mtc_per_in = lin_interp(disp, hs["disp_lt"], hs["mct_ftlt_per_198ft"])  # LT-ft per inch

trim_moment = disp * (lcg - lcb)   # LT-ft
mtc_per_in = lin_interp(disp, hs["disp_lt"], hs["mct_ftlt_per_198ft"])
trim_in = trim_moment / mtc_per_in
trim_ft = trim_in / 12.0

# --- TRIM DISTRIBUTION ABOUT LCF ---
delta_fwd = -trim_ft * (lcf / LBP_FT)
delta_aft =  trim_ft * ((LBP_FT - lcf) / LBP_FT)

fwd_draft = draft + delta_fwd
aft_draft = draft + delta_aft


gm = kmt - kg - fsc



# ---------------- ALLOWABLE VCG CHECK ----------------
if draft > MAX_ALLOWABLE_DRAFT:
    st.warning("Draft exceeds allowable VCG curve range. Using 16 ft limit.")
    draft_for_vcg = MAX_ALLOWABLE_DRAFT
else:
    draft_for_vcg = draft

allow_kg = lin_interp(draft_for_vcg,
                      vcg_curve["draft_ft"],
                      vcg_curve["vcg_no_trim_ft"])

margin = allow_kg - kg

# ---------------- OUTPUT ----------------
st.header("Results")

st.write(f"Displacement: {disp:.2f} LT")
st.write(f"LCG: {lcg:.2f} ft")
st.write(f"KG: {kg:.2f} ft")

st.write(f"Mean Draft: {draft:.2f} ft")
st.write(f"Forward Draft: {fwd_draft:.2f} ft")
st.write(f"Aft Draft: {aft_draft:.2f} ft")
if abs(trim_ft) < 0.01:
    trim_text = "Even keel"
elif trim_ft > 0:
    trim_text = f"{trim_ft:.2f} ft down by stern"
else:
    trim_text = f"{abs(trim_ft):.2f} ft down by bow"

st.write(f"Trim: {trim_text}")


st.write(f"KMt: {kmt:.2f} ft")
st.write(f"FSC: {fsc:.2f} ft")
st.write(f"GMt (corrected): {gm:.2f} ft")
# ---------------- LIST CALCULATION ----------------
if abs(gm) < 0.01:
    heel_text = "GM ≈ 0, list undefined"
else:
    tan_phi = tm / (disp * gm)
    heel_deg = np.degrees(np.arctan(tan_phi))

    if abs(heel_deg) < 0.05:
        heel_text = "Upright"
    elif heel_deg > 0:
        heel_text = f"{heel_deg:.2f}° to starboard"
    else:
        heel_text = f"{abs(heel_deg):.2f}° to port"

st.write(f"List: {heel_text}")


# ---------------- TANK TOTALS ----------------
st.subheader("Tank Totals")

for grp, val in tank_totals.items():
    st.write(f"{grp}: {val:.2f} LT")

# ---------------- GM CHECK ----------------
st.subheader("GM Check")

st.write(f"Minimum GM: {min_gm:.2f} ft")

if gm >= min_gm:
    st.success("GM PASS")
else:
    st.error("GM FAIL")

# ---------------- VCG CHECK ----------------
st.subheader("VCG Limit Check")

st.write(f"Allowable KG: {allow_kg:.2f} ft")
st.write(f"KG Margin: {margin:.2f} ft")

if margin >= 0:
    st.success("VCG PASS")
else:
    st.error("VCG FAIL")
