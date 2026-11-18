"""Test 2f: round-step vectors for round_step_rb from the rb13 golden dumps, plus the check of the red-black leg-start
gating rule (D') against every golden input.

Replays every (leg, iteration, layer) of the dumped shots in processing order (layer id = position in ORDER13, round
g = ORDER13[layer]) with the hardware view of the memories:
  - nothing is cleared at a leg start; a message that was never written holds junk (deterministic random value),
  - at decode start the marginal memory holds junk (the engine's M(-1) = L0 path must replace it).
One vector per round step = the inputs exactly as the engine memories hold them + the expected outputs (golden C and V
records of that layer). Line format = Test 2a gen_vectors_round.py with `first` inserted after `init`:
  g init first syn cnu_mask v2c_o0_st v2c_o1_st prior_cur g8_cur mpost_cur c2v_cur_late_st vmask_cur
  prior_prev g8_prev mpost_prev c2v_prev_o0_st vmask_prev
  exp_c2v exp_cur_bias exp_cur_marg exp_cur_hard exp_cur_v2c exp_prev_bias exp_prev_marg exp_prev_hard exp_prev_v2c
  cmp_cur cmp_prev
Check D' (counted; all must be 0 mismatches), gated sets from ../rtl/rb_pkg_report.json (generated from H + order):
  CNU input of edge k at round g:  golden v2c_in == (init and CNU_GATE[pass(g)][k]) ? prior : stored
  VNU input slot s of an error updated in round g, group d: golden c2v_in == (init and VG[pass][d][t][s]) ? 0 : stored
  first iteration of a decode: golden mem_post == prior (M(-1) = L0); every iteration: g8 == L record of the leg.
Usage (hw/rb/tb, relay_dump_venv): python gen_vectors_rb.py PREFIX NSHOTS OUT SHOTS
  SHOTS: comma-separated syndrome indices (../../golden/syndromes.npz) of shot files PREFIX_shot0.bin, ...
"""
import sys, os, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for p in ("../../gen", "../../golden", "../../../scripts"): sys.path.insert(0, os.path.join(HERE, p))
N, MB, MW, NT, NP, NB_, DV = 4, 7, 5, 10, 72, 35, 6
ORDER13 = [0, 2, 4, 6, 8, 10, 12, 1, 3, 5, 7, 9, 11]


def pack(vals, w):
    v = 0
    for i, x in enumerate(vals):
        v |= (int(x) & ((1 << w) - 1)) << (i * w)
    return format(v, "x")


def sm(x):
    return ((1 << N) | (-x)) if x < 0 else x


