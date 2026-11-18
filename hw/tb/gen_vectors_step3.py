"""Test 2a, Step 4: vectors for conv_check, ctrl (masks) and commit, from the 36-round circuit's H and O
(expectations computed from the matrices, not from the RTL tables). Window W = 12, C = 8, R = 36; windows
t = 0 (global first round), 8, 24 (bulk) and 32 (last window: rounds 32..36).

Bit vectors are written as hex of the packed SystemVerilog vector (bit 0 = LSB):
  hard[W][NTYPES][NPOS]: bit (i * 10 + type) * 72 + pos  — error homed in window round i
  syn / unsat[W][NPOS]:  bit i * 72 + x
  emask[W][NBASE]:       bit i * 35 + k
Files (vectors/):
  conv_vectors.txt   : t hard syn emask conv unsat        (100 vectors per window: half consistent, half with flips;
                       slots without an error (absent types, rounds > R) hold random junk that the masks must hide)
  ctrl_expected.txt  : t g cnu_mask vnu_cur vnu_prev prev_active   (vnu bit = type * 6 + slot)
  commit_vectors.txt : t nrounds carry_en, then per committed round: types_present hard[NTYPES][NPOS]
                       (absent types hold junk); then obs syn_corr
Usage: python gen_vectors_step3.py <circuit36.stim> <engine_params.json> <outdir>
"""
import sys, os, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "gen")); sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
W, C, NT, NP, NB_ = 12, 8, 10, 72, 35


def hexv(bits):
    v = 0
    for b in bits: v |= 1 << int(b)
    return format(v, "x")


