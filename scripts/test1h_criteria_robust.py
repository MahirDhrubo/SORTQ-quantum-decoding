"""Idea 1, Test 1h robustness of the p = 0.003 real-time targets: test1e_criteria.py unchanged (T = 12 us, 10^7 jobs
resampled with seed 20261112, K = 18,080, overhead 200 ns) on
  fresh  : Test 1h step 2 (seed 20261120) rb13 int4.2.8 baseline + float flood, 168,000 shots
  pooled : Test 1g rb13 (Test 1b shots) + fresh rb13 baseline, and Test 1b float flood + fresh float flood, 336,000
Each pair is run as (sweep = rb13, flood = float flood), so the flood trace is checked directly at 24 ns ("ibm_meets",
the model's own IBM check). The float flood traces are also searched on their own for their largest t_iter.
Traces are written to results/test1h/criteria_robust/traces/ (pooled = concatenated iterations).
Usage: python test1h_criteria_robust.py [workers]
"""
import os, sys
import numpy as np
import test1e_criteria as C

D = C.ROOT + "/test1h/criteria_robust"
T = D + "/traces"
C.TRACES = {
    "fresh rb13 (+ float flood at 24 ns)": (T + "/fresh_p{p}_{s}.npz", ["0.003"], [12.0], 13, True),
    "pooled rb13 (+ float flood at 24 ns)": (T + "/pooled_p{p}_{s}.npz", ["0.003"], [12.0], 13, True),
    "fresh float flood": (T + "/fresh_p{p}_flood.npz", ["0.003"], [12.0], 13, False),
    "pooled float flood": (T + "/pooled_p{p}_flood.npz", ["0.003"], [12.0], 13, False),
}


def prep():
    os.makedirs(T, exist_ok=True)
    it = lambda f: np.load(f)["iterations"]
    R = C.ROOT
    fr, ff = it(R + "/test1h/step2/p0.003_rb13_int4.npz"), it(R + "/test1h/step2/p0.003_flood_float.npz")
    gr, bf = it(R + "/test1g/p0.003_rb13.npz"), it(R + "/test1b/p0.003_float_flood.npz")
    for name, a in (("fresh_p0.003_sweep", fr), ("fresh_p0.003_flood", ff),
                    ("pooled_p0.003_sweep", np.concatenate([gr, fr])), ("pooled_p0.003_flood", np.concatenate([bf, ff]))):
        np.savez_compressed(f"{T}/{name}.npz", iterations=a)
        print(name, len(a), float(a.mean()))


if __name__ == "__main__":
    prep()
    sys.argv = [sys.argv[0], D] + sys.argv[1:]
    C.main()
