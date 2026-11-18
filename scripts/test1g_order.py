"""Idea 1, Test 1g: red-black round order (layer ORDER changed, one or two layers per parity).

Decoder exactly as Test 1b / 1f int4.2.8 (relay_bp.RelayDecoderF32, quant int4.2.8, alpha = 1, S = 1, gamma0 = 0.125,
gamma interval (-0.226, 0.622), pre_iter 80, 300 legs x 60, cap 18,080); 12-round circuit, X decoder; sampler seed
20261111 with the Test 1b batch x workers, so the shots are the Test 1b shots; every schedule decodes the same shots.
relay_bp processes the layers in increasing id order (min_sum.rs, run_layered_iteration), so the order is set by the
ids (round r of each check row from dem_tools.layers):
  sweep = r                                  13 layers 0, 1, ..., 12 (= Test 1b sweep)
  rb13  = position of r in 0,2,4,...,12,1,3,...,11   13 layers, one round each, even rounds first
  rb2   = r % 2                              2 layers: {even rounds}, {odd rounds}
Modes:
  hcheck <circuit>                                 column check: rounds touched by each error column (parity)
  run <circuit> <tag> <shots> <workers> <batch> <outdir>   traces <tag>_<sched>.npz (Test 1b format + dec_crc)
  report <outdir> <test1b_dir>                     LER, paired vs sweep (McNemar), iterations, rb13 vs rb2 shot by
                                                   shot (decoding CRC, iterations, success), sweep vs Test 1b
"""
import sys, os, json, time, zlib
import numpy as np
from collections import Counter
from test1b_quant import PRE, LEG_IT, CAP, GAMMA0, INTERVAL, LEGS, first_leg, mcnemar

SCHEDS = ("sweep", "rb13", "rb2")
# env TEST1G_SCHEDS (comma list) restricts the run mode to those schedules (e.g. "sweep,rb13" for the p = 0.001 run)
if os.environ.get("TEST1G_SCHEDS"):
    SCHEDS = tuple(os.environ["TEST1G_SCHEDS"].split(","))
FMT = "int4.2.8"
ORDER13 = [0, 2, 4, 6, 8, 10, 12, 1, 3, 5, 7, 9, 11]
_G = {}


def ids(layers, s):
    if s == "sweep":
        return [int(r) for r in layers]
    if s == "rb13":
        return [ORDER13.index(int(r)) for r in layers]
    if s == "rb2":
        return [int(r) % 2 for r in layers]
    raise ValueError(s)


def make(H, pri, layers, s):
    import relay_bp
    kw = dict(alpha=None, gamma0=GAMMA0, pre_iter=PRE, num_sets=LEGS, set_max_iter=LEG_IT,
              gamma_dist_interval=INTERVAL, stop_nconv=1, seed=0, quant=FMT, check_layers=ids(layers, s))
    return relay_bp.RelayDecoderF32(H, error_priors=pri, **kw)


def hcheck(path):
    import scipy.sparse as sp
    from dem_tools import xdecoder_problem
    P = xdecoder_problem(path)
    H = sp.csc_matrix(P["H"]); L = np.asarray(P["layers"])
    sets, bad_even, bad_odd = Counter(), 0, 0
    for c in range(H.shape[1]):
        rr = L[H.indices[H.indptr[c]:H.indptr[c + 1]]]
        ev = sorted(set(int(r) for r in rr if r % 2 == 0)); od = sorted(set(int(r) for r in rr if r % 2 == 1))
        bad_even += len(ev) > 1; bad_odd += len(od) > 1
        sets[tuple(sorted(set(int(r) - min(rr) for r in rr)))] += 1
    res = dict(columns=int(H.shape[1]), rows=int(H.shape[0]), columns_touching_two_even_rounds=int(bad_even),
               columns_touching_two_odd_rounds=int(bad_odd),
               round_span_patterns={str(k): v for k, v in sorted(sets.items())})
    print(json.dumps(res, indent=1))
    return res


def init(H, pri, layers):
    for s in SCHEDS:
        _G[s] = make(H, pri, layers, s)


def work(syn):
    out = {}
    for s, dec in _G.items():
        t0 = time.time()
        r = dec.decode_detailed_batch(syn)
        d = np.array([x.decoding for x in r], dtype=np.uint8)
        out[s] = dict(dec=d, it=np.array([x.iterations for x in r], dtype=np.int32),
                      ok=np.array([x.success for x in r]),
                      crc=np.array([zlib.crc32(np.packbits(row).tobytes()) for row in d], dtype=np.uint32),
                      sec=time.time() - t0)
    return out


