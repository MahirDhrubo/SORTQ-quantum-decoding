"""Test 2a, Step 0/4: parse the golden dumps, check them against ARITHMETIC.md (independent numpy model), check the
state-ordering / leg-start gating rule, and write test vectors for the cnu / vnu testbenches.

Usage (from hw/golden, relay_dump_venv python): python check_and_vectors.py dump_p0.003 3 [vecdir [PICK_IDX]]
  PICK_IDX: comma-separated index into picks.json for shot file s (default picks[s]); when given, the report is
  check_report_<prefix>.json instead of check_report.json (e.g. dump_legs10 1 /tmp/vec 2).

Checks (all counted, all must be 0 mismatches):
  A  CNU arithmetic: c2v_out (sign, mag) from v2c_in and syndrome (min1/min2, sign parity, saturation)
  B  VNU arithmetic: bias, marginal, v2c_out, hard decision from prior, g8, mem_post, c2v_in
  C  ordering: every CNU input v2c = latest v2c written for that edge (prior at a leg start);
     every VNU input c2v = latest c2v written (0 at a leg start); mem_post = marginal at the end of the previous
     iteration; g8 = the leg's g8 (L record); hard decisions at iteration end = 'I' record.
  D  leg-start gating (hardware view, memories are NOT cleared): golden input == (init and stale ? reset : stored),
     stale for CNU = edge to an error of the same home round as the check (offset 0),
     stale for VNU = edge to a check of round home + 1 while the error is updated in layer = home.
Vectors (decimal text, one record per line, see ../tb/README.md):
  cnu_vectors.txt : syn  mask[35]  in_sign[35] in_mag[35]  out_sign[35] out_mag[35]
                    (inputs as seen by the CNU, i.e. after the leg-start mux; invalid slots get random junk)
  vnu_vectors.txt : init prior g8 mpost  mask[6] late[6] c2v_stored[6]  bias marg hard v2c_out[6]
                    (c2v_stored = hardware memory content; the VNU must gate stale ones to 0 when init = 1)
"""
import sys, os, json, struct
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MSG, MMIN, MMAX, DEN = 15, -64, 63, 8
DEG_C, DEG_V = 35, 6


def parse(path):
    b = open(path, "rb").read(); n = len(b); p = 0
    L, C, V, I = {}, [], [], []
    u32 = lambda q: struct.unpack_from("<I", b, q)[0]
    while p < n:
        t = b[p]; p += 1
        if t == ord("L"):
            leg, nc = u32(p), u32(p + 4); p += 8
            g8 = np.frombuffer(b, np.int8, nc, p).copy(); p += nc
            mg = np.frombuffer(b, np.int8, nc, p).copy(); p += nc
            L[leg] = dict(g8=g8, marg=mg)
        elif t == ord("C"):
            leg, it, lay, row = struct.unpack_from("<IIII", b, p); p += 16
            syn, deg = b[p], b[p + 1]; p += 2
            e = np.frombuffer(b, np.dtype([("col", "<u4"), ("v2c", "i1"), ("neg", "u1"), ("os", "u1"), ("om", "i1")]), deg, p).copy()
            p += 8 * deg
            C.append((leg, it, lay, row, syn, e))
        elif t == ord("V"):
            leg, it, lay, col = struct.unpack_from("<IIII", b, p); p += 16
            prior, g8, mp, bias = struct.unpack_from("<bbbb", b, p); p += 4
            deg = b[p]; p += 1
            e = np.frombuffer(b, np.dtype([("row", "<u4"), ("c2v", "i1"), ("sb", "u1"), ("v2c", "i1")]), deg, p).copy()
            p += 7 * deg
            marg, hard = struct.unpack_from("<bB", b, p); p += 2
            V.append((leg, it, lay, col, prior, g8, mp, bias, e, marg, hard))
        elif t == ord("I"):
            leg, it = u32(p), u32(p + 4); conv = b[p + 8]; nc = u32(p + 9); p += 13
            hd = np.frombuffer(b, np.uint8, nc, p).copy(); p += nc
            I.append((leg, it, conv, hd))
        else:
            raise ValueError(f"bad record tag {t} at {p - 1}")
    return L, C, V, I


def rnd8(x):                      # round(x / 8) with round(y) = floor(y + 1/2), exact for integers
    return (x + 4) >> 3


