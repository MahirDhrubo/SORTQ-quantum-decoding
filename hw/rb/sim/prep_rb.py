"""Test 2f: inputs and software references for the closed-loop simulation of engine_top_rb (Test 3d set-up, rb order).

Problem: one window W = 13 rounds (win_t = 0, last_r = 12) = the whole 12-round circuit, commit over C = 13 rounds.
Software reference: relay_bp int4.2.8 with the rb13 layer order (golden_rb.make; Test 1g schedule (2)), each shot
decoded alone: iterations, success, full decoding, 12 observables.
g8 per leg (LOAD mode): from the 'L' records of all dumps given (Test 2a sweep dumps and Test 2f rb dumps); asserted
identical wherever two dumps contain the same leg (so g8 depends neither on the shot nor on the layer order).
Shots:
  golden: Test 2a syndromes (p = 0.003, seed 20261113) 96, 106, 53 (the 3 Test 2a picks) and 5, 141, 1855 (rb leg
          coverage: legs 1, 1 and 9)
  random: Test 1g rb13 traces (Test 1b shots, sampler seed 20261111), first 40,000 shots per p; N0 converging in leg 0
          and NL in legs 1-3, drawn with numpy seed SEED; the software iterations are checked against the trace.
Modes (from hw/rb/sim, the relay_bp environment):
  pick OUT.json [N0 NL SEED]
  write OUTDIR PICKS.json DUMPS...
"""
import sys, os, json, zlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
S3D = os.path.join(HERE, "..", "..", "sim3d")
sys.path.insert(0, S3D); sys.path.insert(0, os.path.join(HERE, "..", "golden"))
import prep_3d                                                  # noqa: E402  (problem, regen, scan_L, hexw)
from prep_3d import problem, regen, scan_L, hexw, leg_of, NT, NP, NR, PRE, LEG_IT   # noqa: E402
R1G = os.path.join(HERE, "..", "..", "..", "results", "test1g")
GOLDEN = (96, 106, 53, 5, 141, 1855)
ORDER13 = [0, 2, 4, 6, 8, 10, 12, 1, 3, 5, 7, 9, 11]


def make(P):
    import relay_bp
    return relay_bp.RelayDecoderF32(P["H"], error_priors=P["priors"], alpha=None, gamma0=0.125, pre_iter=PRE,
                                    num_sets=300, set_max_iter=LEG_IT,
                                    gamma_dist_interval=(-0.22628432386414646, 0.6216020925981884), stop_nconv=1,
                                    seed=0, quant="int4.2.8", check_layers=[ORDER13.index(int(r)) for r in P["layers"]])


def pick(out, n0=225, nl=25, seed=20261116):
    rng = np.random.default_rng(seed); res = {}
    for p in ("0.003", "0.002"):
        d = np.load(os.path.join(R1G, f"p{p}_rb13.npz")); it, ok = d["iterations"], d["success"]
        lim = 40000; idx = np.arange(lim)
        a = idx[ok[:lim] & (it[:lim] <= PRE)]
        b = idx[ok[:lim] & (it[:lim] > PRE) & (it[:lim] <= PRE + 3 * LEG_IT)]
        sa = sorted(rng.choice(a, n0, replace=False).tolist()); sb = sorted(rng.choice(b, min(nl, len(b)), replace=False).tolist())
        res[p] = dict(leg0=sa, legs1to3=sb, pool_leg0=int(len(a)), pool_legs1to3=int(len(b)),
                      trace_iterations={int(i): int(it[i]) for i in sa + sb})
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps({p: {k: v for k, v in r.items() if k != "trace_iterations"} for p, r in res.items()}, indent=1))