def main():
    prefix, nshots, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    pidx = [int(x) for x in sys.argv[4].split(",")]
    from check_and_vectors import parse
    from golden import problem
    from labels import labels
    ep = json.load(open(os.path.join(HERE, "..", "..", "..", "results", "test1c", "engine_params.json")))
    rep = json.load(open(os.path.join(HERE, "..", "rtl", "rb_pkg_report.json")))
    P = problem(); L = labels(P, ep); H = P["H"].tocsr(); Hc = H.tocsc()
    R = int(L["row_r"].max())
    be = ep["base_edge_table_round5"]; tn = L["tnames"]
    slot = {}
    for t in ep["error_types"]:
        for j, e in enumerate(t["edges"]): slot[(tn.index(t["type"]), e["round_offset"], e["shift_a"], e["shift_b"])] = j
    kslot = {k: slot[(tn.index(e["error_type"]), e["round_offset"], e["shift_a"], e["shift_b"])] for k, e in enumerate(be)}
    CG = {p: set(rep["cnu_gated"][str(p)]) for p in (0, 1)}
    VG = {}
    for p in (0, 1):
        for d, nm in ((0, "cur"), (1, "prev")):
            VG[(p, d)] = {(tn.index(x.split(".")[0]), int(x.split(".")[1])) for x in rep["vnu_gated"][f"pass{p}_{nm}"]}
    idx = {}; c0 = c1 = 0
    for k, e in enumerate(be):
        if e["round_offset"] == 0: idx[k] = c0; c0 += 1
        else: idx[k] = c1; c1 += 1
    NE0, NE1 = c0, c1
    llr = np.log((1 - np.asarray(P["priors"], float)) / np.asarray(P["priors"], float))
    prior_q = np.clip(np.floor(2 * llr + 0.5), -15, 15).astype(int)
    col_of = {(int(L["col_t"][j]), int(L["col_p"][j]), int(L["col_h"][j])): j for j in range(H.shape[1])}
    R0 = int(L["col_h"].max())
    ptab = [[0] * NT for _ in range(R0 + 1)]
    for (t, p, h), j in col_of.items():
        if p == 0: ptab[h][t] = int(prior_q[j])
    for (t, p, h), j in col_of.items():
        assert int(prior_q[j]) == ptab[h][t]
    with open(os.path.join(os.path.dirname(os.path.abspath(out)), "prior_table.txt"), "w") as pf:
        for h in range(R0 + 1): pf.write(" ".join(map(str, ptab[h])) + "\n")
    row_of = {(int(L["row_x"][i]), int(L["row_r"][i])): i for i in range(H.shape[0])}
    ebase = {}
    for i in range(H.shape[0]):
        for j in H.indices[H.indptr[i]:H.indptr[i + 1]]: ebase[(i, int(j))] = L["edge_base"](i, int(j))
    cmask, vmask = {}, {}
    for g in range(R + 1):
        ks = {frozenset(ebase[(i, int(j))] for j in H.indices[H.indptr[i]:H.indptr[i + 1]]) for i in np.where(L["row_r"] == g)[0]}
        assert len(ks) == 1; cmask[g] = sum(1 << k for k in next(iter(ks)))
    for h in range(R + 1):
        m = [0] * NT
        for t in range(NT):
            sets = set()
            for p in range(NP):
                j = col_of.get((t, p, h))
                if j is None: continue
                sets.add(frozenset(kslot[ebase[(int(i), j)]] for i in Hc.indices[Hc.indptr[j]:Hc.indptr[j + 1]]))
            assert len(sets) <= 1
            if sets: m[t] = sum(1 << s for s in next(iter(sets)))
        vmask[h] = m
    has_o1 = [any(e["round_offset"] == 1 and tn.index(e["error_type"]) == t for e in be) for t in range(NT)]
    D = dict(cnu_inputs=0, cnu_gated=0, cnu_gated_stale_differs=0, cnu_mismatch=0,
             vnu_inputs=0, vnu_gated=0, vnu_gated_stale_differs=0, vnu_mismatch=0,
             first_iter_mpost_checked=0, first_iter_mpost_mismatch=0, g8_mismatch=0, steps=0, init_steps=0,
             leg_starts=0)
    f = open(out, "w"); nvec = 0
    for s in range(nshots):
        Ld, C, V, I = parse(f"{prefix}_shot{s}.bin")
        syn = np.load(os.path.join(HERE, "..", "..", "golden", "syndromes.npz"))["syn"][pidx[s]]
        rng = np.random.default_rng(1000 + s)
        junk_m = {}; junk_c = {}
        def jm(key):           # junk message for a never-written edge (hardware memory content)
            if key not in junk_m: junk_m[key] = int(rng.integers(-15, 16))
            return junk_m[key]
        def jc(key):
            if key not in junk_c: junk_c[key] = int(rng.integers(-15, 16))
            return junk_c[key]
        v2c_h, c2v_h = {}, {}
        marg = rng.integers(-64, 64, H.shape[1]).astype(int)       # junk marginal memory before the decode
        layers = {}
        for r in C: layers.setdefault((r[0], r[1], r[2]), [[], []])[0].append(r)
        for r in V: layers.setdefault((r[0], r[1], r[2]), [[], []])[1].append(r)
        for (leg, it, lay) in sorted(layers):
            Cs, Vs = layers[(leg, it, lay)]
            g = ORDER13[lay]; pas = g % 2
            if lay == 0: mstart = marg.copy()
            init = it == 0; first = init and leg == 0
            D["steps"] += 1; D["init_steps"] += init; D["leg_starts"] += int(init and lay == 0)
            g8 = Ld[leg]["g8"]
            def err(t, p, h): return col_of.get((t, p, h))
            v2c_st = lambda i, j: v2c_h[(i, j)] if (i, j) in v2c_h else jm((i, j))
            c2v_st = lambda i, j: c2v_h[(i, j)] if (i, j) in c2v_h else jc((i, j))
            # ---- inputs (hardware memory contents)
            o0 = [0] * (NE0 * NP); o1 = [0] * (NE1 * NP); late = [0] * (NE1 * NP); po0 = [0] * (NE0 * NP)
            for k, e in enumerate(be):
                t = tn.index(e["error_type"])
                for p in range(NP):
                    pa, pb = divmod(p, 6); x = ((pa - e["shift_a"]) % 12) * 6 + (pb - e["shift_b"]) % 6
                    if e["round_offset"] == 0:
                        j = err(t, p, g); i = row_of.get((x, g))
                        if j is not None and i is not None: o0[idx[k] * NP + p] = sm(v2c_st(i, j))
                        j = err(t, p, g - 1); i = row_of.get((x, g - 1))
                        if j is not None and i is not None: po0[idx[k] * NP + p] = sm(c2v_st(i, j))
                    else:
                        j = err(t, p, g - 1); i = row_of.get((x, g))
                        if j is not None and i is not None: o1[idx[k] * NP + p] = sm(v2c_st(i, j))
                        j = err(t, p, g); i = row_of.get((x, g + 1))
                        if j is not None and i is not None: late[idx[k] * NP + p] = sm(c2v_st(i, j))
            def node_vals(h):
                pr, gg, mp = [0] * (NT * NP), [0] * (NT * NP), [0] * (NT * NP)
                for t in range(NT):
                    for p in range(NP):
                        j = err(t, p, h)
                        if j is not None:
                            pr[t * NP + p] = prior_q[j]; gg[t * NP + p] = g8[j]; mp[t * NP + p] = mstart[j]
                return pr, gg, mp
            prc, g8c, mpc = node_vals(g)
            prp, g8p, mpp = node_vals(g - 1) if g >= 1 else ([0] * (NT * NP),) * 3
            vmc = vmask[g]; vmp = [vmask[g - 1][t] if (g >= 1 and has_o1[t]) else 0 for t in range(NT)]
            synv = [int(syn[row_of[(x, g)]]) for x in range(NP)]
            # ---- check D' and expected outputs
            ec2v = [0] * (NP * NB_)
            for (_, _, _, row, sy, e) in Cs:
                x = int(L["row_x"][row]); assert int(L["row_r"][row]) == g
                for q in range(len(e)):
                    col = int(e["col"][q]); k = ebase[(row, col)]
                    ec2v[x * NB_ + k] = (int(e["os"][q]) << N) | int(e["om"][q])
                    gate = init and (k in CG[pas]); st = v2c_st(row, col)
                    exp_in = int(prior_q[col]) if gate else st
                    D["cnu_inputs"] += 1; D["cnu_gated"] += gate
                    D["cnu_gated_stale_differs"] += int(gate and st != int(e["v2c"][q]))
                    D["cnu_mismatch"] += int(exp_in != int(e["v2c"][q]))
            exp = {gr: dict(bias=[0] * (NT * NP), marg=[0] * (NT * NP), hard=[0] * (NT * NP), v2c=[0] * (NT * NP * DV),
                            cmp=[0] * (NT * NP)) for gr in ("cur", "prev")}
            for (_, _, _, col, prior, gg_, mp_, bias, e, mg, hard) in Vs:
                h = int(L["col_h"][col]); gr = "cur" if h == g else "prev"; assert h in (g, g - 1)
                t, p = int(L["col_t"][col]), int(L["col_p"][col]); q = t * NP + p; d = g - h
                if first:
                    D["first_iter_mpost_checked"] += 1; D["first_iter_mpost_mismatch"] += int(mp_ != prior_q[col])
                D["g8_mismatch"] += int(gg_ != g8[col])
                X = exp[gr]; X["bias"][q] = bias; X["marg"][q] = mg; X["hard"][q] = hard; X["cmp"][q] = 1
                for z in range(len(e)):
                    row = int(e["row"][z]); k = ebase[(row, col)]; sl = kslot[k]
                    X["v2c"][q * DV + sl] = sm(int(e["v2c"][z]))
                    if int(L["row_r"][row]) != g:            # stored input (the other round)
                        gate = init and ((t, sl) in VG[(pas, d)]); st = c2v_st(row, col)
                        exp_in = 0 if gate else st
                        D["vnu_inputs"] += 1; D["vnu_gated"] += gate
                        D["vnu_gated_stale_differs"] += int(gate and st != int(e["c2v"][z]))
                        D["vnu_mismatch"] += int(exp_in != int(e["c2v"][z]))
            mp_first = mpc if not first else mpc        # junk memory content (mstart = junk at decode start)
            fields = [str(g), str(int(init)), str(int(first)), pack(synv, 1), format(cmask[g], "x"), pack(o0, MW),
                      pack(o1, MW), pack(prc, MW), pack(g8c, 4), pack(mp_first, MB), pack(late, MW), pack(vmc, DV),
                      pack(prp, MW), pack(g8p, 4), pack(mpp, MB), pack(po0, MW), pack(vmp, DV), pack(ec2v, MW)]
            for gr in ("cur", "prev"):
                X = exp[gr]
                fields += [pack(X["bias"], MB), pack(X["marg"], MB), pack(X["hard"], 1), pack(X["v2c"], MW)]
            fields += [pack(exp["cur"]["cmp"], 1), pack(exp["prev"]["cmp"], 1)]
            f.write(" ".join(fields) + "\n"); nvec += 1
            # ---- advance the hardware state with the golden outputs of this layer
            for (_, _, _, row, sy, e) in Cs:
                for q in range(len(e)):
                    c2v_h[(row, int(e["col"][q]))] = -int(e["om"][q]) if e["os"][q] else int(e["om"][q])
            for (_, _, _, col, prior, gg_, mp_, bias, e, mg, hard) in Vs:
                for z in range(len(e)): v2c_h[(int(e["row"][z]), col)] = int(e["v2c"][z])
                marg[col] = mg
        legs = sorted({k[0] for k in layers})
        print(f"shot file {s} (syndrome {pidx[s]}): {len(layers)} round steps, legs {legs[0]}..{legs[-1]}", flush=True)
    f.close()
    print("D':", json.dumps(D))
    json.dump(D, open(out + ".check.json", "w"), indent=1)
    print(f"{nvec} round-step vectors -> {out}")


if __name__ == "__main__":
    main()
