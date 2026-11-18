"""Review fixes, part A.1: sliding-window decoding of the 36-round gross-code circuit with the red-black int4.2.8 decoder.

Windows and commit: test1d_window.Windowed unchanged (W rounds, commit C, last window commits all; global = one window).
Each window's decoder is replaced by relay_bp RelayDecoderF32 with quant int4.2.8 and the red-black order over the
window's own detector layers (local layer l = round - t; ids: the even l first, then the odd l), Test 1b settings.
Shots: Test 1d chunks (test1d_window.sample, chunk k = sampler seed seed0 + k): p = 0.003: 6 x 5,000 (seed0 1000);
p = 0.002: 25,000 per chunk (seed0 2000), chunks in order until --budget hours have passed (no chunk is started after).
Both settings decode the same chunks. Per chunk and setting: results/review_fixes/windows/chunks/<tag>_<set>_c<k>.npz.
Modes:
  run <tag> <shots> <chunk> <seed0> [budget_h]     (RAYON_NUM_THREADS threads per batch)
  merge <tag>                                       -> windows/<tag>_<setting>.npz (+ .json)
"""
import sys, os, json, time, glob
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import test1d_window as T1D                                             # noqa: E402
from archive_shots2 import C36                                          # noqa: E402

OUT = os.path.join(HERE, "..", "results", "review_fixes", "windows")
SETTINGS = {"W12_C8": (12, 8), "global": (None, None)}
ARGS = dict(alpha=None, gamma0=0.125, pre_iter=80, num_sets=300, set_max_iter=60,
            gamma_dist_interval=(-0.22628432386414646, 0.6216020925981884), stop_nconv=1, seed=0, quant="int4.2.8")


def rb_ids(local):
    L = int(local.max()) + 1
    order = list(range(0, L, 2)) + list(range(1, L, 2))
    pos = {l: i for i, l in enumerate(order)}
    return [pos[int(l)] for l in local]


def rb_windowed(P, W, C):
    import relay_bp
    w = T1D.Windowed(P, W, C)
    rnd = np.asarray(P["layers"])
    for x in w.win:
        Hw = w.H[x["rows"]][:, x["cols"]].tocsr()
        x["dec"] = relay_bp.RelayDecoderF32(Hw, error_priors=w.pri[x["cols"]], check_layers=rb_ids(rnd[x["rows"]] - x["t"]), **ARGS)
        x["layers"] = int((rnd[x["rows"]] - x["t"]).max()) + 1
    return w


def run(tag, shots, chunk, seed0, budget_h=None):
    from dem_tools import xdecoder_problem
    p = tag[1:]
    P = xdecoder_problem(C36.format(p=p))
    os.makedirs(os.path.join(OUT, "chunks"), exist_ok=True)
    Ws = {s: rb_windowed(P, *v) for s, v in SETTINGS.items()}
    t_start = time.time()
    for k in range(-(-shots // chunk)):
        if budget_h is not None and time.time() - t_start > budget_h * 3600:
            print(f"budget of {budget_h} h reached before chunk {k}", flush=True); break
        n = min(chunk, shots - k * chunk)
        fn = {s: os.path.join(OUT, "chunks", f"{tag}_{s}_c{k:04d}.npz") for s in SETTINGS}
        if all(os.path.exists(f) for f in fn.values()):
            continue
        syn, obs = T1D.sample(P, n, seed0 + k)
        for s, w in Ws.items():
            t0 = time.time()
            parts = [w.decode(syn[a:a + 2500]) for a in range(0, n, 2500)]
            E = np.concatenate([x[0] for x in parts]); it = np.concatenate([x[1] for x in parts]); ok = np.concatenate([x[2] for x in parts])
            fail = T1D.logical_fail(E, w.O, obs)
            synok = T1D.syndrome_ok(w.H, E, syn)
            tmp = fn[s] + ".tmp.npz"
            np.savez_compressed(tmp, iterations=it, window_converged=ok, logical_fail=fail, syndrome_ok=synok,
                                window_t=np.array([x["t"] for x in w.win]), window_layers=np.array([x["layers"] for x in w.win]),
                                W=w.W, C=w.C, R=w.NR - 1, seed=seed0 + k, seconds=time.time() - t0)
            os.replace(tmp, fn[s])
            print(json.dumps(dict(tag=tag, chunk=k, setting=s, shots=n, fails=int(fail.sum()),
                                  windows_not_converged=int((~ok).sum()), seconds=round(time.time() - t0))), flush=True)
    print("RUN DONE", tag, flush=True)


def merge(tag):
    for s in SETTINGS:
        fs = sorted(glob.glob(os.path.join(OUT, "chunks", f"{tag}_{s}_c*.npz")))
        D = [dict(np.load(f)) for f in fs]
        it = np.concatenate([d["iterations"] for d in D]); ok = np.concatenate([d["window_converged"] for d in D])
        fail = np.concatenate([d["logical_fail"] for d in D]); synok = np.concatenate([d["syndrome_ok"] for d in D])
        np.savez_compressed(os.path.join(OUT, f"{tag}_{s}.npz"), iterations=it, window_converged=ok, logical_fail=fail,
                            syndrome_ok=synok, window_t=D[0]["window_t"], window_layers=D[0]["window_layers"],
                            W=D[0]["W"], C=D[0]["C"], R=D[0]["R"], seeds=np.array([int(d["seed"]) for d in D]))
        R = int(D[0]["R"]); ler = float(fail.mean())
        json.dump(dict(tag=tag, setting=s, chunks=len(D), shots=int(len(fail)), fails=int(fail.sum()), ler=ler,
                       ler_per_round=(1 - (1 - 2 * ler) ** (1 / R)) / 2, rounds=R,
                       windows=int(it.shape[1]), window_layers=D[0]["window_layers"].tolist(),
                       windows_not_converged=int((~ok).sum()),
                       syndrome_mismatch_in_fully_converged=int(np.sum(ok.all(1) & ~synok)),
                       seconds=float(sum(float(d["seconds"]) for d in D))),
                  open(os.path.join(OUT, f"{tag}_{s}.json"), "w"), indent=1)
        print("merged", tag, s, len(fail), int(fail.sum()), flush=True)


if __name__ == "__main__":
    m = sys.argv[1]
    if m == "run":
        run(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), int(sys.argv[5]), float(sys.argv[6]) if len(sys.argv) > 6 else None)
    elif m == "merge":
        merge(sys.argv[2])
