"""Idea 1, Test 2d: resource model from the measured Test 2c post-route numbers (no new decoding / synthesis here).

Inputs (all measured earlier):
  hw/synth/results.json                 post-route LUT / FF / LUTRAM per run and per sub-instance (Test 2c + 2d runs)
  results/test1f/criteria/criteria.json largest t_iter per schedule (k1..k4, flood), int4.2.8, 13-round decode
  results/test1e/criteria/criteria.json W12_C8 targets (Test 1d windows, F32 sweep), p = 0.003 / 0.002
X decoder H (dem_tools.xdecoder_problem, 12-round circuit): 936 checks (792 deg 35, 72 deg 25, 72 deg 16),
8,784 errors (deg 2: 864, 3: 5,328, 4: 864, 5: 864, 6: 864), 30,672 edges.
Output: results/test2d/model.json, results/test2d/pareto.csv; tables printed.
Usage: python test2d_model.py
"""
import os, json, csv

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
R = json.load(open(os.path.join(ROOT, "hw/synth/results.json")))
C1F = json.load(open(os.path.join(ROOT, "results/test1f/criteria/criteria.json")))["rows"]
C1E = json.load(open(os.path.join(ROOT, "results/test1e/criteria/criteria.json")))["rows"]
# REF_RUN (env): reference engine run for the P1 point (default: the Test 2c follow-up run); OUT_SUB: output subfolder
REF_RUN = os.environ.get("REF_RUN", "engine_top_pf2_p1_lutram_fmax")
OUT = os.path.join(ROOT, "results/test2d", os.environ.get("OUT_SUB", "")); os.makedirs(OUT, exist_ok=True)
DEV_LUT = 4085760
CHK = {35: 792, 25: 72, 16: 72}
VAR = {2: 864, 3: 5328, 4: 864, 5: 864, 6: 864}
IBM_LUT, IBM_PCT, IBM_T_ITER = 2.1e6, 51.6, 24.0     # IBM figures as given in the task / as used in Test 1e
M = {}


def u(run, k="lut"):
    return R[run]["util"].get(k, 0.0)


def sub(run, inst, k="lut"):
    for s in R[run]["sub"]:
        if s["inst"] == inst:
            return s.get(k, 0.0)
    raise KeyError((run, inst))


def lanes(run, k="lut"):
    return sum(s.get(k, 0.0) for s in R[run]["sub"] if s["inst"].startswith("g_lt"))


# ------------------------------------------------------------------ 1. fully parallel X decoder from our blocks
cnu_run = {35: "cnu", 25: "cnu_d25", 16: "cnu_d16"}
vnu_run = {6: "vnu", 5: "vnu_d5", 4: "vnu_d4", 3: "vnu_d3", 2: "vnu_d2"}
cal = dict(cnu={d: dict(n=n, lut=u(cnu_run[d]), ff=u(cnu_run[d], "ff")) for d, n in CHK.items()},
           vnu={d: dict(n=n, lut=u(vnu_run[d]), ff=u(vnu_run[d], "ff")) for d, n in VAR.items()})
cal["cnu_lut"] = sum(v["n"] * v["lut"] for v in cal["cnu"].values())
cal["vnu_lut"] = sum(v["n"] * v["lut"] for v in cal["vnu"].values())
cal["cnu_ff"] = sum(v["n"] * v["ff"] for v in cal["cnu"].values())
cal["vnu_ff"] = sum(v["n"] * v["ff"] for v in cal["vnu"].values())
ref = REF_RUN
lane_lut, lane_ff = lanes(ref) / 720, lanes(ref, "ff") / 720
cal["gamma_lane_lut_each"], cal["gamma_lane_ff_each"] = lane_lut, lane_ff
cal["gamma_lanes_lut"] = 8784 * lane_lut
cal["mpost_ff"] = 8784 * 7                  # M(t-1) per error (7-bit marginal), registers
cal["base_lut"] = cal["cnu_lut"] + cal["vnu_lut"]
cal["with_gamma_lut"] = cal["base_lut"] + cal["gamma_lanes_lut"]
cal["ratio_base_vs_ibm"] = cal["base_lut"] / IBM_LUT
cal["ratio_gamma_vs_ibm"] = cal["with_gamma_lut"] / IBM_LUT
M["calibration"] = cal

# ------------------------------------------------------------------ 2. SORTQ engines, k rounds per layer
eng = {"pf2 P1": (REF_RUN, 1), "pf2 P2": ("engine_top_pf2_p2_lutram_fmax", 2),
       "pf P1": ("engine_top_pf_p1_lutram_fmax", 1)}
E = {}
for name, (run, P) in eng.items():
    tot, rs = u(run), sub(run, "u_rs")
    ff, rsff = u(run, "ff"), sub(run, "u_rs", "ff")
    period = R[run]["period"]
    E[name] = dict(run=run, passes=P, period_ns=period, clock_mhz=1000 / period, lut_total=tot, lut_round_step=rs,
                   lut_shared=tot - rs, ff_total=ff, ff_round_step=rsff, lutram=u(run, "lutram"),
                   gamma_lanes_lut=lanes(run), k={})
    for k in (1, 2, 3, 4):
        layers = {1: 13, 2: 7, 3: 5, 4: 4}[k]
        E[name]["k"][k] = dict(
            lut=tot + (k - 1) * rs, lut_pct=100 * (tot + (k - 1) * rs) / DEV_LUT,
            lut_with_lanes=tot + (k - 1) * (rs + lanes(run)),
            ff=ff + (k - 1) * rsff, lutram=u(run, "lutram"),
            layers_13r=layers, cycles_13r=layers * (P + 1), ns_13r=layers * (P + 1) * period,
            cycles_w12=(12 if k == 1 else None) and 12 * (P + 1), ns_w12=(12 * (P + 1) * period if k == 1 else None),
            measured=(k == 1))
