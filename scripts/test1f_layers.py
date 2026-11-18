"""Idea 1, Test 1f: accuracy and iterations when k consecutive check rounds form one layer.

Decoder exactly as Test 1b int4.2.8 (test1b_quant.make): relay_bp.RelayDecoderF32, quant int4.2.8, alpha = 1 (None),
S = 1, gamma0 = 0.125, gamma interval (-0.226, 0.622), pre_iter 80, 300 legs x 60, cap 18,080; 12-round circuit,
X decoder. Sampler seed 20261111: the same shots as Test 1b, and every schedule decodes the same shots.
Schedules (check_layers = layer index per check row; rows' round r = 0..12 from dem_tools.layers):
  k1 = r (13 layers, = Test 1b sweep), k2 = r // 2 (7 layers), k3 = r // 3 (5), k4 = r // 4 (4)
  (consecutive rounds grouped, the last group smaller), flood = no check_layers (= Test 1b flood).
Iteration = one pass over all layers (as in Test 1b).

Modes:
  run <circuit> <tag> <shots> <workers> <batch> <outdir>   per-shot traces <tag>_<sched>.npz (Test 1b format:
                                                             iterations, success, first_leg, hit_cap, logical_fail)
  report <outdir> <test1b_dir>                              report.json: LER, paired vs k1 (McNemar), iterations
                                                             (mean, p50, p90, p99, p99.9, max); k1 / flood shot by
                                                             shot against the Test 1b int4.2.8 sweep / flood traces
"""
import sys, os, json, time
import numpy as np
from test1b_quant import PRE, LEG_IT, CAP, GAMMA0, INTERVAL, LEGS, first_leg, mcnemar

SCHEDS = ("k1", "k2", "k3", "k4", "flood")
FMT = "int4.2.8"
_G = {}


def check_layers(layers, sched):
    if sched == "flood":
        return None
    k = int(sched[1:])
    return [int(x) // k for x in layers]


def make(H, pri, layers, sched):
    import relay_bp
    kw = dict(alpha=None, gamma0=GAMMA0, pre_iter=PRE, num_sets=LEGS, set_max_iter=LEG_IT,
              gamma_dist_interval=INTERVAL, stop_nconv=1, seed=0, quant=FMT)
    cl = check_layers(layers, sched)
    if cl is not None:
        kw["check_layers"] = cl
    return relay_bp.RelayDecoderF32(H, error_priors=pri, **kw)


def init(H, pri, layers):
    for s in SCHEDS:
        _G[s] = make(H, pri, layers, s)


def work(syn):
    out = {}
    for s, dec in _G.items():
        t0 = time.time()
        r = dec.decode_detailed_batch(syn)
        out[s] = dict(dec=np.array([x.decoding for x in r], dtype=np.uint8),
                      it=np.array([x.iterations for x in r], dtype=np.int32),
                      ok=np.array([x.success for x in r]), sec=time.time() - t0)
    return out


def run(path, tag, shots, workers, batch, outdir):
    from multiprocessing import Pool
    from dem_tools import xdecoder_problem
    os.makedirs(outdir, exist_ok=True)
    P = xdecoder_problem(path)
    H, pri, O, layers = P["H"], P["priors"], P["O"], P["layers"]
    nl = {s: (len(set(check_layers(layers, s))) if s != "flood" else 1) for s in SCHEDS}
    sampler = P["circuit"].compile_detector_sampler(seed=20261111)
    T = {s: dict(it=[], ok=[], fail=[]) for s in SCHEDS}
    SEC = {s: 0.0 for s in SCHEDS}
    t_start, done, nb = time.time(), 0, 0

    def save():
        for s in SCHEDS:
            it = np.concatenate(T[s]["it"]); ok = np.concatenate(T[s]["ok"]); fail = np.concatenate(T[s]["fail"])
            np.savez_compressed(os.path.join(outdir, f"{tag}_{s}.npz"), iterations=it, success=ok,
                                first_leg=first_leg(it, ok), hit_cap=(it >= CAP) & ~ok, logical_fail=fail)
        summ = dict(tag=tag, shots=done, wall_s=round(time.time() - t_start, 1), layers=nl,
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
                    T[s]["it"].append(r["it"]); T[s]["ok"].append(r["ok"])
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
        R = dict(shots=J["shots"], layers=J["layers"], ler={}, paired_vs_k1={}, iterations={},
                 cpu_s_per_shot=J["cpu_s_per_shot"], vs_test1b={})
        for s, d in D.items():
            fl = d["logical_fail"]; it = d["iterations"]
            R["ler"][s] = dict(fails=int(fl.sum()), ler=float(fl.mean()), hit_cap=int(d["hit_cap"].sum()),
                               not_converged=int((~d["success"]).sum()))
            R["iterations"][s] = dict(mean=float(it.mean()), p50=float(np.percentile(it, 50)),
                                      p90=float(np.percentile(it, 90)), p99=float(np.percentile(it, 99)),
                                      p99_9=float(np.percentile(it, 99.9)), max=int(it.max()))
        base = D["k1"]["logical_fail"]
        for s in SCHEDS[1:]:
            q = D[s]["logical_fail"]
            b, c = int(np.sum(base & ~q)), int(np.sum(~base & q))
            R["paired_vs_k1"][s] = dict(both=int(np.sum(base & q)), only_k1=b, only_other=c, mcnemar_p=mcnemar(b, c))
        for s, s1b in (("k1", "sweep"), ("flood", "flood")):
            fn = os.path.join(dir1b, f"{tag}_{FMT}_{s1b}.npz")
            if os.path.exists(fn):
                e = np.load(fn); d = D[s]; n = min(len(e["iterations"]), len(d["iterations"]))
                R["vs_test1b"][s] = dict(
                    shots_compared=n, test1b_trace=os.path.basename(fn),
                    iterations_differ=int(np.sum(e["iterations"][:n] != d["iterations"][:n])),
                    logical_fail_differ=int(np.sum(e["logical_fail"][:n] != d["logical_fail"][:n])),
                    success_differ=int(np.sum(e["success"][:n] != d["success"][:n])))
        out[tag] = R
    json.dump(out, open(os.path.join(outdir, "report.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    m = sys.argv[1]
    if m == "run":
        run(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7])
    elif m == "report":
        report(sys.argv[2], sys.argv[3])
