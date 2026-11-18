"""Idea 1, Test 1h: test1e_criteria.py (unchanged model) on the step-3 traces of the chosen setting
(results/test1h/step3/p{p}_<chosen>.npz, p = 0.003 and 0.002), T = 12 us. The override is at module level so the
pool workers (forkserver start) see it.   Usage: python test1h_criteria.py OUTDIR [workers]
"""
import os, json
import test1e_criteria as C

_c = json.load(open(os.path.join(C.ROOT, "test1h", "chosen.json")))["chosen"]
C.TRACES = {f"1h {_c}": (C.ROOT + "/test1h/step3/p{p}_" + _c + ".npz", ["0.003", "0.002"], [12.0], 13, False)}

if __name__ == "__main__":
    C.main()
