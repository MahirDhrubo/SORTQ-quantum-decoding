"""Test 2a, Step 0: golden reference dumps from the Test 1b integer decoder (int4.2.8, round sweep).

Decoder settings exactly as Test 1b (test1b_quant.make): RelayDecoderF32, alpha None (= 1), gamma0 0.125,
pre_iter 80, 300 legs x 60, gamma interval (-0.226, 0.622), stop_nconv 1, seed 0, check_layers = rounds.

Modes (run from hw/golden; the venv decides which relay_bp build is used):
  sample  N SEED              sample N syndromes of the 12-round p = 0.003 circuit -> syndromes.npz
  decode  OUT.npz FMT SCHED   decode all of syndromes.npz (batch, RAYON_NUM_THREADS threads) -> OUT.npz
  pick    REF.npz K           choose K shots whose first leg does not converge (so leg 2 runs) -> picks.json
  dump    OUT_PREFIX          decode each picked shot alone with RELAY_DUMP=<prefix>_shot<i>.bin -> <prefix>_res.npz
  single  OUT.npz             decode each picked shot alone, no dump (same call path as 'dump') -> OUT.npz
  dumplegs OUT_PREFIX I LEGS  decode picked shot picks[I] alone with RELAY_DUMP_LEGS=LEGS (legs 0..LEGS-1 dumped)
                              -> <prefix>_shot0.bin, <prefix>_res.npz (leg-boundary coverage)
  compare A.npz B.npz         per-shot equality of iterations, success, decoding, quant_counts
"""
import sys, os, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))
CIRC = os.path.join(HERE, "..", "..", "circuits", "bb_ibm",
                    "circuit=bicycle_bivariate_144_12_12_memory_Z,distance=12,rounds=12,error_rate=0.003,"
                    "noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim")
GAMMA0, INTERVAL = 0.125, (-0.22628432386414646, 0.6216020925981884)
PRE, LEGS, LEG_IT = 80, 300, 60


def problem():
    from dem_tools import xdecoder_problem
    return xdecoder_problem(CIRC)


def make(P, fmt, sched):
    import relay_bp
    kw = dict(alpha=None, gamma0=GAMMA0, pre_iter=PRE, num_sets=LEGS, set_max_iter=LEG_IT,
              gamma_dist_interval=INTERVAL, stop_nconv=1, seed=0, quant="none" if fmt == "float" else fmt)
    if sched == "sweep":
        kw["check_layers"] = [int(x) for x in P["layers"]]
    return relay_bp.RelayDecoderF32(P["H"], error_priors=P["priors"], **kw)


def pack(res):
    return dict(iterations=np.array([r.iterations for r in res]), success=np.array([r.success for r in res]),
                decoding=np.array([np.asarray(r.decoding) for r in res], dtype=np.uint8),
                quant_counts=np.array([r.quant_counts or [0] * 8 for r in res], dtype=np.uint64))


def main():
    m = sys.argv[1]
    if m == "sample":
        n, seed = int(sys.argv[2]), int(sys.argv[3])
        P = problem()
        det, obs = P["circuit"].compile_detector_sampler(seed=seed).sample(n, separate_observables=True)
        np.savez_compressed("syndromes.npz", syn=det[:, P["z_rows"]].astype(np.uint8), seed=seed, circuit=CIRC)
        print(f"sampled {n} shots, seed {seed}")
    elif m == "decode":
        out, fmt, sched = sys.argv[2:5]
        P = problem(); syn = np.load("syndromes.npz")["syn"]
        res = make(P, fmt, sched).decode_detailed_batch(syn)
        np.savez_compressed(out, **pack(res)); print(f"decoded {len(res)} shots -> {out}")
    elif m == "pick":
        ref, k = np.load(sys.argv[2]), int(sys.argv[3])
        it, ok = ref["iterations"], ref["success"]
        two = np.where((it > PRE) & ok & (it <= PRE + LEG_IT))[0]      # converges in leg 2 (index 1)
        more = np.where((it > PRE + LEG_IT) | ~ok)[0]                  # leg 2 also fails
        picks = [int(x) for x in list(two[:k - 1]) + list(more[:1])]
        info = dict(picks=picks, iterations=[int(it[i]) for i in picks], success=[bool(ok[i]) for i in picks],
                    n_shots=len(it), n_leg1_fails=int(np.sum((it > PRE) | ~ok)), rule=
                    "first K-1 shots converging in leg 2 (80 < it <= 140) + first shot needing more than 2 legs")
        json.dump(info, open("picks.json", "w"), indent=1); print(json.dumps(info))
    elif m in ("dump", "single"):
        P = problem(); syn = np.load("syndromes.npz")["syn"]; picks = json.load(open("picks.json"))["picks"]
        res = []
        for i, s in enumerate(picks):
            if m == "dump":
                os.environ["RELAY_DUMP"] = f"{sys.argv[2]}_shot{i}.bin"; os.environ["RELAY_DUMP_LEGS"] = "2"
            else:
                os.environ.pop("RELAY_DUMP", None)
            dec = make(P, "int4.2.8", "sweep")
            res.append(dec.decode_detailed(syn[s]))
            del dec
        out = f"{sys.argv[2]}_res.npz" if m == "dump" else sys.argv[2]
        np.savez_compressed(out, **pack(res)); print(f"{m}: {len(res)} shots -> {out}")
    elif m == "dumplegs":
        P = problem(); syn = np.load("syndromes.npz")["syn"]; picks = json.load(open("picks.json"))["picks"]
        i, legs = int(sys.argv[3]), sys.argv[4]
        os.environ.pop("RELAY_DUMP", None)
        off = pack([make(P, "int4.2.8", "sweep").decode_detailed(syn[picks[i]])])      # dump off, same call path
        os.environ["RELAY_DUMP"] = f"{sys.argv[2]}_shot0.bin"; os.environ["RELAY_DUMP_LEGS"] = legs
        on = pack([make(P, "int4.2.8", "sweep").decode_detailed(syn[picks[i]])])
        os.environ.pop("RELAY_DUMP", None)
        np.savez_compressed(f"{sys.argv[2]}_res.npz", **on)
        same = {k: bool(np.array_equal(on[k], off[k])) for k in on}
        print(f"dumplegs: shot {picks[i]} (pick {i}), legs dumped {legs}, iterations {int(on['iterations'][0])}, "
              f"success {bool(on['success'][0])}; dump on vs off identical: {same}")
    elif m == "compare":
        a, b = np.load(sys.argv[2]), np.load(sys.argv[3])
        rep = {k: int(np.sum(np.any((a[k] != b[k]).reshape(len(a[k]), -1), axis=1))) for k in
               ("iterations", "success", "decoding", "quant_counts")}
        rep["shots"] = int(len(a["iterations"])); rep["identical"] = all(v == 0 for k, v in rep.items() if k != "shots")
        print(json.dumps(rep))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
