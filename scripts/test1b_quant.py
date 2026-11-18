"""Idea 1, Test 1b: quantization. Relay-BP with hardware-sized integers, round sweep and flooding.

Decoder: relay_bp.RelayDecoderF32 with the added options check_layers (13 layers = sweep, none = flooding) and
quant ("none" = f32 float, "int4.2.8", "int6.4.8", "wide"). Integer values are exact in f32.
Parameters (Test 2b): alpha = None (alpha = 1), gamma0 = 0.125, gamma interval (-0.226, 0.622), pre_iter 80,
300 legs x 60, stop_nconv S = 1, cap 18,080. Sampler seed 20261111 (shots as in Test 2b).

Modes:
  sanity <circuit_p0.003> <outdir>                 wide vs float (1,000 shots); flood vs 1-layer (300 shots)
  run <circuit> <tag> <shots> <workers> <batch> <outdir>
  report <outdir>                                   summary tables from the run JSON/npz files
"""
import sys, os, json, time
import numpy as np

GAMMA0 = 0.125
INTERVAL = (-0.22628432386414646, 0.6216020925981884)
PRE, LEGS, LEG_IT = 80, 300, 60
CAP = PRE + LEGS * LEG_IT
FORMATS = ("float", "int4.2.8", "int6.4.8")
SCHEDS = ("sweep", "flood")
_G = {}


def make(H, pri, layers, fmt, sched):
    import relay_bp
    kw = dict(alpha=None, gamma0=GAMMA0, pre_iter=PRE, num_sets=LEGS, set_max_iter=LEG_IT,
              gamma_dist_interval=INTERVAL, stop_nconv=1, seed=0, quant="none" if fmt == "float" else fmt)
    if sched == "sweep":
        kw["check_layers"] = [int(x) for x in layers]
    elif sched == "one_layer":
        kw["check_layers"] = [0] * H.shape[0]
    return relay_bp.RelayDecoderF32(H, error_priors=pri, **kw)


def first_leg(it, ok):
    """Leg index of the first solution (0 = pre-iteration leg), -1 if none. Exact for S = 1: every failed leg runs
    to its full length, so total = 80 + 60 (k - 1) + i_k for a solution in leg k >= 1."""
    leg = np.where(it <= PRE, 0, 1 + (it - PRE - 1) // LEG_IT)
    return np.where(ok, leg, -1)


def gamma_grid():
    lo, hi = INTERVAL
    out = {}
    for g in range(-8, 9):
        a, b = max(lo, (g - 0.5) / 8), min(hi, (g + 0.5) / 8)   # round half up: g <=> 8*gamma in [g-1/2, g+1/2)
        if b > a:
            out[f"{g}/8"] = (b - a) / (hi - lo)
    return out


# ---------------------------------------------------------------- sanity
def sanity(path, outdir):
    from dem_tools import xdecoder_problem
    P = xdecoder_problem(path)
    H, pri, layers = P["H"], P["priors"], P["layers"]
    det, _ = P["circuit"].compile_detector_sampler(seed=20261111).sample(1000, separate_observables=True)
    syn = det[:, P["z_rows"]].astype(np.uint8)
    res = {}
    for sched in SCHEDS:
        rf = make(H, pri, layers, "float", sched).decode_detailed_batch(syn)
        rw = make(H, pri, layers, "wide", sched).decode_detailed_batch(syn)
        dd = sum(int(np.sum(a.decoding != b.decoding)) for a, b in zip(rf, rw))
        ds = sum(int(not np.array_equal(a.decoding, b.decoding)) for a, b in zip(rf, rw))
        di = sum(int(a.iterations != b.iterations) for a, b in zip(rf, rw))
        dc = sum(int(a.success != b.success) for a, b in zip(rf, rw))
        res[f"wide_vs_float_{sched}"] = dict(shots=1000, differing_decisions=dd, shots_with_different_decoding=ds,
                                             shots_with_different_iterations=di, shots_with_different_convergence=dc)
        print(f"wide vs float, {sched}, 1000 shots: differing decisions {dd} (bits), shots with different decoding "
              f"{ds}, different iterations {di}, different convergence {dc}", flush=True)
    s3 = syn[:300]
    for fmt in ("float", "int4.2.8"):
        a = make(H, pri, layers, fmt, "flood").decode_detailed_batch(s3)
        b = make(H, pri, layers, fmt, "one_layer").decode_detailed_batch(s3)
        same = dict(decoding=all(np.array_equal(x.decoding, y.decoding) for x, y in zip(a, b)),
                    iterations=all(x.iterations == y.iterations for x, y in zip(a, b)),
                    posteriors=all(np.array_equal(x.posterior_ratios, y.posterior_ratios) for x, y in zip(a, b)))
        if fmt != "float":
            same["sat_counts"] = all(x.quant_counts == y.quant_counts for x, y in zip(a, b))
        res[f"flood_vs_1layer_{fmt}"] = dict(shots=300, **same)
        print(f"{fmt}: flooding vs 1 layer, 300 shots, bit-identical: {same}", flush=True)
    res["gamma_grid_probabilities"] = gamma_grid()
    json.dump(res, open(os.path.join(outdir, "sanity.json"), "w"), indent=1)
    print("SANITY DONE", flush=True)


# ---------------------------------------------------------------- run
def init(H, pri, layers):
    for f in FORMATS:
        for s in SCHEDS:
            _G[(f, s)] = make(H, pri, layers, f, s)


def work(syn):
    out = {}
    for key, dec in _G.items():
        t0 = time.time()
        r = dec.decode_detailed_batch(syn)
        qc = np.array([x.quant_counts for x in r], dtype=np.int64).sum(0) if key[0] != "float" else None
        out[key] = dict(dec=np.array([x.decoding for x in r], dtype=np.uint8),
                        it=np.array([x.iterations for x in r], dtype=np.int32),
                        ok=np.array([x.success for x in r]), qc=qc, sec=time.time() - t0)
    return out


def run(path, tag, shots, workers, batch, outdir):
    from multiprocessing import Pool
    from dem_tools import xdecoder_problem
    P = xdecoder_problem(path)
    H, pri, O, layers = P["H"], P["priors"], P["O"], P["layers"]
    sampler = P["circuit"].compile_detector_sampler(seed=20261111)
    keys = [(f, s) for f in FORMATS for s in SCHEDS]
    T = {k: dict(it=[], ok=[], fail=[]) for k in keys}
    QC = {k: np.zeros(8, dtype=np.int64) for k in keys if k[0] != "float"}
    SEC = {k: 0.0 for k in keys}
    t_start, done, nb = time.time(), 0, 0

    def save():
        for (f, s) in keys:
            it = np.concatenate(T[(f, s)]["it"]); ok = np.concatenate(T[(f, s)]["ok"])
            fail = np.concatenate(T[(f, s)]["fail"])
            np.savez_compressed(os.path.join(outdir, f"{tag}_{f}_{s}.npz"), iterations=it, success=ok,
                                first_leg=first_leg(it, ok), hit_cap=(it >= CAP) & ~ok, logical_fail=fail)
        summ = dict(tag=tag, shots=done, wall_s=round(time.time() - t_start, 1),
                    fails={f"{f}_{s}": int(np.concatenate(T[(f, s)]["fail"]).sum()) for f, s in keys},
                    cpu_s_per_shot={f"{f}_{s}": SEC[(f, s)] / max(done, 1) for f, s in keys},
                    quant_counts={f"{f}_{s}": QC[(f, s)].tolist() for f, s in QC})
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
                for k in keys:
                    r = res[k]
                    pred = (r["dec"].astype(np.int64) @ O.T.astype(np.int64)) % 2
                    T[k]["it"].append(r["it"]); T[k]["ok"].append(r["ok"])
                    T[k]["fail"].append(np.any(pred != ob, axis=1))
                    SEC[k] += r["sec"]
                    if r["qc"] is not None:
                        QC[k] += r["qc"]
            done += n; nb += 1
            if nb % 5 == 0 or done >= shots:
                summ = save()
                print(json.dumps(dict(shots=done, wall_s=summ["wall_s"], fails=summ["fails"])), flush=True)
    print("DONE", tag, flush=True)


# ---------------------------------------------------------------- report
def mcnemar(b, c):
    from math import comb
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    return min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n)


