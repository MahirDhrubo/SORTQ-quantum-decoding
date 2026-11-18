"""Review fixes, parts A.2 and A.3: queue model with the exact measured cycle formulas instead of iterations x t_iter
+ 200 ns overhead.

Queue: test1e_queue.lindley unchanged (FIFO, one engine, a job every T, W(n+1) = max(0, W(n) + S(n) - T), latency =
W + S, 10^7 jobs resampled from the trace with seed 20261112 as test1e_criteria.seq; 2-D traces = windows in time order).
Service time S per job (decode or window), n = iterations, legs = 1 if n <= 80 else 1 + ceil((n - 80) / 60),
leg ends = legs - 1:
  red-black engine_top_rb (measured, hw/summary_2f.md: exact for all 506 shots):
      cycles = 2 + P(L) * n + 13 * leg ends + 12, clock period 4.76 ns (210.1 MHz, post-route);
      L = detector layers of the job; P(L) = cycles per iteration = L when every pair of steps sharing an error is
      >= 5 slots apart in the red-black order (cyclic), otherwise the smallest period with idle slots
      (hw/rb/gen/gen_rb_pkg.min_period). The constants 2, 13 and 12 were measured with L = 13 (pipeline depth and the
      5-cycle convergence check, which is also 5 cycles for 864 detectors); they are assumed for other L.
  sweep engine_top_pf2fix (measured, hw/summary_3d.md: 14 + 1 + 26 n + 10 leg ends + 10), clock period 7.24 ns.
  fully parallel [25]: n * 24 ns; no start, leg-end or end overhead (none is reported in [25]; assumption, favourable
      to [25]).
Modes:
  table4    12-round traces, T = 12 us: fully parallel = int4.2.8 flooding (Test 1b), sweep = int4.2.8 sweep (Test 1b),
            red-black = rb13 (Test 1g; p = 0.001 eval run; fresh and pooled sets at p = 0.003)
  windows   results/review_fixes/windows/p{p}_W12_C8.npz, T = C = 8 us (red-black, per-window L)
Output: results/review_fixes/queue_<mode>.json (printed).
"""
import sys, os, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE); sys.path.insert(0, os.path.join(HERE, "..", "hw", "rb", "gen"))
import test1e_criteria as C                                 # noqa: E402
from test1e_queue import Sim                                # noqa: E402
from gen_rb_pkg import min_period                           # noqa: E402

R = os.path.join(HERE, "..", "results")
OUT = os.path.join(R, "review_fixes")
T_RB, T_SW, T_FP = 4.76, 7.24, 24.0