def main():
    prefix, nshots = sys.argv[1], int(sys.argv[2])
    vec = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "..", "tb", "vectors")
    pidx = [int(x) for x in sys.argv[4].split(",")] if len(sys.argv) > 4 else list(range(nshots))
    report = f"check_report_{os.path.basename(prefix)}.json" if len(sys.argv) > 4 else "check_report.json"
    os.makedirs(vec, exist_ok=True)
    from golden import problem
    P = problem(); H = P["H"].tocsr(); layers = np.asarray(P["layers"]); Hc = H.tocsc()
    home = np.array([layers[Hc.indices[Hc.indptr[c]:Hc.indptr[c + 1]]].min() for c in range(H.shape[1])])
    llr = np.log((1 - np.asarray(P["priors"], float)) / np.asarray(P["priors"], float))
    prior_q = np.clip(np.floor(2 * llr + 0.5), -MSG, MSG).astype(int)    # ARITHMETIC.md: round(2*LLR), saturated
    rng = np.random.default_rng(1)
    cnt = {k: 0 for k in ("A_records", "A_edges", "A_mismatch", "B_records", "B_mismatch",
                          "C_cnu_in_mismatch", "C_vnu_in_mismatch", "C_mempost_mismatch", "C_g8_mismatch",
                          "C_hard_mismatch", "C_conv_mismatch", "C_prior_mismatch", "D_cnu_mismatch", "D_vnu_mismatch",
                          "D_cnu_stale_edges", "D_vnu_stale_edges", "D_vnu_stale_nonzero_stored",
                          "D_cnu_stale_differs", "v2c_in_negative_zero", "c2v_out_negative_zero",
                          "iterations", "legs")}
    hist = dict(c2v_mag=np.zeros(16, int), v2c=np.zeros(31, int), bias=np.zeros(128, int), marg=np.zeros(128, int))
    g8_leg = {}
    fc = open(os.path.join(vec, "cnu_vectors.txt"), "w"); fv = open(os.path.join(vec, "vnu_vectors.txt"), "w")
    per_shot = []
    for s in range(nshots):
        L, C, V, I = parse(f"{prefix}_shot{s}.bin")
        res = np.load(f"{prefix}_res.npz")
        ncols = H.shape[1]
        # golden state (reset at leg start) and hardware state (never reset, except power-up = 0)
        v2c_g, c2v_g, v2c_h, c2v_h = {}, {}, {}, {}
        marg = np.zeros(ncols, int); marg_iter_start = None
        cur = (-1, -1)
        ci = vi = ii = 0
        # merge records in file order: rebuild order from (leg, it, layer) and type; file order is C... V... per layer
        # (we parse into separate lists but they are in file order within each list, and per layer C precede V)
        events = [(r[0], r[1], r[2], 0, k) for k, r in enumerate(C)] + [(r[0], r[1], r[2], 1, k) for k, r in enumerate(V)]
        events.sort(key=lambda x: (x[0], x[1], x[2], x[3], x[4]))
        n_it = len(I); cnt["iterations"] += n_it; cnt["legs"] += len(L)
        for leg in L:
            g8_leg.setdefault(leg, []).append(L[leg]["g8"])
        Iix = {(r[0], r[1]): r for r in I}
        for (leg, it, lay, typ, k) in events:
            if (leg, it) != cur:
                if cur != (-1, -1):         # end of previous iteration: compare hard decisions with 'I'
                    hd = (marg <= 0).astype(np.uint8)
                    cnt["C_hard_mismatch"] += int(np.sum(hd != Iix[cur][3]))
                if it == 0:                 # leg start: golden resets messages, keeps marginals
                    v2c_g, c2v_g = {}, {}
                    if leg == 0:
                        marg = L[0]["marg"].astype(int).copy()
                    cnt["C_mempost_mismatch"] += int(np.sum(L[leg]["marg"] != marg))
                marg_iter_start = marg.copy(); cur = (leg, it)
            init = it == 0
            if typ == 0:
                _, _, _, row, syn, e = C[k]
                cols = e["col"].astype(int); v = e["v2c"].astype(int); neg = e["neg"].astype(int)
                # A: arithmetic
                mag = np.abs(v); s_all = (syn + neg.sum()) & 1
                m1 = mag.min(); m2 = np.partition(mag, 1)[1] if len(mag) > 1 else 127
                om = np.minimum(np.where(mag == m1, m2, m1), MSG); os_ = s_all ^ neg
                cnt["A_records"] += 1; cnt["A_edges"] += len(v)
                cnt["A_mismatch"] += int(np.sum((om != e["om"]) | (os_ != e["os"])))
                cnt["v2c_in_negative_zero"] += int(np.sum((v == 0) & (neg == 1)))
                cnt["c2v_out_negative_zero"] += int(np.sum((e["om"] == 0) & (e["os"] == 1)))
                np.add.at(hist["c2v_mag"], e["om"].astype(int), 1)
                # C / D: ordering and gating
                for j, c in enumerate(cols):
                    key = (row, int(c)); gold = int(v[j])
                    stale = init and home[c] == lay
                    if v2c_g.get(key, int(prior_q[c])) != gold:          # C: golden state (reset to prior)
                        cnt["C_cnu_in_mismatch"] += 1
                    d_exp = int(prior_q[c]) if stale else v2c_h.get(key, 0)   # D: hardware view + leg-start mux
                    if d_exp != gold:
                        cnt["D_cnu_mismatch"] += 1
                    if stale:
                        cnt["D_cnu_stale_edges"] += 1
                        cnt["D_cnu_stale_differs"] += int(v2c_h.get(key, 0) != gold)
                # write
                for j, c in enumerate(cols):
                    val = -int(e["om"][j]) if e["os"][j] else int(e["om"][j])
                    c2v_g[(row, int(c))] = val; c2v_h[(row, int(c))] = val
                # vector
                mask = np.zeros(DEG_C, int); isg = rng.integers(0, 2, DEG_C); imag = rng.integers(0, 16, DEG_C)
                osg = np.zeros(DEG_C, int); omg = np.zeros(DEG_C, int)
                d = len(v); mask[:d] = 1; isg[:d] = neg; imag[:d] = mag; osg[:d] = e["os"]; omg[:d] = e["om"]
                fc.write(" ".join(map(str, [syn, *mask, *isg, *imag, *osg, *omg])) + "\n")
            else:
                _, _, _, col, prior, g8, mp, bias, e, mg, hard = V[k]
                rows = e["row"].astype(int); cin = e["c2v"].astype(int)
                cnt["C_prior_mismatch"] += int(prior != prior_q[col])
                # B: arithmetic
                b_exp = min(max(rnd8((DEN - g8) * prior + g8 * mp), MMIN), MMAX)
                tot = b_exp + cin.sum()
                m_exp = min(max(tot, MMIN), MMAX)
                v_exp = np.clip(tot - cin, -MSG, MSG)
                h_exp = int(m_exp <= 0)
                cnt["B_records"] += 1
                bad = (b_exp != bias) or (m_exp != mg) or (h_exp != hard) or bool(np.any(v_exp != e["v2c"]))
                cnt["B_mismatch"] += int(bad)
                hist["bias"][bias + 64] += 1; hist["marg"][mg + 64] += 1
                np.add.at(hist["v2c"], e["v2c"].astype(int) + 15, 1)
                # C: inputs
                if g8 != L[leg]["g8"][col]:
                    cnt["C_g8_mismatch"] += 1
                if mp != marg_iter_start[col]:
                    cnt["C_mempost_mismatch"] += 1
                late = np.array([1 if (layers[r] == home[col] + 1 and lay == home[col]) else 0 for r in rows])
                stored = np.array([c2v_h.get((int(r), col), 0) for r in rows])
                for j, r in enumerate(rows):
                    g_exp = c2v_g.get((int(r), col), 0)
                    if g_exp != cin[j]:
                        cnt["C_vnu_in_mismatch"] += 1
                    d_exp = 0 if (init and late[j]) else stored[j]
                    if d_exp != cin[j]:
                        cnt["D_vnu_mismatch"] += 1
                    if init and late[j]:
                        cnt["D_vnu_stale_edges"] += 1
                        cnt["D_vnu_stale_nonzero_stored"] += int(stored[j] != 0)
                # write
                for j, r in enumerate(rows):
                    v2c_g[(int(r), col)] = int(e["v2c"][j]); v2c_h[(int(r), col)] = int(e["v2c"][j])
                marg[col] = mg
                d = len(rows); mask = np.zeros(DEG_V, int); lt = np.zeros(DEG_V, int)
                st = rng.integers(-MSG, MSG + 1, DEG_V); vo = np.zeros(DEG_V, int)
                mask[:d] = 1; lt[:d] = late; st[:d] = stored; vo[:d] = e["v2c"]
                fv.write(" ".join(map(str, [int(init), prior, g8, mp, *mask, *lt, *st, bias, mg, hard, *vo])) + "\n")
        hd = (marg <= 0).astype(np.uint8); cnt["C_hard_mismatch"] += int(np.sum(hd != Iix[cur][3]))
        # convergence flag from I records vs H * hard == syndrome
        syn_all = np.load("syndromes.npz")["syn"][json.load(open("picks.json"))["picks"][pidx[s]]]
        for (leg, it, conv, hdv) in I:
            ok = bool(np.all((H @ hdv.astype(int)) % 2 == syn_all))
            cnt["C_conv_mismatch"] += int(ok != bool(conv))
        last = I[-1]
        per_shot.append(dict(shot=s, iterations=len(I), legs=len(L), records_C=len(C), records_V=len(V),
                             last_iteration_converged=bool(last[2]), result_iterations=int(res["iterations"][s])))
        print(json.dumps(per_shot[-1]), flush=True)
    fc.close(); fv.close()
    out = dict(counts=cnt, shots=per_shot,
               g8_sets={str(l): {str(int(v)): int(c) for v, c in zip(*np.unique(np.concatenate(g), return_counts=True))}
                        for l, g in g8_leg.items()},
               g8_identical_across_shots={str(l): bool(all(np.array_equal(g[0], x) for x in g)) for l, g in g8_leg.items()},
               hist={k: v.tolist() for k, v in hist.items()})
    json.dump(out, open(report, "w"), indent=1)
    print(json.dumps(out["counts"], indent=1)); print("g8 sets:", out["g8_sets"], out["g8_identical_across_shots"])


if __name__ == "__main__":
    main()
