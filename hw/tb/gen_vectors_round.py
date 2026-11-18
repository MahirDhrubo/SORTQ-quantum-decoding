"""Test 2a stretch: vectors for one full round step (round_step.sv) from the golden dumps.

Replays every (leg, iteration, layer) of the dumped shots with the hardware view of the memories (no clearing at a
leg start), and writes one vector per round step: the inputs exactly as the engine memories hold them at the start
of layer g, and the expected outputs = the golden C and V records of that layer.
Masks (cnu_mask, vmask_cur/prev) are derived from H (12-round circuit, window = whole circuit).
Line (hex fields, packed SystemVerilog order, element [0]..[0] at the LSB):
  g init syn cnu_mask v2c_o0_st v2c_o1_st prior_cur g8_cur mpost_cur c2v_cur_late_st vmask_cur
  prior_prev g8_prev mpost_prev c2v_prev_o0_st vmask_prev
  exp_c2v exp_cur_bias exp_cur_marg exp_cur_hard exp_cur_v2c exp_prev_bias exp_prev_marg exp_prev_hard exp_prev_v2c
  cmp_cur cmp_prev            (cmp = errors updated in this layer; only those VNU outputs are compared)
Also writes <dir of OUT>/prior_table.txt: R + 1 lines (home round h = 0..R), NTYPES decimal priors each (0 where the
type is absent); asserts that every error of (type, h) has that prior (round_step reads priors from a register file).
Usage (hw/tb, relay_dump_venv):
  python gen_vectors_round.py PREFIX NSHOTS OUT [PICK_IDX]
  PICK_IDX: comma-separated index into picks.json for shot file s (default: shot s = picks[s]).
  e.g. python gen_vectors_round.py ../golden/dump_p0.003 3 vectors/round_vectors.txt
       python gen_vectors_round.py ../golden/dump_legs10 1 vectors/round_vectors_legs10.txt 2
"""
import sys, os, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for p in ("../gen", "../golden", "../../scripts"): sys.path.insert(0, os.path.join(HERE, p))
N, MB, MW, NT, NP, NB_, DV = 4, 7, 5, 10, 72, 35, 6


def pack(vals, w):
    v = 0
    for i, x in enumerate(vals):
        v |= (int(x) & ((1 << w) - 1)) << (i * w)
    return format(v, "x")


def sm(x):            # integer -> {sign, mag}
    return ((1 << N) | (-x)) if x < 0 else x