def report(outdir):
    tags = sorted({f.split("_")[0] for f in os.listdir(outdir) if f.startswith("p0.") and f.endswith(".npz")},
                  reverse=True)
    out = {}
    for tag in tags:
        D = {}
        for f in FORMATS:
            for s in SCHEDS:
                fn = os.path.join(outdir, f"{tag}_{f}_{s}.npz")
                if os.path.exists(fn):
                    D[(f, s)] = dict(np.load(fn))
        J = json.load(open(os.path.join(outdir, f"{tag}.json")))
        R = dict(shots=J["shots"], ler={}, paired={}, iterations={}, saturation={}, cpu_s_per_shot=J["cpu_s_per_shot"])
        for (f, s), d in D.items():
            fl = d["logical_fail"]; it = d["iterations"]
            R["ler"][f"{f}_{s}"] = dict(fails=int(fl.sum()), ler=float(fl.mean()), hit_cap=int(d["hit_cap"].sum()))
            R["iterations"][f"{f}_{s}"] = dict(
                mean=float(it.mean()), p50=float(np.percentile(it, 50)), p90=float(np.percentile(it, 90)),
                p99=float(np.percentile(it, 99)), p99_9=float(np.percentile(it, 99.9)),
                frac_gt_80=float(np.mean(it > 80)), frac_gt_1000=float(np.mean(it > 1000)))
        for s in SCHEDS:
            base = D[("float", s)]["logical_fail"]
            for f in FORMATS[1:]:
                q = D[(f, s)]["logical_fail"]
                b, c = int(np.sum(base & ~q)), int(np.sum(~base & q))
                R["paired"][f"{f}_{s}"] = dict(both=int(np.sum(base & q)), only_float=b, only_int=c, mcnemar_p=mcnemar(b, c))
            fl = D[("float", "flood")]["logical_fail"]; sw = D[("float", "sweep")]["logical_fail"]
        for f in FORMATS:
            a, b_ = D[(f, "flood")]["logical_fail"], D[(f, "sweep")]["logical_fail"]
            b, c = int(np.sum(a & ~b_)), int(np.sum(~a & b_))
            R["paired"][f"sweep_vs_flood_{f}"] = dict(both=int(np.sum(a & b_)), only_flood=b, only_sweep=c,
                                                      mcnemar_p=mcnemar(b, c))
        for k, v in J["quant_counts"].items():
            v = np.array(v, dtype=float)
            R["saturation"][k] = dict(c2v_clipped=v[1] / v[0], v2c_clipped=v[3] / v[2], marginal_clipped=v[5] / v[4],
                                      bias_clipped=v[7] / v[6], updates=dict(c2v=int(v[0]), v2c=int(v[2]),
                                                                             marginal=int(v[4]), bias=int(v[6])))
        out[tag] = R
    json.dump(out, open(os.path.join(outdir, "report.json"), "w"), indent=1)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    m = sys.argv[1]
    if m == "sanity":
        sanity(sys.argv[2], sys.argv[3])
    elif m == "run":
        run(sys.argv[2], sys.argv[3], int(sys.argv[4]), int(sys.argv[5]), int(sys.argv[6]), sys.argv[7])
    elif m == "report":
        report(sys.argv[2])
