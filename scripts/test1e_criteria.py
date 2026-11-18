"""Idea 1, Test 1e criteria: Part C (largest t_iter, 1 ns search) under several real-time criteria, on existing
traces only (no decoding). Uses the Sim / Lindley model of test1e_queue.py with the same job resampling
(seed 20261112, 10^7 jobs), so criterion (b) reproduces the earlier Part C numbers.

Criteria (sweep, K uncapped = 18080, overhead 200 ns):
  a  throughput only: utilization < 0.7 and queue max < 1000 jobs
  b  p99.9 latency < 100 us     c  p99.9 < 1 ms     d  p99.9 < 10 ms
(b-d have no utilization condition; utilization at the answer is reported.)
IBM flood design: the flood trace at 24 ns / iteration, overhead 200 ns (12-round traces only).

Usage: python test1e_criteria.py OUTDIR [workers]
"""
import sys, os, json, time
import numpy as np
from multiprocessing import Pool
from test1e_queue import Sim

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
JOBS, SEED, K, OV, IBM_T = 10_000_000, 20261112, 18080, 200.0, 24.0
CRIT = {"a": "util < 0.7 and queue max < 1000", "b": "p99.9 < 100 us", "c": "p99.9 < 1 ms", "d": "p99.9 < 10 ms"}
LAT_US = {"b": 100.0, "c": 1000.0, "d": 10000.0}
# trace name -> (npz pattern, ps, Ts in us, rounds per job, has flood)
TRACES = {
    "1b float, 12 rounds": (ROOT + "/test1b/p{p}_float_{s}.npz", ["0.003", "0.002", "0.001"], [12.0, 8.0], 13, True),
    "1d global, 36 rounds": (ROOT + "/test1d/p{p}_global.npz", ["0.003", "0.002"], [36.0], 37, False),
    "1d W12_C8": (ROOT + "/test1d/p{p}_W12_C8.npz", ["0.003", "0.002"], [8.0], 12, False),
    "1d W8_C4": (ROOT + "/test1d/p{p}_W8_C4.npz", ["0.003", "0.002"], [4.0], 8, False),
}


def seq(path):
    it = np.load(path)["iterations"].astype(np.int64)
    n = it.shape[0]; per = it.shape[1] if it.ndim == 2 else 1
    idx = np.random.default_rng(SEED).integers(0, n, -(-JOBS // per))
    return np.ascontiguousarray(it[idx].ravel()[:JOBS])


def ok(sim, c, t, T):
    r = sim.run(K, t, OV, T, full=True)
    good = (r["util"] < 0.7 and r["queue_max"] < 1000) if c == "a" else (r["util"] < 1 and r["lat_p999_us"] < LAT_US[c])
    return good, r


def search(sim, c, T, mean_it):
    cap = 0.7 if c == "a" else 1.0
    hi = float(np.floor((cap * T * 1000 - OV) / mean_it - 1e-9))   # utilization bound (strict)
    if hi < 1 or not ok(sim, c, 1.0, T)[0]:
        return None, None, "fails at 1 ns"
    if ok(sim, c, hi, T)[0]:
        lo, binding = hi, ("utilization < 0.7" if c == "a" else "stability (util < 1)")
    else:
        lo = 1.0
        while hi - lo > 1:
            mid = np.floor((lo + hi) / 2)
            if ok(sim, c, mid, T)[0]: lo = mid
            else: hi = mid
        binding = "queue max" if c == "a" else "p99.9 latency"
    return lo, ok(sim, c, lo, T)[1], binding


def job(arg):
    name, p = arg
    pat, _, Ts, rounds, flood = TRACES[name]
    sw = seq(pat.format(p=p, s="sweep")); sim = Sim(sw); mean_it = float(np.minimum(sw, K).mean())
    simf = Sim(seq(pat.format(p=p, s="flood"))) if flood else None
    rows = []
    for T in Ts:
        ibm = simf.run(K, IBM_T, OV, T, full=True) if flood else None
        for c in CRIT:
            t, r, b = search(sim, c, T, mean_it)
            row = dict(trace=name, p=p, T_us=T, crit=c, rounds=rounds, t_iter_max_ns=t, binding=b,
                       per_round_ns=(t / rounds if t else None), util=r and r["util"],
                       lat_p999_us=r and r["lat_p999_us"], queue_max=r and r["queue_max"])
            if flood:
                row["ibm_meets"] = bool(ok(simf, c, IBM_T, T)[0])
                row["ibm"] = dict(util=ibm["util"], lat_p999_us=ibm["lat_p999_us"], queue_max=ibm["queue_max"])
            rows.append(row)
    print(f"{name} p = {p}: done", flush=True)
    return rows


def main():
    out = sys.argv[1]; workers = int(sys.argv[2]) if len(sys.argv) > 2 else 2
    os.makedirs(out, exist_ok=True); t0 = time.time()
    with Pool(workers) as pool:
        rows = sum(pool.map(job, [(n, p) for n, v in TRACES.items() for p in v[1]]), [])
    json.dump(dict(rows=rows, criteria=CRIT, K=K, overhead_ns=OV, jobs=JOBS, seed=SEED, seconds=time.time() - t0),
              open(os.path.join(out, "criteria.json"), "w"), indent=1, default=float)
    print(f"DONE in {time.time() - t0:.0f} s")


if __name__ == "__main__":
    main()