def main():
    prefix, nshots, out = sys.argv[1], int(sys.argv[2]), sys.argv[3]
    pidx = [int(x) for x in sys.argv[4].split(",")] if len(sys.argv) > 4 else list(range(nshots))
    from check_and_vectors import parse
    from golden import problem
    from labels import labels
    ep = json.load(open(os.path.join(HERE, "..", "..", "results", "test1c", "engine_params.json")))
    P = problem(); L = labels(P, ep); H = P["H"].tocsr(); Hc = H.tocsc()
    R = int(L["row_r"].max())
    be = ep["base_edge_table_round5"]; tn = L["tnames"]
    slot = {}
    for t in ep["error_types"]:
        for j, e in enumerate(t["edges"]): slot[(tn.index(t["type"]), e["round_offset"], e["shift_a"], e["shift_b"])] = j
    kslot = {k: slot[(tn.index(e["error_type"]), e["round_offset"], e["shift_a"], e["shift_b"])] for k, e in enumerate(be)}
    idx = {}; c0 = c1 = 0
    for k, e in enumerate(be):
        if e["round_offset"] == 0: idx[k] = c0; c0 += 1
        else: idx[k] = c1; c1 += 1
    NE0, NE1 = c0, c1
    llr = np.log((1 - np.asarray(P["priors"], float)) / np.asarray(P["priors"], float))
    prior_q = np.clip(np.floor(2 * llr + 0.5), -15, 15).astype(int)
    col_of = {(int(L["col_t"][j]), int(L["col_p"][j]), int(L["col_h"][j])): j for j in range(H.shape[1])}
    R0 = int(L["col_h"].max())
    ptab = [[0] * NT for _ in range(R0 + 1)]; nchk = 0
    for (t, p, h), j in col_of.items():
        if p == 0: ptab[h][t] = int(prior_q[j])
    for (t, p, h), j in col_of.items():
        assert int(prior_q[j]) == ptab[h][t], f"prior of (type {t}, pos {p}, home {h}) differs from the table"; nchk += 1
    with open(os.path.join(os.path.dirname(os.path.abspath(out)), "prior_table.txt"), "w") as pf:
        for h in range(R0 + 1): pf.write(" ".join(map(str, ptab[h])) + "\n")
    print(f"prior table: {R0 + 1} home rounds x {NT} types; {nchk} errors checked against it, 0 differ", flush=True)
    row_of = {(int(L["row_x"][i]), int(L["row_r"][i])): i for i in range(H.shape[0])}
    ebase = {}                                                     # (row, col) -> base edge
    for i in range(H.shape[0]):
        for j in H.indices[H.indptr[i]:H.indptr[i + 1]]: ebase[(i, int(j))] = L["edge_base"](i, int(j))
    # masks from H
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
    f = open(out, "w"); nvec = 0
    for s in range(nshots):
        Ld, C, V, I = parse(f"{prefix}_shot{s}.bin")
        syn = np.load(os.path.join(HERE, "..", "golden", "syndromes.npz"))["syn"][
            json.load(open(os.path.join(HERE, "..", "golden", "picks.json")))["picks"][pidx[s]]]
        v2c_h, c2v_h = {}, {}
        marg = Ld[0]["marg"].astype(int).copy()
        layers = {}
        for r in C: layers.setdefault((r[0], r[1], r[2]), [[], []])[0].append(r)
        for r in V: layers.setdefault((r[0], r[1], r[2]), [[], []])[1].append(r)
        for (leg, it, g) in sorted(layers):
            Cs, Vs = layers[(leg, it, g)]
            if g == 0: mstart = marg.copy()
            init = it == 0
            g8 = Ld[leg]["g8"]
            def err(t, p, h): return col_of.get((t, p, h))
            # ---- inputs
            o0 = [0] * (NE0 * NP); o1 = [0] * (NE1 * NP); late = [0] * (NE1 * NP); po0 = [0] * (NE0 * NP)
            for k, e in enumerate(be):
                t = tn.index(e["error_type"])
                for p in range(NP):
                    pa, pb = divmod(p, 6); x = ((pa - e["shift_a"]) % 12) * 6 + (pb - e["shift_b"]) % 6
                    if e["round_offset"] == 0:
                        j = err(t, p, g); i = row_of.get((x, g))
                        if j is not None and i is not None: o0[idx[k] * NP + p] = sm(v2c_h.get((i, j), 0))
                        j = err(t, p, g - 1); i = row_of.get((x, g - 1))
                        if j is not None and i is not None: po0[idx[k] * NP + p] = sm(c2v_h.get((i, j), 0))
                    else:
                        j = err(t, p, g - 1); i = row_of.get((x, g))
                        if j is not None and i is not None: o1[idx[k] * NP + p] = sm(v2c_h.get((i, j), 0))
                        j = err(t, p, g); i = row_of.get((x, g + 1))
                        if j is not None and i is not None: late[idx[k] * NP + p] = sm(c2v_h.get((i, j), 0))
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
            synv = [0] * NP
            for x in range(NP): synv[x] = int(syn[row_of[(x, g)]])
            # ---- expected
            ec2v = [0] * (NP * NB_)
            for (_, _, _, row, sy, e) in Cs:
                x = int(L["row_x"][row])
                for q in range(len(e)):
                    k = ebase[(row, int(e["col"][q]))]
                    ec2v[x * NB_ + k] = (int(e["os"][q]) << N) | int(e["om"][q])
            exp = {gr: dict(bias=[0] * (NT * NP), marg=[0] * (NT * NP), hard=[0] * (NT * NP), v2c=[0] * (NT * NP * DV),
                            cmp=[0] * (NT * NP)) for gr in ("cur", "prev")}
            for (_, _, _, col, prior, gg_, mp_, bias, e, mg, hard) in Vs:
                h = int(L["col_h"][col]); gr = "cur" if h == g else "prev"; assert h in (g, g - 1)
                t, p = int(L["col_t"][col]), int(L["col_p"][col]); q = t * NP + p
                X = exp[gr]; X["bias"][q] = bias; X["marg"][q] = mg; X["hard"][q] = hard; X["cmp"][q] = 1
                for z in range(len(e)):
                    k = ebase[(int(e["row"][z]), col)]
                    X["v2c"][q * DV + kslot[k]] = sm(int(e["v2c"][z]))
            fields = [str(g), str(int(init)), pack(synv, 1), format(cmask[g], "x"), pack(o0, MW), pack(o1, MW),
                      pack(prc, MW), pack(g8c, 4), pack(mpc, MB), pack(late, MW), pack(vmc, DV),
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
        print(f"shot {s} (pick {pidx[s]}): {len(layers)} round steps, legs {legs[0]}..{legs[-1]} "
              f"({len(legs) - 1} leg boundaries), init steps {sum(1 for k in layers if k[1] == 0 and k[0] > 0)} "
              f"after a boundary", flush=True)
    f.close()
    print(f"{nvec} round-step vectors -> {out}")


if __name__ == "__main__":
    main()
