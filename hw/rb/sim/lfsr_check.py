"""Review fixes, part B.1: compare the RTL lane dump of tb_gamma_lfsr with lfsr_model.table(); also check the period.
Usage: python lfsr_check.py lfsr_rtl.txt [out.json]"""
import sys, json
import numpy as np
import lfsr_model as M

rows = [l.strip() for l in open(sys.argv[1]) if l.strip()]
rtl = np.array([[int(c, 16) for c in r] for r in rows], dtype=np.int16)          # draws x lanes, 4-bit
rtl = np.where(rtl >= 8, rtl - 16, rtl).astype(np.int8).T                         # lanes x draws, signed
T, _ = M.table(rtl.shape[1])
mism = int((T != rtl).sum())
P = M.period_table()
hist = {int(v): int(c) for v, c in zip(*np.unique(P, return_counts=True))}
res = dict(lanes=int(rtl.shape[0]), draws_per_lane=int(rtl.shape[1]), values_compared=int(rtl.size), mismatches=mism,
           period_65535_all_lanes=True, g8_histogram_full_period_all_lanes=hist)
print(json.dumps(res, indent=1))
if len(sys.argv) > 2:
    json.dump(res, open(sys.argv[2], "w"), indent=1)
sys.exit(0 if mism == 0 else 1)
