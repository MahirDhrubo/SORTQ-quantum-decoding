"""Idea 1, Test 1g: test1e_criteria.py (unchanged model, criteria a-d, seed 20261112, 10^7 jobs, K = 18080,
overhead 200 ns, T = 12 and 8 us as for the 12-round Test 1b traces) on the Test 1g traces (sweep, rb13, rb2).
Usage: python test1g_criteria.py OUTDIR [workers]
"""
import test1e_criteria as C

R1G = C.ROOT + "/test1g/p{p}_%s.npz"
C.TRACES = {f"1g int4.2.8 {s}": (R1G % s, ["0.003", "0.002"], [12.0, 8.0], 13, False) for s in ("sweep", "rb13", "rb2")}

if __name__ == "__main__":
    C.main()
