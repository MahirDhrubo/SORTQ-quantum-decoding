"""Test 3d (reduced): inputs and software references for the closed-loop simulation of engine_top_pf2.

Problem the engine implements here: one window of W = 13 rounds (win_t = 0, last_r = 12) = the whole 12-round
circuit (13 detector rounds 0..12), i.e. exactly the Test 1b X-decoder problem; commit over C = 13 rounds (no carry).
Software reference: relay_bp int4.2.8 round sweep (Test 1b settings, golden.make), each shot decoded alone.

g8 per leg (LOAD mode): the decoder re-seeds its gamma RNG (seed 0) at every decode, so every shot uses the same g8
vector per leg (ARITHMETIC.md section 5). The vectors are taken from the 'L' records of the golden dumps and checked
to be identical across all dumps that contain the same leg (the p = 0.002 dump made here included).
Priors: prior_q = clip(floor(2 * LLR + 0.5), -15, 15) per error (as gen_vectors_round.py), one value per (type, home
round), asserted for every error.

Modes (run from hw/sim3d with the relay_bp environment; dump mode with the relay_bp environment (dump build)):
  pick  OUT.json                choose the random shots from the Test 1b traces
  dump2 OUT.bin                 RELAY_DUMP one p = 0.002 shot that reaches leg 1 (g8 check across p)
  write OUTDIR PICKS.json DUMPS...   per-shot input files shot_<name>.txt + index.json (decodes in software)
"""
import sys, os, json, struct, zlib
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "golden")); sys.path.insert(0, os.path.join(HERE, "..", "gen"))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
CDIR = os.path.join(HERE, "..", "..", "circuits", "bb_ibm")
def circ(p):
    return os.path.join(CDIR, f"circuit=bicycle_bivariate_144_12_12_memory_Z,distance=12,rounds=12,error_rate={p},"
                              "noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim")
R1B = os.path.join(HERE, "..", "..", "results", "test1b")
BATCH = {"0.003": 4000, "0.002": 8000}           # Test 1b batch x workers (500 x 8, 1000 x 8)
PRE, LEG_IT = 80, 60
NT, NP, NR = 10, 72, 13


def problem(p):
    from dem_tools import xdecoder_problem
    return xdecoder_problem(circ(p))


def make(P):
    import relay_bp
    return relay_bp.RelayDecoderF32(P["H"], error_priors=P["priors"], alpha=None, gamma0=0.125, pre_iter=PRE,
                                    num_sets=300, set_max_iter=LEG_IT,
                                    gamma_dist_interval=(-0.22628432386414646, 0.6216020925981884), stop_nconv=1,
                                    seed=0, quant="int4.2.8", check_layers=[int(x) for x in P["layers"]])


def leg_of(it):
    return 0 if it <= PRE else 1 + (it - PRE - 1) // LEG_IT


def pick(out, n0=45, nl=5, seed=20261114, exclude=None):
    rng = np.random.default_rng(seed)
    res = {}
    ex = json.load(open(exclude)) if exclude else {}
    for p in ("0.003", "0.002"):
        d = np.load(os.path.join(R1B, f"p{p}_int4.2.8_sweep.npz"))
        it, ok = d["iterations"], d["success"]
        lim = 40000                                  # first 40,000 shots (cheap to regenerate)
        idx = np.arange(lim)
        used = set(ex.get(p, {}).get("leg0", []) + ex.get(p, {}).get("legs1to3", []))
        a = np.array([i for i in idx[ok[:lim] & (it[:lim] <= PRE)] if i not in used])          # converge in leg 0
        b = np.array([i for i in idx[ok[:lim] & (it[:lim] > PRE) & (it[:lim] <= PRE + 3 * LEG_IT)] if i not in used])
        sa = sorted(rng.choice(a, n0, replace=False).tolist()); sb = sorted(rng.choice(b, min(nl, len(b)), replace=False).tolist())
        res[p] = dict(leg0=sa, legs1to3=sb, pool_leg0=int(len(a)), pool_legs1to3=int(len(b)),
                      trace_iterations={int(i): int(it[i]) for i in sa + sb})
    json.dump(res, open(out, "w"), indent=1)
    print(json.dumps({p: {k: v for k, v in r.items() if k != "trace_iterations"} for p, r in res.items()}, indent=1))


def regen(p, idxs):
    """syndromes (and observables) of the Test 1b shots idxs (same sampler calls as test1b_quant.run)."""
    P = problem(p); s = P["circuit"].compile_detector_sampler(seed=20261111)
    need = max(idxs) + 1; out = {}; done = 0; n = BATCH[p]
    while done < need:
        det, obs = s.sample(n, separate_observables=True)
        for i in idxs:
            if done <= i < done + n:
                out[i] = (det[i - done][P["z_rows"]].astype(np.uint8), obs[i - done].astype(np.uint8))
        done += n
    return P, out


def scan_L(path):
    """'L' records only (leg -> g8 vector), skipping the other records."""
    b = open(path, "rb").read(); n = len(b); q = 0; L = {}
    u32 = lambda z: struct.unpack_from("<I", b, z)[0]
    while q < n:
        t = b[q]; q += 1
        if t == 76:                                   # 'L'
            leg, nc = u32(q), u32(q + 4); q += 8
            L[leg] = np.frombuffer(b, np.int8, nc, q).copy(); q += 2 * nc
        elif t == 67:                                 # 'C'
            deg = b[q + 17]; q += 18 + 8 * deg
        elif t == 86:                                 # 'V'
            deg = b[q + 20]; q += 21 + 7 * deg + 2
        elif t == 73:                                 # 'I'
            nc = u32(q + 9); q += 13 + nc
        else:
            raise ValueError(f"bad tag {t} at {q - 1}")
    return L


