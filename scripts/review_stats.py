"""Review fixes, part C: paired statistics for every comparison of Fig. 7 (no new decoding).

Traces: results/test1b (float / int4.2.8 x flood / sweep), results/test1g (rb13 int4.2.8, p = 0.003 / 0.002),
results/test1g/p001 (rb13, p = 0.001), results/test1h/step2 (fresh shots, seed 20261120: rb13 int4.2.8, float flood).
For each pair (A, B) on the same shots: failures A / B, both / only A / only B, exact two-sided McNemar p
(test1b_quant.mcnemar), and a 95% CI of the failure ratio A / B = (both + onlyA) / (both + onlyB).

CI of a paired ratio of proportions: Bonett & Price (2006), adjusted Wald on the log scale:
  ln((n11 + b + 1) / (n11 + c + 1)) +- z * sqrt((b + c + 2) / ((n11 + b + 1) (n11 + c + 1)))
  with n11 = both, b = only A, c = only B. Cross-checked by a multinomial bootstrap of the four paired cells
  (20,000 resamples, seed 1, percentile interval).
Output: results/review_fixes/stats.json, stats.md.   Usage: python review_stats.py
"""
import os, json
import numpy as np
from math import log, sqrt, exp
from test1b_quant import mcnemar

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
OUT = os.path.join(R, "review_fixes")
NAMES = dict(ff="float flood", i4f="int4.2.8 flood", fs="float sweep", i4s="int4.2.8 sweep", rb="int4.2.8 red-black")
PAIRS = [("i4f", "ff"), ("fs", "ff"), ("i4s", "ff"), ("rb", "ff"), ("i4s", "i4f"), ("rb", "i4f"), ("i4s", "fs"),
         ("rb", "i4s"), ("rb", "fs")]
Z = 1.959963984540054


def traces(p):
    t = lambda s: os.path.join(R, "test1b", f"p{p}_{s}.npz")
    d = dict(ff=t("float_flood"), i4f=t("int4.2.8_flood"), fs=t("float_sweep"), i4s=t("int4.2.8_sweep"),
             rb=os.path.join(R, "test1g", "p001", "p0.001_rb13.npz") if p == "0.001" else os.path.join(R, "test1g", f"p{p}_rb13.npz"))
    return {k: np.load(v)["logical_fail"].astype(bool) for k, v in d.items()}


def cells(a, b):
    return int((a & b).sum()), int((a & ~b).sum()), int((~a & b).sum()), int((~a & ~b).sum())


def bonett_price(n11, b, c):
    r = (n11 + b + 1) / (n11 + c + 1)
    se = sqrt((b + c + 2) / ((n11 + b + 1) * (n11 + c + 1)))
    return exp(log(r) - Z * se), exp(log(r) + Z * se)


def boot(n11, b, c, n00, B=20000, seed=1):
    rng = np.random.default_rng(seed)
    n = n11 + b + c + n00
    m = rng.multinomial(n, np.array([n11, b, c, n00]) / n, size=B)
    fa, fb = m[:, 0] + m[:, 1], m[:, 0] + m[:, 2]
    ok = fb > 0
    q = np.percentile(fa[ok] / fb[ok], [2.5, 97.5])
    return float(q[0]), float(q[1])


def row(label, p, a_name, b_name, n11, b, c, n00):
    fa, fb = n11 + b, n11 + c
    lo, hi = bonett_price(n11, b, c)
    blo, bhi = boot(n11, b, c, n00)
    return dict(set=label, p=p, A=a_name, B=b_name, shots=n11 + b + c + n00, fails_A=fa, fails_B=fb, both=n11,
                only_A=b, only_B=c, mcnemar_p=mcnemar(b, c), ratio=(fa / fb if fb else None),
                ci95=[lo, hi], ci95_bootstrap=[blo, bhi])


def main():
    os.makedirs(OUT, exist_ok=True)
    rows = []
    for p in ("0.003", "0.002", "0.001"):
        D = traces(p)
        for a, b in PAIRS:
            rows.append(row("Test 1b shots", p, a, b, *cells(D[a], D[b])))
    # fresh set (Test 1h step 2) and pooled red-black vs float flood at p = 0.003
    D = traces("0.003")
    fr = np.load(os.path.join(R, "test1h", "step2", "p0.003_rb13_int4.npz"))["logical_fail"].astype(bool)
    ff = np.load(os.path.join(R, "test1h", "step2", "p0.003_flood_float.npz"))["logical_fail"].astype(bool)
    c1, c2 = cells(D["rb"], D["ff"]), cells(fr, ff)
    rows.append(row("fresh shots (seed 20261120)", "0.003", "rb", "ff", *c2))
    rows.append(row("pooled (336,000)", "0.003", "rb", "ff", *[x + y for x, y in zip(c1, c2)]))
    json.dump(rows, open(os.path.join(OUT, "stats.json"), "w"), indent=1)
    L = ["| Shot set | p | A | B | Failures A / B | Both | Only A | Only B | McNemar p | Ratio A/B | 95% CI (Bonett–Price) | 95% CI (bootstrap) |",
         "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append(f"| {r['set']} | {r['p']} | {NAMES[r['A']]} | {NAMES[r['B']]} | {r['fails_A']} / {r['fails_B']} | {r['both']} | "
                 f"{r['only_A']} | {r['only_B']} | {r['mcnemar_p']:.3g} | {r['ratio']:.3f} | {r['ci95'][0]:.2f}–{r['ci95'][1]:.2f} | "
                 f"{r['ci95_bootstrap'][0]:.2f}–{r['ci95_bootstrap'][1]:.2f} |")
    open(os.path.join(OUT, "stats.md"), "w").write("\n".join(L) + "\n")
    print("\n".join(L))


if __name__ == "__main__":
    main()
