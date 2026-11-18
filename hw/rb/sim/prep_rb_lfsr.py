"""Review fixes, part B.3: per-shot inputs and software references for the closed-loop simulation of engine_top_rb in
LFSR mode (gamma lanes drawing from their LFSRs; no g8 loading).

Shots (in this order, one stream, engine reset once before the first shot, as tb_engine_rb without +RESET):
  the 6 golden shots (Test 2a syndromes 96, 106, 53, 5, 141, 1855), then per p = 0.003, 0.002 the first 75 leg-0 and
  all 25 legs-1-3 shots of picks_rb.json (Test 2f picks, Test 1b shots), in index order.
Software reference: the rb13 int4.2.8 decoder (prep_rb.make settings) with explicit_gammas from lfsr_model, starting at
the global draw counter D of the stream; D advances by lfsr_model.draws(iterations) after every shot.
File format: as prep_rb.write (line 1: iterations, success, legs, observables; priors; syndromes; hard decisions +
masks; g8 per leg and home round, here the LFSR model's g8, unused by the engine in LFSR mode).
Usage (from hw/rb/sim, the relay_bp environment): python prep_rb_lfsr.py OUTDIR
"""
import sys, os, json, zlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import prep_rb                                                   # noqa: E402
from prep_rb import problem, regen, hexw, leg_of, NT, NP, NR, GOLDEN, ORDER13, PRE, LEG_IT   # noqa: E402
sys.path.insert(0, os.path.join(HERE, "..", "..", "gen"))
from labels import labels                                        # noqa: E402
import lfsr_model as M                                           # noqa: E402


def main(outdir):
    import relay_bp
    os.makedirs(outdir, exist_ok=True)
    ep = json.load(open(os.path.join(HERE, "..", "..", "..", "results", "test1c", "engine_params.json")))
    picks = json.load(open(os.path.join(HERE, "picks_rb.json")))
    jobs = [("0.003", "golden", s) for s in GOLDEN]
    for p in ("0.003", "0.002"):
        jobs += sorted([(p, "leg0", s) for s in picks[p]["leg0"][:75]] + [(p, "legs1to3", s) for s in picks[p]["legs1to3"]],
                       key=lambda j: j[2])
    T = M.period_table()
    D = 0; index = dict(stream="reset once, then the shots in order", shots=[])
    gs = np.load(os.path.join(HERE, "..", "..", "golden", "syndromes.npz"))["syn"]
    ctx = {}
    for p in ("0.003", "0.002"):
        P = problem(p); L = labels(P, ep); H = P["H"].tocsr()
        O = np.asarray(P["O"].todense() if hasattr(P["O"], "todense") else P["O"]) % 2
        col = {(int(L["col_t"][j]), int(L["col_p"][j]), int(L["col_h"][j])): j for j in range(H.shape[1])}
        llr = np.log((1 - np.asarray(P["priors"], float)) / np.asarray(P["priors"], float))
        pq = np.clip(np.floor(2 * llr + 0.5), -15, 15).astype(int)
        ptab = [[0] * NT for _ in range(NR)]
        for (t, q, h), j in col.items():
            if q == 0: ptab[h][t] = int(pq[j])
        rowpos = {(int(L["row_x"][i]), int(L["row_r"][i])): i for i in range(H.shape[0])}
        _, S = regen(p, [s for pp, k, s in jobs if pp == p and k != "golden"])
        ctx[p] = dict(P=P, O=O, col=col, ptab=ptab, rowpos=rowpos, S=S, lane=(L["col_t"] * M.NP + L["col_p"]).astype(np.int64),
                      home=L["col_h"].astype(int))
    for (p, kind, s) in jobs:
        c = ctx[p]; P = c["P"]
        syn = gs[s] if kind == "golden" else c["S"][s][0]
        G = M.gamma_matrix(T, D, c["lane"], c["home"])
        dec = relay_bp.RelayDecoderF32(P["H"], error_priors=P["priors"], alpha=None, gamma0=0.125, pre_iter=PRE,
                                       num_sets=300, set_max_iter=LEG_IT,
                                       gamma_dist_interval=(-0.22628432386414646, 0.6216020925981884), stop_nconv=1,
                                       seed=0, quant="int4.2.8", check_layers=[ORDER13.index(int(r)) for r in P["layers"]],
                                       explicit_gammas=G)
        r = dec.decode_detailed_batch(syn[None, :])[0]
        d = np.asarray(r.decoding, dtype=np.uint8); it = int(r.iterations)
        assert r.success, (p, kind, s)
        lg = leg_of(it)
        obs_pred = (c["O"].astype(np.int64) @ d.astype(np.int64)) % 2
        name = f"p{p}_{kind}_{s}"
        col = c["col"]
        with open(os.path.join(outdir, f"shot_{name}.txt"), "w") as f:
            f.write(f"{it} 1 {lg + 1} {hexw(obs_pred.tolist())}\n")
            for h in range(NR): f.write(" ".join(str(c["ptab"][h][t]) for t in range(NT)) + "\n")
            for h in range(NR): f.write(hexw([int(syn[c["rowpos"][(x, h)]]) for x in range(NP)]) + "\n")
            for h in range(NR):
                hb = [int(d[col[(t, q, h)]]) if (t, q, h) in col else 0 for t in range(NT) for q in range(NP)]
                pm = [1 if (t, q, h) in col else 0 for t in range(NT) for q in range(NP)]
                f.write(hexw(hb) + " " + hexw(pm) + "\n")
            for leg in range(lg + 1):
                for h in range(NR):
                    bits = []
                    for t in range(NT):
                        for q in range(NP):
                            if (t, q, h) not in col: v = 0
                            elif leg == 0: v = 1
                            else: v = int(round(G[leg][col[(t, q, h)]] * 8))
                            bits += [(v >> k) & 1 for k in range(4)]
                    f.write(hexw(bits) + "\n")
        nd = M.draws(it)
        index["shots"].append(dict(name=name, p=p, kind=kind, shot=s, iterations=it, legs=lg + 1, draw_counter_start=D,
                                   draws=nd, obs=hexw(obs_pred.tolist()), dec_crc=zlib.crc32(np.packbits(d).tobytes())))
        D += nd
        print(name, it, nd, flush=True)
    index["total_draws"] = D
    json.dump(index, open(os.path.join(outdir, "index.json"), "w"), indent=1)
    with open(os.path.join(HERE, "shots_lfsr.txt"), "w") as f:
        for e in index["shots"]: f.write(os.path.join(os.path.basename(outdir), f"shot_{e['name']}.txt") + "\n")


if __name__ == "__main__":
    main(sys.argv[1])
