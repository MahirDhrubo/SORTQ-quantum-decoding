"""Review fixes, part B.2: rb13 int4.2.8 accuracy with the hardware LFSR memory strengths (engine_top_rb, LFSR mode).

Stream model: one engine, reset once before the first shot, then the shots of a set in sample order without reset (as
the hardware decodes a stream). The LFSR state therefore carries from shot to shot: lfsr_model.draws(it) draws per decode,
one global draw counter for all 720 lanes (hw/rb/sim/lfsr_model.py, verified against the RTL in part B.1 / B.3).
Leg 0 uses g8 = 1 in hardware and software, so a shot that converges within leg 0 (it <= 80) decodes exactly as in
the PRNG trace and is copied (it == 80 still advances the counter by 6 prefill draws). Every shot with it > 80 in the
PRNG trace is decoded again, in shot order, with explicit_gammas from the LFSR model.
Decoder: as Test 1g rb13 (int4.2.8, relay_bp RelayDecoderF32, Test 1b settings), plus explicit_gammas.
Shots: archive/shots/<set>.npz (Test 1b / Test 1h sets; identical to the original sampler calls).
Usage: python review_lfsr_acc.py <set> <prng trace npz> <out npz>
"""
import sys, os, json, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
IDEAS = os.path.join(HERE, "..")
sys.path.insert(0, os.path.join(IDEAS, "hw", "rb", "sim")); sys.path.insert(0, os.path.join(IDEAS, "hw", "gen"))
import lfsr_model as M                                  # noqa: E402
from archive_shots import CIRC, load                    # noqa: E402
from test1b_quant import PRE, LEG_IT, LEGS, GAMMA0, INTERVAL, first_leg, CAP   # noqa: E402

ORDER13 = [0, 2, 4, 6, 8, 10, 12, 1, 3, 5, 7, 9, 11]


def main(setname, trace, out):
    import relay_bp
    from dem_tools import xdecoder_problem
    from labels import labels
    p = setname.split("_")[0][1:]
    P = xdecoder_problem(CIRC.format(p=p))
    ep = json.load(open(os.path.join(IDEAS, "results", "test1c", "engine_params.json")))
    L = labels(P, ep)
    lane = (L["col_t"] * M.NP + L["col_p"]).astype(np.int64); home = L["col_h"].astype(int)
    H, pri, O = P["H"], P["priors"], P["O"].astype(np.int64)
    layers = [ORDER13.index(int(r)) for r in P["layers"]]
    T = M.period_table()
    tr = dict(np.load(trace))
    it0, ok0, f0 = tr["iterations"].astype(np.int64), tr["success"], tr["logical_fail"]
    n = len(it0) if not os.environ.get("LIMIT_SHOTS") else int(os.environ["LIMIT_SHOTS"])   # smoke test only
    det, obs, z = load(setname, n)
    assert det.shape[0] == n
    it0, ok0, f0 = it0[:n], ok0[:n], f0[:n]
    it, ok, fail = it0.copy(), ok0.copy(), f0.copy()
    D, redo, t0 = 0, 0, time.time()
    for i in range(n):
        if it0[i] <= PRE:
            D += M.draws(int(it0[i])); continue
        G = M.gamma_matrix(T, D, lane, home)
        dec = relay_bp.RelayDecoderF32(H, error_priors=pri, alpha=None, gamma0=GAMMA0, pre_iter=PRE, num_sets=LEGS,
                                       set_max_iter=LEG_IT, gamma_dist_interval=INTERVAL, stop_nconv=1, seed=0,
                                       quant="int4.2.8", check_layers=layers, explicit_gammas=G)
        r = dec.decode_detailed_batch(det[i:i + 1, z].astype(np.uint8))[0]
        d = np.asarray(r.decoding, dtype=np.int64)
        it[i], ok[i] = int(r.iterations), bool(r.success)
        fail[i] = bool(np.any((O @ d) % 2 != obs[i]))
        D += M.draws(int(it[i])); redo += 1
        if redo % 500 == 0:
            print(json.dumps(dict(shot=i, redone=redo, draws=D, s=round(time.time() - t0))), flush=True)
    np.savez_compressed(out, iterations=it, success=ok, logical_fail=fail, first_leg=first_leg(it, ok),
                        hit_cap=(it >= CAP) & ~ok, prng_iterations=it0, prng_logical_fail=f0)
    summ = dict(set=setname, trace=trace, shots=n, redecoded=redo, total_draws=int(D), wraps_of_period=D / 65535,
                fails_lfsr=int(fail.sum()), fails_prng=int(f0.sum()), mean_it_lfsr=float(it.mean()),
                mean_it_prng=float(it0.mean()), seconds=round(time.time() - t0, 1))
    json.dump(summ, open(out.replace(".npz", ".json"), "w"), indent=1)
    print(json.dumps(summ), flush=True)


if __name__ == "__main__":
    main(*sys.argv[1:4])