def write(outdir, picks_json, dumps):
    from labels import labels
    os.makedirs(outdir, exist_ok=True)
    ep = json.load(open(os.path.join(HERE, "..", "..", "..", "results", "test1c", "engine_params.json")))
    G = {}; agree = {}
    for f in dumps:
        for leg, v in scan_L(f).items():
            if leg in G:
                same = bool(np.array_equal(G[leg], v)); agree.setdefault(leg, []).append((os.path.basename(f), same))
                assert same, f"g8 of leg {leg} differs in {f}"
            else:
                G[leg] = v; agree.setdefault(leg, []).append((os.path.basename(f), "first"))
    assert np.all(G[0] == 1)
    picks = json.load(open(picks_json))
    index = dict(g8_legs=sorted(G), g8_agreement={str(k): v for k, v in agree.items()}, shots=[])
    jobs = [("0.003", "golden", s) for s in GOLDEN]
    for p in ("0.003", "0.002"):
        jobs += [(p, "leg0", s) for s in picks[p]["leg0"]] + [(p, "legs1to3", s) for s in picks[p]["legs1to3"]]
    for p in ("0.003", "0.002"):
        P = problem(p); L = labels(P, ep); H = P["H"].tocsr()
        O = np.asarray(P["O"].todense() if hasattr(P["O"], "todense") else P["O"]) % 2
        col = {(int(L["col_t"][j]), int(L["col_p"][j]), int(L["col_h"][j])): j for j in range(H.shape[1])}
        llr = np.log((1 - np.asarray(P["priors"], float)) / np.asarray(P["priors"], float))
        pq = np.clip(np.floor(2 * llr + 0.5), -15, 15).astype(int)
        ptab = [[0] * NT for _ in range(NR)]
        for (t, q, h), j in col.items():
            if q == 0: ptab[h][t] = int(pq[j])
        for (t, q, h), j in col.items():
            assert int(pq[j]) == ptab[h][t]
        rowpos = {(int(L["row_x"][i]), int(L["row_r"][i])): i for i in range(H.shape[0])}
        mine = [j for j in jobs if j[0] == p]
        gs = np.load(os.path.join(HERE, "..", "..", "golden", "syndromes.npz"))["syn"] if p == "0.003" else None
        rnd = [s for _, k, s in mine if k != "golden"]
        _, S = regen(p, rnd)
        dec = make(P)
        for (_, kind, s) in mine:
            syn = gs[s] if kind == "golden" else S[s][0]
            r = dec.decode_detailed_batch(syn[None, :])[0]
            d = np.asarray(r.decoding, dtype=np.uint8); it = int(r.iterations)
            assert r.success, (p, kind, s)
            lg = leg_of(it)
            assert lg in G, f"no g8 vector for leg {lg}"
            obs_pred = (O.astype(np.int64) @ d.astype(np.int64)) % 2
            name = f"p{p}_{kind}_{s}"
            with open(os.path.join(outdir, f"shot_{name}.txt"), "w") as f:
                f.write(f"{it} {int(bool(r.success))} {lg + 1} {hexw(obs_pred.tolist())}\n")
                for h in range(NR): f.write(" ".join(str(ptab[h][t]) for t in range(NT)) + "\n")
                for h in range(NR):
                    f.write(hexw([int(syn[rowpos[(x, h)]]) for x in range(NP)]) + "\n")
                for h in range(NR):
                    hb = [int(d[col[(t, q, h)]]) if (t, q, h) in col else 0 for t in range(NT) for q in range(NP)]
                    pm = [1 if (t, q, h) in col else 0 for t in range(NT) for q in range(NP)]
                    f.write(hexw(hb) + " " + hexw(pm) + "\n")
                for leg in range(lg + 1):
                    for h in range(NR):
                        bits = []
                        for t in range(NT):
                            for q in range(NP):
                                v = int(G[leg][col[(t, q, h)]]) if (t, q, h) in col else 0
                                bits += [(v >> k) & 1 for k in range(4)]
                        f.write(hexw(bits) + "\n")
            tr = picks[p]["trace_iterations"][str(s)] if kind != "golden" else None
            if tr is not None: assert tr == it, f"{name}: software {it} != Test 1g trace {tr}"
            index["shots"].append(dict(name=name, p=p, kind=kind, shot=s, iterations=it, legs=lg + 1,
                                       converged_leg0=bool(it <= PRE), trace_iterations=tr,
                                       obs=hexw(obs_pred.tolist()), dec_crc=zlib.crc32(np.packbits(d).tobytes())))
            print(name, it, flush=True)
    json.dump(index, open(os.path.join(outdir, "index.json"), "w"), indent=1)


if __name__ == "__main__":
    m = sys.argv[1]
    if m == "pick": pick(sys.argv[2], *map(int, sys.argv[3:6])) if len(sys.argv) > 3 else pick(sys.argv[2])
    elif m == "write": write(sys.argv[2], sys.argv[3], sys.argv[4:])
