"""Eval task 2: test1e_criteria.py (unchanged model) on the p = 0.001 rb13 trace (results/test1g/p001), T = 12 and 8 us.
The TRACES override is at module level so the pool workers (forkserver start) see it.
Usage: python test1g_criteria_p001.py OUTDIR [workers]
"""
import test1e_criteria as C

C.TRACES = {"1g int4.2.8 rb13": (C.ROOT + "/test1g/p001/p{p}_rb13.npz", ["0.001"], [12.0, 8.0], 13, False)}

if __name__ == "__main__":
    C.main()
