"""Idea 1, Test 1f: test1e_criteria.py (unchanged model, criteria a-d, seed 20261112, 10^7 jobs, K = 18080,
overhead 200 ns, T = 12 and 8 us as for the 12-round Test 1b traces) on the Test 1f per-k int4.2.8 traces.
Each schedule (k1..k4, flood) is its own trace -> largest t_iter per k. Output OUTDIR/criteria.json.
Usage: python test1f_criteria.py OUTDIR [workers]
"""
import sys, os
import test1e_criteria as C

R1F = C.ROOT + "/test1f/p{p}_%s.npz"
C.TRACES = {f"1f int4.2.8 {s}": (R1F % s, [p for p in ("0.003", "0.002", "0.001") if os.path.exists(R1F.replace("{p}", p) % "k1")], [12.0, 8.0], 13, False)
            for s in ("k1", "k2", "k3", "k4", "flood")}

if __name__ == "__main__":
    C.main()