M["engines"] = E

# ------------------------------------------------------------------ 3. memory variants (analytic)
lr = {f: sub(ref, f, "lutram") for f in ("u_m_v2c_o0", "u_m_c2v_o1")}
BITS = dict(v2c_o0=22 * 72 * 5, c2v_o1=13 * 72 * 5, marg=4 * 504 * 7 + 2 * 216 * 7, g8=720 * 3 + 504 * 3)
per_bit = lr["u_m_v2c_o0"] / BITS["v2c_o0"]          # measured LUTRAM per (bit per slot), depth 12
total_slot = BITS["v2c_o0"] + BITS["c2v_o1"] + BITS["marg"] + BITS["g8"]
var = {}
a_bits = 72 * (4 + 4 + 6 + 13)                       # min1, min2, min1 index (35 -> 6 bits), 13 offset-1 signs
var["a"] = dict(name="compressed c2v_o1 per check", old_bits=BITS["c2v_o1"], new_bits=a_bits,
                delta_bits=a_bits - BITS["c2v_o1"], delta_lutram=(a_bits - BITS["c2v_o1"]) * per_bit,
                decompress_edges=13 * 72, decompress_lut_est=13 * 72 * 5)
b_add_c2v = 72 * (4 + 4 + 6 + 35)                    # old c2v of all 35 edges, compressed (needed for v2c = M - c2v)
b_marg_wide = BITS["marg"] * 9 // 7 - BITS["marg"]   # marginal stored unsaturated: 9 bits instead of 7
var["b"] = dict(name="v2c not stored, recomputed", removed_bits=BITS["v2c_o0"] + BITS["c2v_o1"],
                added_bits=b_add_c2v + b_marg_wide, added_c2v_bits=b_add_c2v, added_marg_bits=b_marg_wide,
                delta_bits=b_add_c2v + b_marg_wide - BITS["v2c_o0"] - BITS["c2v_o1"],
                delta_lutram=(b_add_c2v + b_marg_wide - BITS["v2c_o0"] - BITS["c2v_o1"]) * per_bit,
                subtractors=22 * 72, recompute_lut_est=22 * 72 * (9 + 6 + 5))
c_bits = 720 * 5 + 504 * 5                           # per-error priors of the errors updated in a step (cur + prev)
var["c"] = dict(name="per-error prior RAM", bits_per_row=c_bits, rows=13, total_bits=13 * c_bits,
                lutram=c_bits * per_bit, removed_ff=u("prior_rf", "ff"), removed_lut=u("prior_rf"),
                removed_copies_ff=18 * 150 + 6 * 150)
M["memory"] = dict(lutram_per_bit_slot=per_bit, bits_per_slot=BITS, total_bits_per_slot=total_slot, variants=var)


# ------------------------------------------------------------------ 4. Pareto
def tmax(trace, p, crit, T=12.0, rows=C1F):
    for r in rows:
        if r["trace"] == trace and r["p"] == p and r["T_us"] == T and r["crit"] == crit:
            return r["t_iter_max_ns"]
    return "n/a"


def meets(ns, trace, p, rows=C1F, T=12.0):
    out = []
    for c in "abcd":
        t = tmax(trace, p, c, T, rows)
        if t == "n/a":
            return "n/a"
        if t is not None and ns <= t:
            out.append(c)
    return "".join(out) or "none"


PS = ["0.001", "0.002", "0.003"]
rows = [dict(design="IBM fully parallel (flood)", k="flood", passes="-", lut=IBM_LUT, lut_pct=IBM_PCT,
             clock="as published", ns_13r=IBM_T_ITER, ns_w12=None,
             **{f"meets_13r_p{p}": meets(IBM_T_ITER, "1f int4.2.8 flood", p) for p in PS},
             **{f"meets_w12_p{p}": "n/a" for p in PS})]
for name in ("pf2 P1", "pf2 P2", "pf P1"):
    e = E[name]
    for k in (1, 2, 3, 4):
        x = e["k"][k]
        r = dict(design=f"SORTQ {name}", k=k, passes=e["passes"], lut=x["lut"], lut_pct=x["lut_pct"],
                 clock=f"{e['clock_mhz']:.1f} MHz {'measured' if k == 1 else 'assumed = k1'}",
                 ns_13r=x["ns_13r"], ns_w12=x["ns_w12"])
        for p in PS:
            r[f"meets_13r_p{p}"] = meets(x["ns_13r"], f"1f int4.2.8 k{k}", p)
            r[f"meets_w12_p{p}"] = (meets(x["ns_w12"], "1d W12_C8", p, rows=C1E, T=8.0) if k == 1 else "n/a")
        rows.append(r)
M["pareto"] = rows
json.dump(M, open(os.path.join(OUT, "model.json"), "w"), indent=1, default=float)
with open(os.path.join(OUT, "pareto.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader()
    for r in rows:
        w.writerow({k: (round(v, 1) if isinstance(v, float) else v) for k, v in r.items()})

# ------------------------------------------------------------------ print
print("calibration:", json.dumps({k: v for k, v in cal.items() if not isinstance(v, dict)}, indent=1))
for d in ("cnu", "vnu"):
    print(d, {k: (v["n"], v["lut"], v["ff"]) for k, v in cal[d].items()})
for name, e in E.items():
    print(name, {k: v for k, v in e.items() if k != "k"})
    for k, x in e["k"].items():
        print("   k", k, {kk: (round(vv, 1) if isinstance(vv, float) else vv) for kk, vv in x.items()})
print("memory", json.dumps(M["memory"], indent=1, default=float))
for r in rows:
    print(r)
