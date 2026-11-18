"""Test 2f, step 1: golden dumps of the int4.2.8 decoder with the red-black layer order (Test 1g schedule (2), rb13).

Same decoder as Test 1b / 2a (golden.make settings); only check_layers changes: layer id of a check row of round r =
position of r in ORDER13 = 0, 2, 4, ..., 12, 1, 3, ..., 11 (test1g_order.ids(..., "rb13")). relay_bp runs the layers in
increasing id order, so the dump's layer field is the position in the order; the round is ORDER13[layer].
Shots: the Test 2a syndromes (../../golden/syndromes.npz, p = 0.003, stim seed 20261113) and picks (picks.json):
  3 shots, legs 0-1 dumped (as Test 2a), and shot picks[2] (= shot 53) legs 0-9.
Modes (run from hw/rb/golden):
  decode OUT.npz           all 2,000 syndromes, rb13, batch (the venv decides the build) -> OUT.npz
  compare A.npz B.npz      per-shot equality (iterations, success, decoding, quant counters)
  dump PREFIX              the 3 picks, dump on (legs 2) and off, same call path -> PREFIX_shot{i}.bin, PREFIX_res.npz
  dumplegs PREFIX I LEGS   pick I with RELAY_DUMP_LEGS = LEGS, dump on and off -> PREFIX_shot0.bin, PREFIX_res.npz
  dumpshots PREFIX LEGS S1,S2,..  syndrome indices S (chosen from the rb decodes for leg coverage), dump on and off
"""
import sys, os, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
G2A = os.path.join(HERE, "..", "..", "golden")
sys.path.insert(0, G2A); sys.path.insert(0, os.path.join(HERE, "..", "..", "..", "scripts"))
from golden import problem, pack, GAMMA0, INTERVAL, PRE, LEGS, LEG_IT     # noqa: E402

ORDER13 = [0, 2, 4, 6, 8, 10, 12, 1, 3, 5, 7, 9, 11]


def make(P):
    import relay_bp
    return relay_bp.RelayDecoderF32(P["H"], error_priors=P["priors"], alpha=None, gamma0=GAMMA0, pre_iter=PRE,
                                    num_sets=LEGS, set_max_iter=LEG_IT, gamma_dist_interval=INTERVAL, stop_nconv=1,
                                    seed=0, quant="int4.2.8",
                                    check_layers=[ORDER13.index(int(r)) for r in P["layers"]])


def main():
    m = sys.argv[1]
    P = problem(); syn = np.load(os.path.join(G2A, "syndromes.npz"))["syn"]
    picks = json.load(open(os.path.join(G2A, "picks.json")))["picks"]
    if m == "decode":
        res = make(P).decode_detailed_batch(syn)
        np.savez_compressed(sys.argv[2], **pack(res)); print(f"decoded {len(res)} shots -> {sys.argv[2]}")
    elif m == "compare":
        a, b = np.load(sys.argv[2]), np.load(sys.argv[3])
        rep = {k: int(np.sum(np.any((a[k] != b[k]).reshape(len(a[k]), -1), axis=1))) for k in
               ("iterations", "success", "decoding", "quant_counts")}
        rep["shots"] = int(len(a["iterations"])); print(json.dumps(rep))
    elif m == "dump":
        on, off = [], []
        for i, s in enumerate(picks):
            os.environ.pop("RELAY_DUMP", None)
            off.append(make(P).decode_detailed(syn[s]))
            os.environ["RELAY_DUMP"] = f"{sys.argv[2]}_shot{i}.bin"; os.environ["RELAY_DUMP_LEGS"] = "2"
            d = make(P); on.append(d.decode_detailed(syn[s])); del d
            os.environ.pop("RELAY_DUMP", None)
        A, B = pack(on), pack(off)
        np.savez_compressed(f"{sys.argv[2]}_res.npz", **A)
        same = {k: bool(np.array_equal(A[k], B[k])) for k in A}
        print(json.dumps(dict(picks=picks, iterations=A["iterations"].tolist(), success=A["success"].tolist(),
                              dump_on_vs_off_identical=same)))
    elif m == "dumplegs":
        i, legs = int(sys.argv[3]), sys.argv[4]
        os.environ.pop("RELAY_DUMP", None)
        B = pack([make(P).decode_detailed(syn[picks[i]])])
        os.environ["RELAY_DUMP"] = f"{sys.argv[2]}_shot0.bin"; os.environ["RELAY_DUMP_LEGS"] = legs
        A = pack([make(P).decode_detailed(syn[picks[i]])])
        os.environ.pop("RELAY_DUMP", None)
        np.savez_compressed(f"{sys.argv[2]}_res.npz", **A)
        print(json.dumps(dict(shot=picks[i], pick=i, legs_dumped=legs, iterations=int(A["iterations"][0]),
                              success=bool(A["success"][0]),
                              dump_on_vs_off_identical={k: bool(np.array_equal(A[k], B[k])) for k in A})))
    elif m == "dumpshots":
        legs = sys.argv[3]; shots = [int(x) for x in sys.argv[4].split(",")]
        on, off = [], []
        for i, s in enumerate(shots):
            os.environ.pop("RELAY_DUMP", None)
            off.append(make(P).decode_detailed(syn[s]))
            os.environ["RELAY_DUMP"] = f"{sys.argv[2]}_shot{i}.bin"; os.environ["RELAY_DUMP_LEGS"] = legs
            d = make(P); on.append(d.decode_detailed(syn[s])); del d
            os.environ.pop("RELAY_DUMP", None)
        A, B = pack(on), pack(off)
        np.savez_compressed(f"{sys.argv[2]}_res.npz", **A)
        print(json.dumps(dict(shots=shots, legs_dumped=legs, iterations=A["iterations"].tolist(),
                              success=A["success"].tolist(),
                              dump_on_vs_off_identical={k: bool(np.array_equal(A[k], B[k])) for k in A})))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main()