def main():
    circ, epf, out = sys.argv[1:4]
    from dem_tools import xdecoder_problem
    from labels import labels
    ep = json.load(open(epf)); P = xdecoder_problem(circ); L = labels(P, ep)
    H = P["H"].tocsr(); Hc = H.tocsc(); O = P["O"]; O = np.asarray(O.todense() if hasattr(O, "todense") else O).astype(np.uint8)
    R = int(L["row_r"].max())
    assert R == 36
    rng = np.random.default_rng(20261113)
    be = ep["base_edge_table_round5"]; tn = L["tnames"]
    ts = {}  # (type, offset, sa, sb) -> slot
    for t in ep["error_types"]:
        for j, e in enumerate(t["edges"]): ts[(tn.index(t["type"]), e["round_offset"], e["shift_a"], e["shift_b"])] = j
    ncol = H.shape[1]
    fconv = open(os.path.join(out, "conv_vectors.txt"), "w")
    fctrl = open(os.path.join(out, "ctrl_expected.txt"), "w")
    fcom = open(os.path.join(out, "commit_vectors.txt"), "w")
    for t in (0, 8, 24, 32):
        rows_w = np.where((L["row_r"] >= t) & (L["row_r"] < t + W))[0]
        cols_w = np.where((L["col_h"] >= t) & (L["col_h"] < t + W))[0]
        Hw = H[rows_w][:, cols_w].tocsr()
        # ---- masks from H (all checks of a round must agree)
        emask_bits = []
        for g in range(t, min(t + W, R + 1)):
            i = g - t
            sets = set()
            for r in np.where(L["row_r"] == g)[0]:
                ks = frozenset(L["edge_base"](r, j) for j in H.indices[H.indptr[r]:H.indptr[r + 1]]
                               if t <= L["col_h"][j] < t + W)
                sets.add(ks)
            assert len(sets) == 1, f"round {g}: checks disagree on the base-edge set"
            ks = next(iter(sets))
            emask_bits += [i * NB_ + k for k in ks]
            # VNU slot masks: errors homed g (cur) and g - 1 (prev, if in window), updated in layer g
            def vmask(h):
                per = {}                             # (type) -> set of slot sets over all 72 positions
                for j in np.where(L["col_h"] == h)[0]:
                    rws = [r for r in Hc.indices[Hc.indptr[j]:Hc.indptr[j + 1]] if t <= L["row_r"][r] < t + W]
                    if not any(L["row_r"][r] == g for r in rws):
                        continue                     # this error is not updated in layer g
                    tt = int(L["col_t"][j]); sl = set()
                    for r in rws:
                        e = be[L["edge_base"](r, j)]
                        sl.add(ts[(tt, e["round_offset"], e["shift_a"], e["shift_b"])])
                    per.setdefault(tt, set()).add(frozenset(sl))
                bits = set()
                for tt, v in per.items():
                    assert len(v) == 1, f"home {h} type {tt}: positions disagree on the slot set"
                    bits |= {tt * 6 + j for j in next(iter(v))}
                return bits, set(per)
            vc, _ = vmask(g)
            vp, _ = vmask(g - 1) if g - 1 >= t else (set(), set())
            km = sum(1 << k for k in ks)
            fctrl.write(f"{t} {g} {km:x} {hexv(vc)} {hexv(vp)} {int(g - 1 >= t)}\n")
        # ---- conv_check vectors
        real = {((L["col_h"][c] - t) * NT + L["col_t"][c]) * NP + L["col_p"][c] for c in cols_w}
        junk_slots = [q for q in range(W * NT * NP) if q not in real]
        for n in range(100):
            e = (rng.random(len(cols_w)) < 0.01).astype(np.uint8)
            s = (Hw @ e) % 2
            flips = []
            if n % 2:
                flips = rng.choice(len(rows_w), size=int(rng.integers(1, 4)), replace=False); s = s.copy(); s[flips] ^= 1
            hard_bits = [((L["col_h"][c] - t) * NT + L["col_t"][c]) * NP + L["col_p"][c] for c, v in zip(cols_w, e) if v]
            # junk in slots with no error (absent boundary types, rounds beyond R): the edge masks must hide it
            hard_bits += [s_ for s_ in junk_slots if rng.random() < 0.5]
            syn_bits = [(L["row_r"][r] - t) * NP + L["row_x"][r] for r, v in zip(rows_w, s) if v]
            uns = (Hw @ e + s) % 2
            uns_bits = [(L["row_r"][r] - t) * NP + L["row_x"][r] for r, v in zip(rows_w, uns) if v]
            fconv.write(f"{t} {hexv(hard_bits)} {hexv(syn_bits)} {hexv(emask_bits)} {int(len(uns_bits) == 0)} {hexv(uns_bits)}\n")
        # ---- commit vectors: commit homes [t, t + C) (last window: everything left)
        last_win = t + W >= R + 1
        homes = list(range(t, R + 1)) if last_win else list(range(t, t + C))
        carry = (not last_win) and (t + C <= R)
        for n in range(20):
            cols_c = np.where(np.isin(L["col_h"], homes))[0]
            e = (rng.random(len(cols_c)) < 0.02).astype(np.uint8)
            obs = (O[:, cols_c] @ e) % 2
            obs_v = sum(int(b) << q for q, b in enumerate(obs))
            sc = []
            if carry:
                rows_n = np.where(L["row_r"] == t + C)[0]
                s = (H[rows_n][:, cols_c] @ e) % 2
                sc = [L["row_x"][r] for r, v in zip(rows_n, s) if v]
            fcom.write(f"{t} {len(homes)} {int(carry)}")
            for h in homes:
                hb = [L["col_t"][c] * NP + L["col_p"][c] for c, v in zip(cols_c, e) if v and L["col_h"][c] == h]
                present = sorted(set(int(x) for x in L["col_t"][L["col_h"] == h]))
                tp = sum(1 << x for x in present)
                hb += [x * NP + p for x in range(NT) if x not in present for p in range(NP) if rng.random() < 0.5]  # junk
                fcom.write(f" {tp:x} {hexv(hb) if hb else '0'}")
            fcom.write(f" {obs_v:x} {hexv(sc) if sc else '0'}\n")
        print(f"window t = {t}: rows {len(rows_w)}, cols {len(cols_w)}, rounds {min(t + W, R + 1) - t}, "
              f"commit homes {homes[0]}..{homes[-1]} carry {carry}", flush=True)
    for f in (fconv, fctrl, fcom): f.close()


if __name__ == "__main__":
    main()