def dump2(out):
    """decode one p = 0.002 Test 1b shot that reaches leg 1 with the dump build (legs 0, 1 dumped)."""
    d = np.load(os.path.join(R1B, "p0.002_int4.2.8_sweep.npz"))
    it, ok = d["iterations"], d["success"]
    i = int(np.flatnonzero(ok[:40000] & (it[:40000] > PRE) & (it[:40000] <= PRE + LEG_IT))[0])
    P, S = regen("0.002", [i])
    os.environ["RELAY_DUMP"] = out; os.environ["RELAY_DUMP_LEGS"] = "2"
    r = make(P).decode_detailed_batch(S[i][0][None, :])[0]
    print(json.dumps(dict(shot=i, iterations=int(r.iterations), trace_iterations=int(it[i]), success=bool(r.success))))


def hexw(bits):                                       # bit list (index 0 = LSB) -> hex string
    v = 0
    for k, x in enumerate(bits):
        if x: v |= 1 << k
    return format(v, "x")


def write(outdir, picks_json, dumps):
    from labels import labels
    os.makedirs(outdir, exist_ok=True)
    ep = json.load(open(os.path.join(HERE, "..", "..", "results", "test1c", "engine_params.json")))
    # g8 per leg from all dumps; must agree wherever two dumps have the same leg
    G = {}; agree = {}
    for f in dumps:
        for leg, v in scan_L(f).items():
            if leg in G:
                same = bool(np.array_equal(G[leg], v)); agree.setdefault(leg, []).append((os.path.basename(f), same))
                assert same, f"g8 of leg {leg} differs in {f}"
            else:
                G[leg] = v; agree.setdefault(leg, []).append((os.path.basename(f), "first"))
    assert np.all(G[0] == 1), "leg 0 g8 must be 1"
    picks = json.load(open(picks_json))
    index = dict(g8_legs=sorted(G), g8_agreement={str(k): v for k, v in agree.items()}, shots=[])
    jobs = [] if os.environ.get("NOGOLDEN") else [("0.003", "golden", int(s)) for s in (96, 106, 53)]
    for p in ("0.003", "0.002"):
        jobs += [(p, "leg0", s) for s in picks[p]["leg0"]] + [(p, "legs1to3", s) for s in picks[p]["legs1to3"]]
    for p in ("0.003", "0.002"):
        P = problem(p); L = labels(P, ep); H = P["H"].tocsr(); O = np.asarray(P["O"].todense() if hasattr(P["O"], "todense") else P["O"]) % 2
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
        if not mine: continue
        if any(k == "golden" for _, k, _ in mine):
            gs = np.load(os.path.join(HERE, "..", "golden", "syndromes.npz"))["syn"]
        S = {}
        rnd = [s for _, k, s in mine if k != "golden"]
        if rnd:
            _, S = regen(p, rnd)
        dec = make(P)
        for (_, kind, s) in mine:
            syn = gs[s] if kind == "golden" else S[s][0]
            r = dec.decode_detailed_batch(syn[None, :])[0]
            d = np.asarray(r.decoding, dtype=np.uint8); it = int(r.iterations)
            assert r.success, (p, kind, s)
            lg = leg_of(it)
            assert lg in G or lg == 0, f"no g8 vector for leg {lg}"
            obs_pred = (O.astype(np.int64) @ d.astype(np.int64)) % 2
            name = f"p{p}_{kind}_{s}"
            with open(os.path.join(outdir, f"shot_{name}.txt"), "w") as f:
                f.write(f"{it} {int(bool(r.success))} {lg + 1} {hexw(obs_pred.tolist())}\n")
                for h in range(NR): f.write(" ".join(str(ptab[h][t]) for t in range(NT)) + "\n")
                for h in range(NR):                  # syndrome of round h, bit x = check position x
                    f.write(hexw([int(syn[rowpos[(x, h)]]) for x in range(NP)]) + "\n")
                for h in range(NR):                  # expected hard decisions [t][p] (bit t*72+p) and presence mask
                    hb = [int(d[col[(t, q, h)]]) if (t, q, h) in col else 0 for t in range(NT) for q in range(NP)]
                    pm = [1 if (t, q, h) in col else 0 for t in range(NT) for q in range(NP)]
                    f.write(hexw(hb) + " " + hexw(pm) + "\n")
                for leg in range(lg + 1):            # g8 + 2 (3 bits) per (round h, t, p), bit (t*72+p)*4
                    for h in range(NR):
                        bits = []
                        for t in range(NT):
                            for q in range(NP):
                                v = int(G[leg][col[(t, q, h)]]) if (t, q, h) in col else 0
                                bits += [(v >> k) & 1 for k in range(4)]   # 4-bit two's complement
                        f.write(hexw(bits) + "\n")
            tr = None
            if kind != "golden":
                tr = picks[p]["trace_iterations"][str(s)]
            index["shots"].append(dict(name=name, p=p, kind=kind, shot=s, iterations=it, legs=lg + 1,
                                       converged_leg0=bool(it <= PRE), trace_iterations=tr,
                                       obs=hexw(obs_pred.tolist()), dec_crc=zlib.crc32(np.packbits(d).tobytes())))
            print(name, it, flush=True)
    json.dump(index, open(os.path.join(outdir, "index.json"), "w"), indent=1)


if __name__ == "__main__":
    m = sys.argv[1]
    if m == "pick": pick(sys.argv[2], *map(int, sys.argv[3:6])) if len(sys.argv) > 3 else pick(sys.argv[2])
    elif m == "pick2": pick(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), sys.argv[6])
    elif m == "dump2": dump2(sys.argv[2])
    elif m == "write": write(sys.argv[2], sys.argv[3], sys.argv[4:])
