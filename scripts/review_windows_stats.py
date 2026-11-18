"""Review fixes, part A.1 statistics: sliding-window (W12_C8) vs global red-black int4.2.8 decoding, 36 rounds.

Inputs: results/review_fixes/windows/p{p}_{W12_C8,global}.npz (review_windows.py merge; same shots for both settings).
Per p: failures, LER per shot and per round (1 - (1 - 2 LER)^(1/36)) / 2 with Wilson 95% intervals mapped through
the same function, paired cells, exact McNemar p and Bonett-Price 95% CI of the failure ratio W12_C8 / global
(review_stats.row, bootstrap cross-check), and per window: iterations (mean, p99.9, max), fraction > 80 iterations,
legs (1 if n <= 80 else 1 + ceil((n - 80) / 60); mean, max), windows not converged.
Output: results/review_fixes/windows_stats.json (printed).
"""
import os, json
import numpy as np
from math import sqrt
from review_stats import cells, row, Z

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results", "review_fixes")
NR = 36


def wilson(k, n):
    ph = k / n; d = 1 + Z * Z / n
    c = (ph + Z * Z / (2 * n)) / d; h = Z * sqrt(ph * (1 - ph) / n + Z * Z / (4 * n * n)) / d
    return c - h, c + h


def per_round(l):
    return (1 - (1 - 2 * l) ** (1 / NR)) / 2


def legs(it):
    return np.where(it <= 80, 1, 1 + -(-(it - 80) // 60))


def main():
    out = []
    for p in ("0.003", "0.002"):
        d = {s: np.load(os.path.join(R, "windows", f"p{p}_{s}.npz")) for s in ("W12_C8", "global")}
        fw, fg = d["W12_C8"]["logical_fail"].astype(bool), d["global"]["logical_fail"].astype(bool)
        n = len(fw)
        e = dict(p=p, shots=n, paired=row("windows", p, "W12_C8", "global", *cells(fw, fg)), settings={})
        for s, x in d.items():
            f = int(x["logical_fail"].sum()); lo, hi = wilson(f, n); it = x["iterations"].astype(np.int64)
            lg = legs(it)
            e["settings"][s] = dict(
                fails=f, ler=f / n, ler_ci95=[lo, hi], ler_per_round=per_round(f / n),
                ler_per_round_ci95=[per_round(lo), per_round(hi)], window_layers=x["window_layers"].tolist(),
                windows_not_converged=int((~x["window_converged"]).sum()),
                shots_with_a_window_not_converged=int((~x["window_converged"]).any(1).sum()),
                syndrome_ok=int(x["syndrome_ok"].sum()),
                per_window=[dict(window=k, t=int(x["window_t"][k]), layers=int(x["window_layers"][k]),
                                 mean_it=float(it[:, k].mean()), p999_it=float(np.percentile(it[:, k], 99.9)),
                                 max_it=int(it[:, k].max()), frac_over_80=float((it[:, k] > 80).mean()),
                                 mean_legs=float(lg[:, k].mean()), max_legs=int(lg[:, k].max()),
                                 not_converged=int((~x["window_converged"][:, k]).sum()))
                            for k in range(it.shape[1])],
                sum_it_per_shot_mean=float(it.sum(1).mean()))
        out.append(e)
    json.dump(out, open(os.path.join(R, "windows_stats.json"), "w"), indent=1, default=float)
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
