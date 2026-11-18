"""Fig. 8(a) real-time target lines (ns per 13-round iteration) with the exact red-black cycle model of
review_queue.py / queue_table4.json.

Service per job: (2 + 13 n + 13 * leg ends + 12) cycles = t_it * (n + (14 + 13 * leg ends) / 13), with t_it = 13 cycles,
leg ends = legs - 1, legs = 1 if n <= 80 else 1 + ceil((n - 80) / 60). It is fed to test1e_queue.lindley (unchanged)
as an "effective iteration count" x = n + (14 + 13 * leg ends) / 13 with overhead 0 and no extra cap (n already <= 18,080).
Jobs: test1e_criteria.seq resampling (seed 20261112, 10^7 jobs), T = 12 us.
Criteria exactly as test1e_criteria.ok:
  thr. (a): utilization < 0.7 and queue max < 1000 jobs
  1 ms (c): utilization < 1 and p99.9 latency < 1 ms
Search: largest t_it on a 0.1 ns grid that meets the criterion (bisection between 0.1 ns and the utilization bound).
Check: the old model (n * t_it + 200 ns, 1 ns search) is also run and must reproduce the current lines 62 / 134 / 282 / 524.
Traces: rb13 int4.2.8, Test 1g (p = 0.003, 0.002) and the fresh p = 0.003 set (Test 1h step 2).
Output: results/review_fixes/fig8_lines.json (printed).
"""
import os, json
import numpy as np
from test1e_criteria import JOBS, SEED, K
from test1e_queue import Sim

R = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "results")
T_US, ENG = 12.0, 61.88
TRACES = {"0.003": "test1g/p0.003_rb13.npz", "0.002": "test1g/p0.002_rb13.npz",
          "0.003 fresh": "test1h/step2/p0.003_rb13_int4.npz"}


def resample(a):
    idx = np.random.default_rng(SEED).integers(0, a.shape[0], JOBS)
    return np.ascontiguousarray(a[idx])


def ok(sim, c, t, ov):
    r = sim.run(np.inf if ov == 0 else K, t, ov, T_US, full=True)
    good = (r["util"] < 0.7 and r["queue_max"] < 1000) if c == "a" else (r["util"] < 1 and r["lat_p999_us"] < 1000.0)
    return good, r


def search(sim, c, ov, mean_x, step):
    cap = 0.7 if c == "a" else 1.0
    hi = np.floor(((cap * T_US * 1000 - ov) / mean_x - 1e-9) / step)          # grid index, utilization bound
    lo = 1
    if not ok(sim, c, lo * step, ov)[0]:
        return None
    if ok(sim, c, hi * step, ov)[0]:
        lo = hi
    else:
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if ok(sim, c, mid * step, ov)[0]: lo = mid
            else: hi = mid
    t = round(lo * step, 1); g, r = ok(sim, c, t, ov); b, rb = ok(sim, c, round(t + step, 1), ov)
    assert g and not b
    return dict(t_it_ns=t, util=r["util"], lat_p999_us=r["lat_p999_us"], queue_max=r["queue_max"],
                next_step=dict(t_it_ns=round(t + step, 1), util=rb["util"], lat_p999_us=rb["lat_p999_us"],
                               queue_max=rb["queue_max"]))


def main():
    out = dict(T_us=T_US, engine_ns=ENG, criteria={"a (thr.)": "util < 0.7 and queue max < 1000",
                                                   "c (1 ms)": "util < 1 and p99.9 < 1 ms"}, rows=[])
    for name, f in TRACES.items():
        n = np.load(os.path.join(R, f))["iterations"].astype(np.int64)
        le = np.where(n <= 80, 1, 1 + -(-(n - 80) // 60)) - 1
        x = resample(n + (14 + 13 * le) / 13.0)
        sim_new = Sim(x); sim_old = Sim(resample(n))
        for c in (("a", "c") if name != "0.003 fresh" else ("c",)):
            new = search(sim_new, c, 0.0, float(x.mean()), 0.1)
            old = search(sim_old, c, 200.0, float(np.minimum(n, K).mean()), 1.0)
            out["rows"].append(dict(trace=name, crit=c, exact=new, old_model_check=old,
                                    engine_side=("left (meets)" if new and ENG <= new["t_it_ns"] else "right (misses)")))
            print(name, c, "exact", new["t_it_ns"] if new else None, "old", old["t_it_ns"] if old else None, flush=True)
    json.dump(out, open(os.path.join(R, "review_fixes", "fig8_lines.json"), "w"), indent=1, default=float)
    print(json.dumps(out, indent=1, default=float))


if __name__ == "__main__":
    main()
