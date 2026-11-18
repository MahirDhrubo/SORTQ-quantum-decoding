"""Test 2a: random CNU / VNU vectors for message width N (default 6 = the int6.4.8 option), from the ARITHMETIC.md
model (the same numpy formulas that matched the golden int4 dumps with 0 mismatches). NOT golden dumps: the dump
format stores 8-bit values and int6 marginals need 9 bits.
Same line formats as check_and_vectors.py (cnu_vectors / vnu_vectors), so tb_cnu / tb_vnu read them with -GN=<N>.
Usage: python gen_vectors_random.py N n_cnu n_vnu outdir
"""
import sys, os
import numpy as np


def main():
    N, ncnu, nvnu, out = int(sys.argv[1]), int(sys.argv[2]), int(sys.argv[3]), sys.argv[4]
    MSG = (1 << N) - 1; MB = N + 3; MMIN, MMAX = -(1 << (MB - 1)), (1 << (MB - 1)) - 1
    rng = np.random.default_rng(N * 1000 + 7)
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, f"cnu_vectors_N{N}.txt"), "w") as f:
        for _ in range(ncnu):
            deg = int(rng.integers(1, 36))
            mask = np.zeros(35, int); mask[rng.choice(35, deg, replace=False)] = 1
            # magnitudes: mostly small with ties (realistic), sometimes full range
            mag = rng.integers(0, MSG + 1, 35) if rng.random() < 0.5 else np.minimum(rng.geometric(0.3, 35) - 1, MSG)
            sg = rng.integers(0, 2, 35); syn = int(rng.integers(0, 2))
            v = np.where(mask == 1, mag, MSG)
            m1 = v.min(); m2 = np.partition(v, 1)[1]
            i1 = int(np.argmax(v == m1))                          # first index of min1 (RTL tie rule)
            par = (syn + int((sg * mask).sum())) & 1
            om = np.where(mask == 1, np.where(np.arange(35) == i1, m2, m1), 0)
            om = np.where((mask == 1) & (mag == m1), m2, om)       # golden rule: every edge equal to min1 gets min2
            osg = np.where(mask == 1, par ^ sg, 0)
            f.write(" ".join(map(str, [syn, *mask, *sg, *mag, *osg, *om])) + "\n")
    with open(os.path.join(out, f"vnu_vectors_N{N}.txt"), "w") as f:
        for _ in range(nvnu):
            d = int(rng.integers(1, 7)); mask = np.zeros(6, int); mask[:d] = 1
            late = rng.integers(0, 2, 6) * mask; init = int(rng.random() < 0.2)
            prior = int(rng.integers(-MSG, MSG + 1)); g8 = int(rng.integers(-2, 6)); mp = int(rng.integers(MMIN, MMAX + 1))
            st = rng.integers(-MSG, MSG + 1, 6)
            bias = min(max(((8 - g8) * prior + g8 * mp + 4) >> 3, MMIN), MMAX)
            eff = np.where((mask == 1) & ~((init == 1) & (late == 1)), st, 0)
            tot = bias + int(eff.sum()); mg = min(max(tot, MMIN), MMAX)
            vo = np.where(mask == 1, np.clip(tot - eff, -MSG, MSG), 0)
            f.write(" ".join(map(str, [init, prior, g8, mp, *mask, *late, *st, bias, mg, int(mg <= 0), *vo])) + "\n")
    print(f"N = {N}: {ncnu} CNU and {nvnu} VNU random vectors written to {out}")


if __name__ == "__main__":
    main()