def leg_ends(n):
    n = np.asarray(n, dtype=np.int64)
    legs = np.where(n <= 80, 1, 1 + -(-(n - 80) // 60))
    return legs - 1


def period(L):
    pairs = [(a, b) for a, b in ((r, r + 1) for r in range(L - 1))]
    order = list(range(0, L, 2)) + list(range(1, L, 2)); pos = {r: i for i, r in enumerate(order)}
    return min_period(L, sorted((min(pos[a], pos[b]), max(pos[a], pos[b])) for a, b in pairs), 5)


def svc_rb(n, L):
    P = period(L)["cycles_per_iteration"]
    return (2 + P * np.asarray(n, np.int64) + 13 * leg_ends(n) + 12) * T_RB


def svc_sw(n):
    return (15 + 26 * np.asarray(n, np.int64) + 10 * leg_ends(n) + 10) * T_SW


def svc_fp(n):
    return np.asarray(n, np.int64) * T_FP


def queue(svc_ns, T_us):
    """svc_ns: shots (x windows) service times in ns -> 10^7 jobs as test1e_criteria.seq, lindley in ps units."""
    a = np.rint(np.asarray(svc_ns) * 1000).astype(np.int64)
    per = a.shape[1] if a.ndim == 2 else 1
    idx = np.random.default_rng(C.SEED).integers(0, a.shape[0], -(-C.JOBS // per))
    seq = np.ascontiguousarray(a[idx].ravel()[:C.JOBS])
    r = Sim(seq).run(np.int64(2) ** 62, 0.001, 0.0, T_us, full=True)
    return dict(util=r["util"], lat_p999_us=r["lat_p999_us"], lat_p99_us=r["lat_p99_us"], queue_max=r["queue_max"],
                mean_service_ns=float(np.asarray(svc_ns).mean()), stable=r["stable"])


def table4():
    t1b = lambda p, s: np.load(os.path.join(R, "test1b", f"p{p}_{s}.npz"))["iterations"]
    rb = {"0.003": os.path.join(R, "test1g", "p0.003_rb13.npz"), "0.002": os.path.join(R, "test1g", "p0.002_rb13.npz"),
          "0.001": os.path.join(R, "test1g", "p001", "p0.001_rb13.npz")}
    out = dict(rb_period_13=period(13), rows=[])
    for p in ("0.003", "0.002", "0.001"):
        fl = t1b(p, "int4.2.8_flood"); sw = t1b(p, "int4.2.8_sweep"); r13 = np.load(rb[p])["iterations"]
        for name, s in (("fully parallel (int4.2.8 flooding, 24 ns/iteration)", svc_fp(fl)),
                        ("SORTQ sweep (exact cycles, 7.24 ns)", svc_sw(sw)),
                        ("SORTQ red-black (exact cycles, 4.76 ns)", svc_rb(r13, 13))):
            out["rows"].append(dict(design=name, p=p, **queue(s, 12.0)))
        out["rows"][-3]["busy_fraction_fig2"] = float(fl.mean() * 24 / 12000)
        out["rows"][-3]["mean_iterations_int4_flood"] = float(fl.mean())
    fr = np.load(os.path.join(R, "test1h", "step2", "p0.003_rb13_int4.npz"))["iterations"]
    pooled = np.concatenate([np.load(rb["0.003"])["iterations"], fr])
    out["rows"].append(dict(design="SORTQ red-black, fresh shots", p="0.003", **queue(svc_rb(fr, 13), 12.0)))
    out["rows"].append(dict(design="SORTQ red-black, pooled", p="0.003", **queue(svc_rb(pooled, 13), 12.0)))
    return out


def windows():
    out = dict(rows=[])
    for p in ("0.003", "0.002"):
        f = os.path.join(R, "review_fixes", "windows", f"p{p}_W12_C8.npz")
        if not os.path.exists(f):
            continue
        d = np.load(f); it = d["iterations"]; Ls = d["window_layers"]
        per = {int(L): period(int(L)) for L in set(Ls.tolist())}
        svc = np.stack([svc_rb(it[:, k], int(Ls[k])) for k in range(it.shape[1])], axis=1)
        le = leg_ends(it)
        out["rows"].append(dict(p=p, shots=int(it.shape[0]), window_layers=Ls.tolist(),
                                period_by_layers={str(k): v for k, v in per.items()},
                                per_window_mean_iterations=it.mean(0).tolist(),
                                per_window_p999_iterations=np.percentile(it, 99.9, axis=0).tolist(),
                                per_window_max_iterations=it.max(0).tolist(),
                                per_window_frac_relay=(it > 80).mean(0).tolist(),
                                per_window_mean_leg_ends=le.mean(0).tolist(),
                                per_window_max_leg_ends=le.max(0).tolist(),
                                per_window_mean_service_ns=svc.mean(0).tolist(),
                                **queue(svc, 8.0)))
    return out


if __name__ == "__main__":
    m = sys.argv[1]
    res = table4() if m == "table4" else windows()
    os.makedirs(OUT, exist_ok=True)
    json.dump(res, open(os.path.join(OUT, f"queue_{m}.json"), "w"), indent=1, default=float)
    print(json.dumps(res, indent=1, default=float))
