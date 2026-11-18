"""Idea 1, Test 1h: pick (after step 2) and report (after step 3), from the traces only.
  pick   <outdir>   step 2: fewest failures among the rb int4.2.8 settings, ties -> fewer mean iterations
                    -> <outdir>/chosen.json
  report <outdir>   steps 1-3 + criteria -> <outdir>/report.json (printed)
McNemar: test1b_quant.mcnemar (exact two-sided binomial on the discordant shots), as in Tests 1b-1g.
"""
import sys, os, json
import numpy as np
from test1b_quant import mcnemar

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
STEP2 = ["rb13_int4", "rb13_int4_g0.0625", "rb13_int4_g0.25", "rb13_int4_i0.15_0.5", "rb13_int4_i0.3_0.7", "odd13_int4"]


def load(path):
    return dict(np.load(path))


def stats(d):
    fl, it = d["logical_fail"], d["iterations"]
    return dict(shots=int(len(fl)), fails=int(fl.sum()), ler=float(fl.mean()), mean_it=float(it.mean()),
                p50=float(np.percentile(it, 50)), p99=float(np.percentile(it, 99)), p99_9=float(np.percentile(it, 99.9)),
                max_it=int(it.max()), not_converged=int((~d["success"]).sum()))


def pair(a, b):
    n = min(len(a["logical_fail"]), len(b["logical_fail"]))   # equal in the full run; smoke = a prefix only
    fa, fb = a["logical_fail"][:n], b["logical_fail"][:n]
    oa, ob = int(np.sum(fa & ~fb)), int(np.sum(~fa & fb))
    return dict(shots_compared=int(n), both=int(np.sum(fa & fb)), only_A=oa, only_B=ob, mcnemar_p=mcnemar(oa, ob),
                ratio=float(fa.sum() / fb.sum()) if fb.sum() else None)


def same(a, b):
    n = min(len(a["iterations"]), len(b["iterations"]))
    return {k: int(np.sum(a[k][:n] != b[k][:n])) for k in ("iterations", "success", "logical_fail", "dec_crc") if k in a and k in b}


def step2(out):
    d = os.path.join(out, "step2")
    ref = load(os.path.join(d, "p0.003_flood_float.npz"))
    rows = {"flood_float": stats(ref)}
    for c in STEP2:
        x = load(os.path.join(d, f"p0.003_{c}.npz"))
        rows[c] = dict(stats(x), vs_float_flood=pair(x, ref))
    base = load(os.path.join(d, "p0.003_rb13_int4.npz"))
    rows["identical_to_baseline"] = {c: same(load(os.path.join(d, f"p0.003_{c}.npz")), base) for c in STEP2[1:]}
    return rows


def pick(out):
    rows = step2(out)
    best = min(STEP2, key=lambda c: (rows[c]["fails"], rows[c]["mean_it"]))
    json.dump(dict(chosen=best, rule="fewest failures, ties -> fewer mean iterations",
                   candidates={c: [rows[c]["fails"], rows[c]["mean_it"]] for c in STEP2}),
              open(os.path.join(out, "chosen.json"), "w"), indent=1)
    print("chosen", best, {c: (rows[c]["fails"], round(rows[c]["mean_it"], 3)) for c in STEP2})


def report(out):
    t1b = lambda p, s: load(os.path.join(R, "test1b", f"p{p}_{s}.npz"))
    res = {}
    # step 1
    s1 = os.path.join(out, "step1")
    rf, ri = load(os.path.join(s1, "p0.003_rb13_float.npz")), load(os.path.join(s1, "p0.003_rb13_int4.npz"))
    ff, fs = t1b("0.003", "float_flood"), t1b("0.003", "float_sweep")
    res["step1"] = dict(rb13_float=stats(rf), float_flood=stats(ff), float_sweep=stats(fs),
                        rb13_int4=stats(ri), int4_flood=stats(t1b("0.003", "int4.2.8_flood")),
                        rb13_float_vs_float_flood=pair(rf, ff), rb13_float_vs_float_sweep=pair(rf, fs),
                        rb13_int4_vs_float_flood=pair(ri, ff), rb13_int4_vs_rb13_float=pair(ri, rf),
                        identity_rb13_int4_vs_test1g=same(ri, load(os.path.join(R, "test1g", "p0.003_rb13.npz"))),
                        identity_flood_sweep_shots="Test 1b traces, same sampler seed / batch x workers")
    res["step2"] = step2(out)
    J = json.load(open(os.path.join(out, "chosen.json"))); c = J["chosen"]; res["chosen"] = J
    s3 = {}
    for p in ("0.003", "0.002"):
        f = os.path.join(out, "step3", f"p{p}_{c}.npz")
        if not os.path.exists(f):
            continue
        x = load(f); ref = t1b(p, "float_flood")
        s3[p] = dict(chosen=stats(x), float_flood=stats(ref), vs_float_flood=pair(x, ref),
                     vs_int4_sweep=pair(x, t1b(p, "int4.2.8_sweep")),
                     vs_test1g_rb13=pair(x, load(os.path.join(R, "test1g", f"p{p}_rb13.npz"))))
        if c == "rb13_int4":
            s3[p]["identity_vs_test1g"] = same(x, load(os.path.join(R, "test1g", f"p{p}_rb13.npz")))
    res["step3"] = s3
    cf = os.path.join(out, "criteria", "criteria.json")
    if os.path.exists(cf):
        res["criteria"] = [r for r in json.load(open(cf))["rows"]]
    json.dump(res, open(os.path.join(out, "report.json"), "w"), indent=1, default=float)
    print(json.dumps(res, indent=1, default=float))


if __name__ == "__main__":
    {"pick": pick, "report": report}[sys.argv[1]](sys.argv[2])
