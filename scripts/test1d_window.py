"""Idea 1, Test 1d: sliding-window (streaming) decoding with the round sweep.

Problem: X-decoder matrix xdec (dem_tools.xdecoder_problem), rounds 0..R (R = final data-measurement round).
Decoder: relay_bp.RelayDecoderF32, quant = "none" (float, as Test 1b), sweep (one layer per round), Test 2b / 1b
parameters: S = 1, gamma0 = 0.125, alpha = None (alpha = 1), gamma interval (-0.226, 0.622), pre_iter 80, 300 legs x 60.

Window W rounds, commit C rounds, t = 0, C, 2C, ...:
  rows    = detectors with round in [t, t + W)
  columns = errors whose home round (earliest detector) is in [t, t + W), restricted to those rows; priors from xdec
  syndrome = observed syndrome of those rows XOR H[rows, :] e_committed (effect of everything committed so far)
  decode with the sweep (layer = round - t); commit columns with home round in [t, t + C);
  the last window (t + W >= R + 1) commits every column of the window.
A window that does not converge commits the decoding the relay decoder returns (with S = 1 and no converged leg this
is the hard decision of the first, pre_iter leg - the same rule the global decoder uses) and is counted.
Global decoding = one window with W >= R + 1.

Traces (.npz): iterations (shots x windows, total over relay legs), window_converged (shots x windows),
logical_fail (shots), window_t, W, C, R. test1e_queue.py reads 2-D 'iterations' as per-window jobs.

Usage:
  python test1d_window.py validate <circuit_12rounds> <shots> <out.json>
  python test1d_window.py run <circuit> <W|global> <C> <shots> <seed> <out.npz>
  python test1d_window.py chunked <circuit> <tag> <shots> <chunk> <seed0> <outdir> global,W6_C3,W8_C4,W12_C8
  python test1d_window.py merge <tag> <shots> <chunk> <outdir> global,W6_C3,W8_C4,W12_C8
"""
import sys, json, time
import numpy as np
import scipy.sparse as sp
from dem_tools import xdecoder_problem

ARGS = dict(alpha=None, gamma0=0.125, pre_iter=80, num_sets=300, set_max_iter=60,
            gamma_dist_interval=(-0.22628432386414646, 0.6216020925981884), stop_nconv=1, seed=0, quant="none")


class Windowed:
    def __init__(self, P, W, C):
        import relay_bp
        self.H = P["H"].tocsr(); self.pri = P["priors"]; self.O = P["O"].astype(np.int64)
        rnd = np.asarray(P["layers"]); self.NR = int(rnd.max()) + 1
        Hc = self.H.tocsc()
        self.home = np.array([rnd[Hc.indices[Hc.indptr[j]:Hc.indptr[j + 1]]].min() for j in range(self.H.shape[1])])
        if W is None or W >= self.NR:
            W, C = self.NR, self.NR
        self.W, self.C = W, C
        self.win = []
        t = 0
        while True:
            last = t + W >= self.NR
            rows = np.where((rnd >= t) & (rnd < t + W))[0]
            cols = np.where((self.home >= t) & (self.home < t + W))[0]
            Hw = self.H[rows][:, cols].tocsr()
            commit = np.ones(len(cols), bool) if last else (self.home[cols] < t + C)
            dec = relay_bp.RelayDecoderF32(Hw, error_priors=self.pri[cols],
                                           check_layers=[int(x) for x in (rnd[rows] - t)], **ARGS)
            Hr = self.H[rows].tocsc()
            tc = np.where(np.diff(Hr.indptr) > 0)[0]                  # columns touching the window rows
            self.win.append(dict(t=t, rows=rows, cols=cols, commit=commit, dec=dec, tc=tc,
                                 Htc=Hr[:, tc].tocsr().astype(np.uint8)))
            if last:
                break
            t += C
        n_committed = sum(int(w["commit"].sum()) for w in self.win)
        assert n_committed == self.H.shape[1], f"columns committed {n_committed} != {self.H.shape[1]}"

    def decode(self, syn):
        """syn: shots x m (uint8). Returns e (shots x n), iterations, converged (shots x windows)."""
        S = syn.shape[0]
        E = np.zeros((S, self.H.shape[1]), dtype=np.uint8)
        it = np.zeros((S, len(self.win)), dtype=np.int32); ok = np.zeros((S, len(self.win)), bool)
        for k, w in enumerate(self.win):
            # effect of committed errors on the window rows (uint8 is exact: row weight <= 35)
            corr = (w["Htc"] @ E[:, w["tc"]].T).T % 2 if k > 0 else 0
            s_w = (syn[:, w["rows"]] ^ corr).astype(np.uint8)
            res = w["dec"].decode_detailed_batch(s_w)
            d = np.array([r.decoding for r in res], dtype=np.uint8)
            it[:, k] = [r.iterations for r in res]; ok[:, k] = [r.success for r in res]
            E[:, w["cols"][w["commit"]]] = d[:, w["commit"]]
        return E, it, ok


