"""Condition serialization and preliminary calculations; vessel data is unverified."""
import copy
import math
import numpy as np


def default_condition(tanks):
    return dict(schema_version=2, name="Untitled condition", operator="",
                ls_disp=1166.86, ls_lcg=96.55, ls_kg=17.07, min_gm=0.5,
                tank_soundings={k: 0.0 for k in tanks},
                tank_empty={k: False for k in tanks}, cargo=[], cargo_names=[],
                observed_fwd=None, observed_aft=None)


def normalize(raw, tanks):
    if not isinstance(raw, dict):
        raise ValueError("The condition file must contain a JSON object.")
    if raw.get("schema_version", 1) not in (1, 2):
        raise ValueError("Unsupported condition file version.")
    out = default_condition(tanks)
    def number(x, label):
        if isinstance(x, bool):
            raise ValueError(f"{label} must be a number.")
        try:
            x = float(x)
        except (TypeError, ValueError):
            raise ValueError(f"{label} must be a number.")
        if not math.isfinite(x):
            raise ValueError(f"{label} must be finite.")
        return x
    for k in ("ls_disp", "ls_lcg", "ls_kg", "min_gm"):
        out[k] = number(raw.get(k, out[k]), k)
    if out["ls_disp"] <= 0 or out["min_gm"] < 0:
        raise ValueError("Lightship must be positive and the GM threshold nonnegative.")
    for k in ("name", "operator"):
        out[k] = str(raw.get(k, out[k]))[:200]
    for field in ("tank_soundings", "tank_empty"):
        data = raw.get(field, {})
        if not isinstance(data, dict):
            raise ValueError(f"{field} must be an object.")
        unknown = set(data) - set(tanks)
        if unknown:
            raise ValueError("Condition contains unknown tank identifiers.")
        for k, value in data.items():
            if field == "tank_empty":
                if not isinstance(value, bool):
                    raise ValueError("Empty flags must be true or false.")
                out[field][k] = value
            else:
                out[field][k] = number(value, k)
    cargo = raw.get("cargo", [])
    if not isinstance(cargo, list) or len(cargo) > 20:
        raise ValueError("A condition may contain up to 20 cargo items.")
    names = raw.get("cargo_names", [])
    if not isinstance(names, list):
        raise ValueError("Cargo names must be a list.")
    for i, row in enumerate(cargo):
        if not isinstance(row, (list, tuple)) or len(row) != 4:
            raise ValueError(f"Cargo {i+1} needs weight, LCG, VCG, and TCG.")
        values = [number(v, f"Cargo {i+1}") for v in row]
        if values[0] < 0:
            raise ValueError("Cargo weight cannot be negative.")
        out["cargo"].append(values)
        out["cargo_names"].append(str(names[i])[:200] if i < len(names) else "")
    for k in ("observed_fwd", "observed_aft"):
        v = raw.get(k)
        out[k] = None if v is None else number(v, k)
        if out[k] is not None and out[k] < 0:
            raise ValueError("Observed drafts cannot be negative.")
    return out


def tank_weight(td, sounding, empty):
    xs, ys = np.array(td["sounding_ft"]), np.array(td["weight_lt"])
    if len(xs) < 2 or len(xs) != len(ys) or not np.all(np.isfinite(xs)) or not np.all(np.isfinite(ys)):
        raise ValueError("Invalid sounding table.")
    if np.any(np.diff(xs) <= 0) or np.any(np.diff(ys) < 0) or np.any(ys < 0):
        raise ValueError("Sounding table must increase consistently.")
    if empty:
        return 0.0
    if not math.isfinite(sounding) or not xs[0] <= sounding <= xs[-1]:
        raise ValueError(f"Enter {xs[0]:.2f}–{xs[-1]:.2f} ft or confirm the tank is empty.")
    return float(np.interp(sounding, xs, ys))


def calculate(c, tanks, hs, vcg, labels):
    errors, warnings = [], []
    disp = c["ls_disp"]
    mx, mz, tm, fsm = disp*c["ls_lcg"], disp*c["ls_kg"], 0.0, 0.0
    totals = {k: 0.0 for k in ("Fuel", "Ballast", "Water", "Other")}
    for w, l, v, t in c["cargo"]:
        disp += w; mx += w*l; mz += w*v; tm += w*t
    for name, td in tanks.items():
        try:
            w = tank_weight(td, c["tank_soundings"][name], c["tank_empty"][name])
        except ValueError as e:
            errors.append(f"{labels.get(name, name)}: {e}")
            continue
        disp += w; mx += w*td["lcg_ft"]; mz += w*td["vcg_ft"]; tm += w*td.get("tcg_ft", 0)
        fsm += td.get("fsm_ftlt", 0)
        totals[td.get("group", "Other")] += w
    if errors:
        return {}, errors, warnings
    r = dict(displacement=disp, lcg=mx/disp, kg=mz/disp, fsc=fsm/disp, totals=totals)
    if not hs.disp_lt.min() <= disp <= hs.disp_lt.max():
        errors.append("Displacement is outside the hydrostatic table. Draft, trim and GM are unavailable.")
        return r, errors, warnings
    # Retain existing equations. Do not silently replace suspect source rows.
    if np.any(np.diff(hs.draft_ft) <= 0):
        warnings.append("Existing hydrostatic table contains inconsistent rows. All hydrostatic results are preliminary.")
    def hydro(col):
        return float(np.interp(disp, hs.disp_lt, hs[col]))
    draft, kmt, lcb, lcf = (hydro(k) for k in ("draft_ft", "kmt_ft", "lcb_ft", "lcf_ft"))
    mtc = hydro("mct_ftlt_per_198ft")
    if mtc <= 0:
        errors.append("Invalid trim coefficient.")
        return r, errors, warnings
    trim = disp*(r["lcg"]-lcb)/mtc/12
    gm = kmt-r["kg"]-r["fsc"]
    r.update(draft=draft, kmt=kmt, trim=trim, fwd=draft-trim*lcf/200,
             aft=draft+trim*(200-lcf)/200, gm=gm)
    if gm > 0.01:
        r["list"] = math.degrees(math.atan(tm/(disp*gm)))
    else:
        errors.append("Corrected GM is nonpositive or near zero; normal list estimate is unavailable.")
    if vcg.draft_ft.min() <= draft <= vcg.draft_ft.max():
        r["allow_kg"] = float(np.interp(draft, vcg.draft_ft, vcg.vcg_no_trim_ft))
        r["margin"] = r["allow_kg"]-r["kg"]
    else:
        errors.append("Draft is outside the available VCG curve; KG margin is unavailable.")
    return r, errors, warnings
