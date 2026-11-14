import streamlit as st
import pandas as pd
import numpy as np
import json
from pathlib import Path

LBP_FT = 200.0
MAX_ALLOWABLE_DRAFT = 16.0
SAVE_FILE = Path("saved_condition.json")


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
    hs = pd.read_csv("data/hydrostatics.csv").sort_values("disp_lt")
    vcg = pd.read_csv("data/allowable_vcg.csv").sort_values("draft_ft")
    with open("data/tanks.json") as f:
        tanks = json.load(f)
    return hs, vcg, tanks

hs, vcg_curve, tanks = load_data()

#st.write("Loaded tanks:", list(tanks.keys()))

st.title("Responder Stability - Trim, Draft, VCG, and GM")

# ---------------- Lightship Corrections ----------------
Lightship_Corrections = [
    # (weight LT, LCG ft, VCG ft, TCG ft)
    (-350.0, 108.0, 20.0, -0.9),
    (0.0,  0.0,  0.0, 0.0),
    (0.0,  0.0,  0.0, 0.0),
]


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

        # Cargo
        if "cargo" in saved:
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

tank_soundings = {}
for t in tanks:
    tank_soundings[t] = st.sidebar.number_input(t, value=0.0, key=f"snd_{t}")

# ---------------- CARGO INPUT ----------------
st.sidebar.header("Cargo / Deck Loads")

cargo = []
num_cargo = st.sidebar.number_input("Number of cargo items", min_value=0, max_value=20, value=3)

for i in range(num_cargo):
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

    # Cargo
    save_data["cargo"] = cargo

    SAVE_FILE.write_text(json.dumps(save_data, indent=2))
    st.sidebar.success("Condition saved")


# ---------------- WEIGHT SUMMATION ----------------
disp = ls_disp
mx = ls_disp * ls_lcg
mz = ls_disp * ls_kg
tm = 0.0
fsm_total = 0.0
# Apply fixed weights (hidden from user)
for w, l, v, t in Lightship_Corrections:
    disp += w
    mx += w * l
    mz += w * v
    tm += w * t

tank_totals = {"Fuel": 0.0, "Ballast": 0.0, "Other": 0.0}

for w, l, v, t in cargo:
    disp += w
    mx += w * l
    mz += w * v
    tm += w * t

# ---- TANK TABLE VALIDATION (TEMP) ----
for name, td in tanks.items():
    xs = td["sounding_ft"]
    ys = td["weight_lt"]
    if len(xs) != len(ys):
        st.error(f"{name} length mismatch: sounding={len(xs)} weight={len(ys)}")

for t, snd in tank_soundings.items():
    td = tanks[t]

    wt = lin_interp(snd, td["sounding_ft"], td["weight_lt"])
    disp += wt
    mx += wt * td["lcg_ft"]
    mz += wt * td["vcg_ft"]
    tm += wt * td.get("tcg_ft", 0.0)
    fsm_total += td.get("fsm_ftlt", 0.0)

    group = td.get("group", "Other")
    tank_totals[group] = tank_totals.get(group, 0.0) + wt

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