def run(path, tag, shots, workers, batch, outdir):
    from multiprocessing import Pool
    from dem_tools import xdecoder_problem
    os.makedirs(outdir, exist_ok=True)
    P = xdecoder_problem(path)
    H, pri, O, layers = P["H"], P["priors"], P["O"], P["layers"]
    sampler = P["circuit"].compile_detector_sampler(seed=20261111)
    T = {s: dict(it=[], ok=[], fail=[], crc=[]) for s in SCHEDS}
    SEC = {s: 0.0 for s in SCHEDS}
    t_start, done, nb = time.time(), 0, 0

    def save():
        for s in SCHEDS:
            it = np.concatenate(T[s]["it"]); ok = np.concatenate(T[s]["ok"]); fail = np.concatenate(T[s]["fail"])
            np.savez_compressed(os.path.join(outdir, f"{tag}_{s}.npz"), iterations=it, success=ok,
                                first_leg=first_leg(it, ok), hit_cap=(it >= CAP) & ~ok, logical_fail=fail,
                                dec_crc=np.concatenate(T[s]["crc"]))
        summ = dict(tag=tag, shots=done, wall_s=round(time.time() - t_start, 1),
                    layers={s: len(set(ids(layers, s))) for s in SCHEDS},
                    fails={s: int(np.concatenate(T[s]["fail"]).sum()) for s in SCHEDS},
                    cpu_s_per_shot={s: SEC[s] / max(done, 1) for s in SCHEDS})
        json.dump(summ, open(os.path.join(outdir, f"{tag}.json"), "w"), indent=1)
        return summ

    with Pool(workers, initializer=init, initargs=(H, pri, layers)) as pool:
        while done < shots:
            n = min(batch * workers, shots - done)
            det, obs = sampler.sample(n, separate_observables=True)
            syn = det[:, P["z_rows"]].astype(np.uint8)
            parts = np.array_split(np.arange(n), workers)
            for res, idx in zip(pool.map(work, [syn[i] for i in parts]), parts):
                ob = obs[idx].astype(np.int64)
                for s in SCHEDS:
                    r = res[s]
                    pred = (r["dec"].astype(np.int64) @ O.T.astype(np.int64)) % 2
                    T[s]["it"].append(r["it"]); T[s]["ok"].append(r["ok"]); T[s]["crc"].append(r["crc"])
                    T[s]["fail"].append(np.any(pred != ob, axis=1))
                    SEC[s] += r["sec"]
            done += n; nb += 1
            if nb % 5 == 0 or done >= shots:
                summ = save()
                print(json.dumps(dict(shots=done, wall_s=summ["wall_s"], fails=summ["fails"])), flush=True)
    print("DONE", tag, flush=True)


def report(outdir, dir1b):
    tags = sorted({f.split("_")[0] for f in os.listdir(outdir) if f.startswith("p0.") and f.endswith(".npz")},
                  reverse=True)
    out = {}
    for tag in tags:
        J = json.load(open(os.path.join(outdir, f"{tag}.json")))
        D = {s: dict(np.load(os.path.join(outdir, f"{tag}_{s}.npz"))) for s in SCHEDS}
        R = dict(shots=J["shots"], layers=J["layers"], ler={}, paired_vs_sweep={}, iterations={},
                 cpu_s_per_shot=J["cpu_s_per_shot"])
        for s, d in D.items():
            fl = d["logical_fail"]; it = d["iterations"]
            R["ler"][s] = dict(fails=int(fl.sum()), ler=float(fl.mean()), hit_cap=int(d["hit_cap"].sum()),
                               not_converged=int((~d["success"]).sum()))
            R["iterations"][s] = dict(mean=float(it.mean()), p50=float(np.percentile(it, 50)),
                                      p90=float(np.percentile(it, 90)), p99=float(np.percentile(it, 99)),
                                      p99_9=float(np.percentile(it, 99.9)), max=int(it.max()))
        base = D["sweep"]["logical_fail"]
        for s in SCHEDS[1:]:
            q = D[s]["logical_fail"]
            b, c = int(np.sum(base & ~q)), int(np.sum(~base & q))
            R["paired_vs_sweep"][s] = dict(both=int(np.sum(base & q)), only_sweep=b, only_other=c,
                                           mcnemar_p=mcnemar(b, c))
        a, b2 = D["rb13"], D["rb2"]
        R["rb13_vs_rb2"] = dict(shots=len(a["iterations"]),
                                decoding_differ=int(np.sum(a["dec_crc"] != b2["dec_crc"])),
                                iterations_differ=int(np.sum(a["iterations"] != b2["iterations"])),
                                success_differ=int(np.sum(a["success"] != b2["success"])),
                                logical_fail_differ=int(np.sum(a["logical_fail"] != b2["logical_fail"])))
        fn = os.path.join(dir1b, f"{tag}_{FMT}_sweep.npz")
        if os.path.exists(fn):
            e = np.load(fn); d = D["sweep"]; n = min(len(e["iterations"]), len(d["iterations"]))
            R["sweep_vs_test1b"] = dict(shots_compared=n,
                                        iterations_differ=int(np.sum(e["iterations"][:n] != d["iterations"][:n])),
                                        logical_fail_differ=int(np.sum(e["logical_fail"][:n] != d["logical_fail"][:n])),
                                        success_differ=int(np.sum(e["success"][:n] != d["success"][:n])))
        out[tag] = R
    json.dump(out, open(os.path.join(outdir, "report.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    m = sys.argv[1]
    if m == "hcheck":
        res = hcheck(sys.argv[2])
        if len(sys.argv) > 3:
            json.dump(res, open(sys.argv[3], "w"), indent=1)
    elif m == "run":
        run(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7])
    elif m == "report":
        report(sys.argv[2], sys.argv[3])