def logical_fail(E, O, obs, sub=2000):
    out = np.zeros(E.shape[0], bool)
    for a in range(0, E.shape[0], sub):
        out[a:a + sub] = np.any((E[a:a + sub].astype(np.int32) @ O.T.astype(np.int32)) % 2 != obs[a:a + sub], axis=1)
    return out


def syndrome_ok(H, E, syn):
    """True per shot if H e == syn (uint8 products are exact: row weight <= 35)."""
    return ~np.any(((H.astype(np.uint8) @ E.T).T % 2) != syn, axis=1)


SETTINGS = {"global": (None, None), "W6_C3": (6, 3), "W8_C4": (8, 4), "W12_C8": (12, 8)}


def chunked(path, tag, shots, chunk, seed0, outdir, names, sub=2500):
    """Checkpointed run: chunk k uses sampler seed seed0 + k for every setting (same shots). A finished chunk is
    written atomically (tmp + rename) and skipped on restart, so a crash loses at most one chunk."""
    import os
    os.makedirs(os.path.join(outdir, "chunks"), exist_ok=True)
    P = xdecoder_problem(path)
    nchunks = -(-shots // chunk)
    W = {}
    for k in range(nchunks):
        n = min(chunk, shots - k * chunk)
        fn = {s: os.path.join(outdir, "chunks", f"{tag}_{s}_c{k:04d}.npz") for s in names}
        todo = [s for s in names if not os.path.exists(fn[s])]
        if not todo:
            print(f"chunk {k + 1}/{nchunks}: already done, skipped", flush=True); continue
        syn, obs = sample(P, n, seed0 + k)
        for s in todo:
            if s not in W:
                W[s] = Windowed(P, *SETTINGS[s])
            w = W[s]; t0 = time.time()
            parts = [w.decode(syn[a:a + sub]) for a in range(0, n, sub)]
            E = np.concatenate([x[0] for x in parts]); it = np.concatenate([x[1] for x in parts])
            ok = np.concatenate([x[2] for x in parts])
            fail = logical_fail(E, w.O, obs)
            synok = syndrome_ok(w.H, E, syn)
            tmp = fn[s] + ".tmp.npz"
            np.savez_compressed(tmp, iterations=it, window_converged=ok, logical_fail=fail, syndrome_ok=synok,
                                window_t=np.array([x["t"] for x in w.win]), W=w.W, C=w.C, R=w.NR - 1,
                                seconds=time.time() - t0)
            os.replace(tmp, fn[s])
            print(f"chunk {k + 1}/{nchunks} {s}: {n} shots, fails {int(fail.sum())}, windows not converged "
                  f"{int((~ok).sum())}, {time.time() - t0:.0f} s", flush=True)
    print("CHUNKS DONE", tag, flush=True)


def merge(tag, shots, chunk, outdir, names):
    import os
    nchunks = -(-shots // chunk)
    for s in names:
        fs = [os.path.join(outdir, "chunks", f"{tag}_{s}_c{k:04d}.npz") for k in range(nchunks)]
        missing = [f for f in fs if not os.path.exists(f)]
        assert not missing, f"missing chunks: {missing[:3]}"
        D = [np.load(f) for f in fs]
        it = np.concatenate([d["iterations"] for d in D]); ok = np.concatenate([d["window_converged"] for d in D])
        fail = np.concatenate([d["logical_fail"] for d in D]); synok = np.concatenate([d["syndrome_ok"] for d in D])
        assert len(fail) == shots, f"{s}: {len(fail)} shots merged, expected {shots}"
        R = int(D[0]["R"]); ler = float(fail.mean()); allok = ok.all(1)
        np.savez_compressed(os.path.join(outdir, f"{tag}_{s}.npz"), iterations=it, window_converged=ok,
                            logical_fail=fail, window_t=D[0]["window_t"], W=D[0]["W"], C=D[0]["C"], R=R)
        summ = dict(tag=tag, setting=s, W=int(D[0]["W"]), C=int(D[0]["C"]), rounds=R, shots=int(len(fail)),
                    windows=int(it.shape[1]), fails=int(fail.sum()), ler=ler,
                    ler_per_round=(1 - (1 - 2 * ler) ** (1 / R)) / 2,
                    windows_not_converged=int((~ok).sum()), shots_with_unconverged_window=int((~allok).sum()),
                    syndrome_mismatch_in_fully_converged_shots=int(np.sum(allok & ~synok)),
                    cpu_seconds=float(sum(float(d["seconds"]) for d in D)))
        json.dump(summ, open(os.path.join(outdir, f"{tag}_{s}.json"), "w"), indent=1)
        print(json.dumps(summ), flush=True)
    print("MERGE DONE", tag, flush=True)


def sample(P, shots, seed):
    det, obs = P["circuit"].compile_detector_sampler(seed=seed).sample(shots, separate_observables=True)
    return det[:, P["z_rows"]].astype(np.uint8), obs.astype(np.int64)


def validate(path, shots, out):
    import relay_bp
    P = xdecoder_problem(path)
    syn, obs = sample(P, shots, 20261111)
    w = Windowed(P, 10 ** 6, None)
    t0 = time.time(); E, it, ok = w.decode(syn); tw = time.time() - t0
    g = relay_bp.RelayDecoderF32(P["H"], error_priors=P["priors"], check_layers=[int(x) for x in P["layers"]], **ARGS)
    res = g.decode_detailed_batch(syn)
    Eg = np.array([r.decoding for r in res], dtype=np.uint8); itg = np.array([r.iterations for r in res])
    r = dict(shots=shots, windows=len(w.win), decisions_identical=bool(np.array_equal(E, Eg)),
             differing_decisions=int(np.sum(E != Eg)), iterations_identical=bool(np.array_equal(it[:, 0], itg)),
             shots_with_different_iterations=int(np.sum(it[:, 0] != itg)), seconds=round(tw, 1))
    # syndrome check on a real sliding window as well (W=6, C=3) on the same shots
    for (W, C) in ((6, 3), (8, 4)):
        ww = Windowed(P, W, C); E2, it2, ok2 = ww.decode(syn)
        allok = ok2.all(1)
        bad = int(np.sum(np.any(((P["H"] @ E2[allok].T.astype(np.int64)).T % 2) != syn[allok], axis=1)))
        r[f"W{W}C{C}_syndrome_check"] = dict(shots_all_windows_converged=int(allok.sum()), syndrome_mismatches=bad,
                                             windows=len(ww.win))
    print(json.dumps(r), flush=True)
    json.dump(r, open(out, "w"), indent=1)


def run(path, W, C, shots, seed, out):
    P = xdecoder_problem(path)
    t0 = time.time(); w = Windowed(P, W, C); t_build = time.time() - t0
    syn, obs = sample(P, shots, seed)
    t0 = time.time(); E, it, ok = w.decode(syn); t_dec = time.time() - t0
    fail = logical_fail(E, w.O, obs)
    allok = ok.all(1)
    synbad = int(np.sum(allok & ~syndrome_ok(w.H, E, syn)))
    np.savez_compressed(out, iterations=it, window_converged=ok, logical_fail=fail,
                        window_t=np.array([x["t"] for x in w.win]), W=w.W, C=w.C, R=w.NR - 1)
    R = w.NR - 1
    ler = float(fail.mean())
    summ = dict(circuit=path.split("/")[-1], W=w.W, C=w.C, rounds=R, shots=shots, windows=len(w.win),
                window_t=[int(x["t"]) for x in w.win], fails=int(fail.sum()), ler=ler,
                ler_per_round=(1 - (1 - 2 * ler) ** (1 / R)) / 2,
                windows_not_converged=int((~ok).sum()), shots_with_unconverged_window=int((~allok).sum()),
                syndrome_mismatch_in_fully_converged_shots=synbad,
                mean_it_per_window=it.mean(0).round(1).tolist(), seconds_build=round(t_build, 1),
                seconds_decode=round(t_dec, 1), seconds_per_shot=t_dec / shots)
    json.dump(summ, open(out.replace(".npz", ".json"), "w"), indent=1)
    print(json.dumps(summ), flush=True)


if __name__ == "__main__":
    m = sys.argv[1]
    if m == "chunked":      # chunked <circuit> <tag> <shots> <chunk> <seed0> <outdir> <settings,comma>
        chunked(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7],
                sys.argv[8].split(","))
    elif m == "merge":      # merge <tag> <shots> <chunk> <outdir> <settings,comma>
        merge(sys.argv[2], int(sys.argv[3]), int(sys.argv[4]), sys.argv[5], sys.argv[6].split(","))
    elif m == "validate":
        validate(sys.argv[2], int(sys.argv[3]), sys.argv[4])
    else:
        W = None if sys.argv[3] == "global" else int(sys.argv[3])
        C = None if W is None else int(sys.argv[4])
        run(sys.argv[2], W, C, int(sys.argv[5]), int(sys.argv[6]), sys.argv[7])
