"""Idea 1, Test 1e: iteration caps (Part A), FIFO queue simulation (Part B) and the speed target (Part C),
from measured per-shot iteration traces. No decoding is done here.

Trace sources (per p and schedule), given as path patterns with {p} and {sched}:
  --npz PATTERN   .npz with 'iterations' and 'logical_fail' (Test 1b format) -> Parts A, B, C
  --npy PATTERN   .npy with iterations only (Test 2b / "1a")                 -> Parts B, C (no LER condition)
For each p the npz source is used if the file exists, else the npy one.
  --check-npy PATTERN   compare npz iterations shot by shot with these npy iterations (e.g. 1b float vs 1a)

Model (Part B): one engine, FIFO, a job (window) arrives every T us. Job iterations are resampled with replacement
from the per-shot trace (shots independent; the same resampled shot indices for every configuration, sweep and
flood alike). Service S = min(it, K) * t_iter + overhead. Lindley: W(n+1) = max(0, W(n) + S(n) - T); latency =
W + S. Queue length = number of earlier jobs still in the system when a job arrives.

Window traces (Test 1d): 'iterations' may be 2-D (shots x windows). Then a job = one window; Part A counts a shot as
failed if it failed or any of its windows needs more than K iterations; Part B resamples shots and feeds their
windows to the queue in time order. A flood trace is optional (sweep-only traces skip flood and IBM rows).
--Ts sets the arrival periods in us (default 12,8; for windows use C rounds x 1 us).

Usage: python test1e_queue.py --out DIR [--label "dry run"] [--ps 0.003,0.002,0.001] [--npz P] [--npy P]
                              [--check-npy P] [--jobs 10000000] [--workers 2]
"""
import argparse, os, json, time
import numpy as np
from numba import njit

KS = [50, 100, 200, 500, 1000, 18080]
TS_US = [12.0, 8.0]
T_ITER_NS = [25, 50, 100, 200, 400]
OVERHEADS_NS = [0, 200]
IBM_T_ITER = 24
QBINS = 2_000_000


@njit(cache=True)
def lindley(it, K, t_iter, ov, T, lat, dep, qhist):
    n = it.shape[0]
    W = 0.0
    Sprev = 0.0
    waits = 0
    sumS = 0.0
    j = 0
    qmax = 0
    for k in range(qhist.shape[0]):
        qhist[k] = 0
    for i in range(n):
        x = it[i]
        if x > K:
            x = K
        S = x * t_iter + ov
        if i > 0:
            W = W + Sprev - T
            if W < 0.0:
                W = 0.0
        if W > 0.0:
            waits += 1
        L = W + S
        lat[i] = L
        A = i * T
        dep[i] = A + L
        while dep[j] <= A:
            j += 1
        q = i - j
        if q > qmax:
            qmax = q
        qhist[min(q, qhist.shape[0] - 1)] += 1
        Sprev = S
        sumS += S
    return sumS / n, waits / n, qmax


class Sim:
    def __init__(self, it_seq):
        self.it = it_seq
        n = it_seq.shape[0]
        self.lat = np.empty(n); self.dep = np.empty(n); self.qh = np.zeros(QBINS, dtype=np.int64)

    def run(self, K, t_iter_ns, ov_ns, T_us, full=True):
        T = T_us * 1000.0
        mS, pw, qmax = lindley(self.it, K, float(t_iter_ns), float(ov_ns), T, self.lat, self.dep, self.qh)
        p999 = float(np.quantile(self.lat, 0.999)) / 1000
        if not full:
            return dict(util=mS / T, p999_us=p999)
        c = np.cumsum(self.qh)
        q999 = int(np.searchsorted(c, 0.999 * c[-1]))
        p50, p99 = (float(x) / 1000 for x in np.quantile(self.lat, [0.5, 0.99]))
        return dict(util=mS / T, p_wait=pw, queue_p999=q999, queue_max=int(qmax), lat_p50_us=p50, lat_p99_us=p99,
                    lat_p999_us=p999, lat_max_us=float(self.lat.max()) / 1000,
                    p_lat_gt_10us=float(np.mean(self.lat > 10_000)), p_lat_gt_100us=float(np.mean(self.lat > 100_000)),
                    stable=mS / T < 1.0)


def load(args, p):
    src = {}
    for s in ("sweep", "flood"):
        # a pattern without {sched} is a sweep-only trace (e.g. Test 1d windows)
        fz = args.npz.format(p=p, sched=s) if args.npz and (s == "sweep" or "{sched}" in args.npz) else None
        fy = args.npy.format(p=p, sched=s) if args.npy and (s == "sweep" or "{sched}" in args.npy) else None
        if fz and os.path.exists(fz):
            d = np.load(fz)
            src[s] = dict(it=d["iterations"].astype(np.int64), fail=d["logical_fail"].astype(bool), path=fz)
            assert src[s]["it"].shape[0] == src[s]["fail"].shape[0], "iterations and logical_fail must have one row per shot"
        elif fy and os.path.exists(fy):
            src[s] = dict(it=np.load(fy).astype(np.int64), fail=None, path=fy)
    return src


def part_a(src):
    out = {}
    for s, d in src.items():
        if d["fail"] is None:
            out[s] = "not available (no per-shot logical-fail data)"; continue
        it, f = d["it"], d["fail"]
        if it.ndim == 1:
            it = it[:, None]
        ler = float(f.mean())
        over = lambda K: np.any(it > K, axis=1)               # a shot exceeds K if any of its windows does
        out[s] = {str(K): dict(ler=float(np.mean(f & ~over(K)) + np.mean(over(K))),
                               ratio=(float(np.mean(f & ~over(K)) + np.mean(over(K))) / ler) if ler > 0 else None,
                               frac_gt_K=float(np.mean(over(K))),
                               frac_windows_gt_K=float(np.mean(it > K))) for K in KS}
        out[s]["uncapped_ler"] = ler; out[s]["fails"] = int(f.sum()); out[s]["shots"] = int(len(f))
    return out


def worker(job):
    p, s, it_seq, configs = job
    sim = Sim(it_seq)
    rows = []
    for (K, t, ov, T, kind) in configs:
        r = sim.run(K, t, ov, T)
        rows.append(dict(p=p, sched=s, kind=kind, K=K, t_iter_ns=t, overhead_ns=ov, T_us=T, **r))
    return rows


def refine(job):
    """Part C: largest t_iter (1 ns resolution) with util < 0.7 and p99.9 < 100 us, per K, for the sweep."""
    p, it_seq, cases = job
    sim = Sim(it_seq)
    out = []
    for (K, ov, T) in cases:
        mean_it = float(np.minimum(it_seq, K).mean())
        t_util = (0.7 * T * 1000 - ov) / mean_it              # util < 0.7  <=>  t < t_util
        lo, hi = 0.0, float(np.floor(t_util - 1e-9))
        if hi < 1 or sim.run(K, 1.0, ov, T, full=False)["p999_us"] >= 100:
            out.append(dict(p=p, K=K, overhead_ns=ov, T_us=T, t_iter_max_ns=None)); continue
        lo = 1.0
        if sim.run(K, hi, ov, T, full=False)["p999_us"] < 100:
            lo = hi
        else:
            while hi - lo > 1:
                mid = np.floor((lo + hi) / 2)
                if sim.run(K, mid, ov, T, full=False)["p999_us"] < 100:
                    lo = mid
                else:
                    hi = mid
        r = sim.run(K, lo, ov, T, full=False)
        out.append(dict(p=p, K=K, overhead_ns=ov, T_us=T, t_iter_max_ns=lo, util=r["util"], lat_p999_us=r["p999_us"],
                        binding="utilization" if lo == np.floor(t_util - 1e-9) else "p99.9 latency"))
    return out


def plots(res, out, label):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    C = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]          # categorical slots 1-4 (fixed order)
    ink, ink2, grid = "#0b0b0b", "#52514e", "#e4e3df"
    plt.rcParams.update({"font.size": 9, "axes.edgecolor": ink2, "axes.labelcolor": ink, "xtick.color": ink2,
                         "ytick.color": ink2, "axes.spines.top": False, "axes.spines.right": False})
    ps = list(res["partA"])
    pa = [p for p in ps if isinstance(res["partA"][p].get("sweep"), dict)]
    if pa:
        fig, axs = plt.subplots(1, len(pa), figsize=(3.6 * len(pa), 3.0), squeeze=False)
        for ax, p in zip(axs[0], pa):
            for c, s in zip(C, ("sweep", "flood")):
                if not isinstance(res["partA"][p].get(s), dict):
                    continue
                A = res["partA"][p][s]
                ax.plot(KS, [A[str(K)]["ler"] for K in KS], color=c, lw=2, marker="o", ms=4, label=s)
                ax.axhline(1.1 * A["uncapped_ler"], color=c, lw=1, ls=":")
            ax.set_xscale("log"); ax.set_yscale("log"); ax.grid(color=grid, lw=0.6)
            ax.set_title(f"p = {p}", color=ink); ax.set_xlabel("iteration cap K")
        axs[0][0].set_ylabel("LER(K)  (dotted: 1.1 x uncapped)")
        axs[0][0].legend(frameon=False)
        fig.suptitle(f"Test 1e: LER vs iteration cap{' [' + label + ']' if label else ''}", color=ink)
        fig.tight_layout(); fig.savefig(os.path.join(out, "ler_vs_K.png"), dpi=150); plt.close(fig)
    fig, axs = plt.subplots(1, len(ps), figsize=(3.6 * len(ps), 3.0), squeeze=False)
    rows = res["partB"]
    for ax, p in zip(axs[0], ps):
        k = 0
        for s in ("sweep", "flood"):
            for T in TS_US:
                sel = [r for r in rows if r["p"] == p and r["sched"] == s and r["T_us"] == T and r["K"] == 18080
                       and r["overhead_ns"] == 200 and r["kind"] == "grid"]
                sel.sort(key=lambda r: r["t_iter_ns"])
                ax.plot([r["t_iter_ns"] for r in sel], [r["lat_p999_us"] for r in sel], color=C[k], lw=2, marker="o",
                        ms=4, label=f"{s}, T = {T:g} us")
                k += 1
        for T, mk in zip(TS_US, ("s", "^")):
            b = [r for r in rows if r["p"] == p and r["kind"] == "ibm" and r["T_us"] == T and r["K"] == 18080
                 and r["overhead_ns"] == 200]
            if b:
                ax.plot([IBM_T_ITER], [b[0]["lat_p999_us"]], color=ink, marker=mk, ms=6, ls="none",
                        label=f"IBM flood 24 ns, T = {T:g} us")
        ax.axhline(100, color=ink2, lw=1, ls=":")
        ax.set_xscale("log"); ax.set_yscale("log"); ax.grid(color=grid, lw=0.6)
        ax.minorticks_off(); ax.set_xticks(T_ITER_NS); ax.set_xticklabels([str(x) for x in T_ITER_NS])
        ax.set_title(f"p = {p}", color=ink); ax.set_xlabel("t_iter (ns)")
    axs[0][0].set_ylabel("p99.9 latency (us)")
    h, l = axs[0][0].get_legend_handles_labels()
    fig.legend(h, l, loc="lower center", ncol=6, frameon=False, fontsize=7)
    fig.suptitle(f"Test 1e: p99.9 latency vs time per iteration (K uncapped, overhead 200 ns; dotted = 100 us)"
                 f"{' [' + label + ']' if label else ''}", color=ink, fontsize=9)
    fig.tight_layout(rect=(0, 0.08, 1, 1)); fig.savefig(os.path.join(out, "p999_latency_vs_titer.png"), dpi=150); plt.close(fig)


def fmt(x, nd=3):
    if x is None:
        return "–"
    if isinstance(x, float):
        if x == 0:
            return "0"
        return f"{x:.{nd}g}" if abs(x) < 1e4 else f"{x:.3g}"
    return str(x)


def best_c(res, p, T, ov):
    rows = [r for r in res["partC"] if r["p"] == p and r["T_us"] == T and r["overhead_ns"] == ov
            and r["t_iter_max_ns"] is not None]
    return max(rows, key=lambda r: (r["t_iter_max_ns"], -r["K"])) if rows else None


def write_tables(res, out):
    """Result tables (markdown) generated from the JSON; the interpretation is written separately."""
    L = [f"<!-- generated by test1e_queue.py{' [' + res['label'] + ']' if res['label'] else ''} -->"]
    if res["check"]:
        L += ["### Check: 1b float iterations vs 1a", "| p | schedule | shots compared | mismatches | match |",
              "|---|---|---|---|---|"]
        for p, d in res["check"].items():
            for s, c in d.items():
                L.append(f"| {p} | {s} | {c['compared']:,} | {c['mismatches']:,} | {'yes' if c['match'] else 'no'} |")
    L += ["", "### Part A: LER(K)"]
    for p, A in res["partA"].items():
        if not isinstance(A.get("sweep"), dict):
            L.append(f"- p = {p}: not available (no per-shot logical-fail data)."); continue
        sch = [s for s in ("sweep", "flood") if isinstance(A.get(s), dict)]
        L += [f"p = {p} ({A['sweep']['shots']:,} shots; uncapped: " + ", ".join(
              f"{s} {A[s]['fails']} fails = {fmt(A[s]['uncapped_ler'])}" for s in sch) + ")", "",
              "| K | " + " | ".join(f"{s} LER(K) | ratio | P(it > K)" for s in sch) + " |",
              "|---|" + "---|---|---|" * len(sch)]
        for K in KS:
            L.append(f"| {K} | " + " | ".join(f"{fmt(A[s][str(K)]['ler'])} | {fmt(A[s][str(K)]['ratio'])} | "
                                              f"{fmt(A[s][str(K)]['frac_gt_K'])}" for s in sch) + " |")
        L.append("")
    L += ["### Part C: speed target for the sweep (largest t_iter; util < 0.7, p99.9 < 100 us, LER(K) <= 1.1 x uncapped)",
          "| p | T (us) | overhead (ns) | best K | t_iter max, 1 ns search | t_iter max, grid | limited by | util | p99.9 (us) | LER ratio | LER condition |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in res["partA"]:
        for T in TS_US:
            for ov in OVERHEADS_NS:
                r = best_c(res, p, T, ov)
                if r is None:
                    L.append(f"| {p} | {T:g} | {ov} | none feasible | | | | | | | |"); continue
                L.append(f"| {p} | {T:g} | {ov} | {r['K']} | {r['t_iter_max_ns']:.0f} ns | {fmt(r['t_iter_max_grid_ns'])} | "
                         f"{r['binding']} | {fmt(r['util'])} | {fmt(r['lat_p999_us'])} | {fmt(r.get('ler_ratio'))} | "
                         f"{r['ler_condition']} |")
    L += ["", "Per K (sweep, overhead 200 ns): largest t_iter (ns), 1 ns search", "",
          "| p | T (us) | " + " | ".join(f"K = {K}" for K in KS) + " |", "|---|---|" + "---|" * len(KS)]
    for p in res["partA"]:
        for T in TS_US:
            cells = []
            for K in KS:
                r = [x for x in res["partC"] if x["p"] == p and x["T_us"] == T and x["overhead_ns"] == 200 and x["K"] == K]
                cells.append("excl. (LER)" if not r else ("none" if r[0]["t_iter_max_ns"] is None else f"{r[0]['t_iter_max_ns']:.0f}"))
            L.append(f"| {p} | {T:g} | " + " | ".join(cells) + " |")
    L += ["", "### Part B (selection; overhead 200 ns; all 792 configurations in queue_results.json)",
          "Rows: K uncapped (18080) and the Part C best K for the same p, T. 'unstable' = utilization >= 1.", ""]
    hdr = ("| p | T | design | K | t_iter | util | P(wait) | queue p99.9 / max | lat p50 | p99 | p99.9 | max (us) | "
           "P(>10us) | P(>100us) |")
    L += [hdr, "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for p in res["partA"]:
        for T in TS_US:
            bc = best_c(res, p, T, 200)
            Ksel = sorted({18080} | ({bc["K"]} if bc else set()))
            for K in Ksel:
                rows = [r for r in res["partB"] if r["p"] == p and r["T_us"] == T and r["K"] == K and r["overhead_ns"] == 200]
                rows.sort(key=lambda r: (r["kind"] != "ibm", r["sched"], r["t_iter_ns"]))
                for r in rows:
                    d = "IBM flood" if r["kind"] == "ibm" else r["sched"]
                    if not r["stable"]:
                        L.append(f"| {p} | {T:g} | {d} | {K} | {r['t_iter_ns']} | {fmt(r['util'])} | unstable | | | | | | | |")
                        continue
                    L.append(f"| {p} | {T:g} | {d} | {K} | {r['t_iter_ns']} | {fmt(r['util'])} | {fmt(r['p_wait'])} | "
                             f"{r['queue_p999']} / {r['queue_max']} | {fmt(r['lat_p50_us'])} | {fmt(r['lat_p99_us'])} | "
                             f"{fmt(r['lat_p999_us'])} | {fmt(r['lat_max_us'])} | {fmt(r['p_lat_gt_10us'])} | "
                             f"{fmt(r['p_lat_gt_100us'])} |")
    open(os.path.join(out, "tables.md"), "w").write("\n".join(L) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True); ap.add_argument("--label", default="")
    ap.add_argument("--ps", default="0.003,0.002,0.001"); ap.add_argument("--npz"); ap.add_argument("--npy")
    ap.add_argument("--check-npy"); ap.add_argument("--jobs", type=int, default=10_000_000)
    ap.add_argument("--workers", type=int, default=2); ap.add_argument("--seed", type=int, default=20261112)
    ap.add_argument("--from-json", help="only regenerate plots and tables from an existing queue_results.json")
    ap.add_argument("--Ts", default="12,8", help="arrival periods in us")
    args = ap.parse_args()
    global TS_US
    TS_US = [float(x) for x in args.Ts.split(",")]
    if args.from_json:
        res = json.load(open(args.from_json))
        plots(res, args.out, res["label"]); write_tables(res, args.out); print("tables + plots written"); return
    os.makedirs(args.out, exist_ok=True)
    t0 = time.time()
    tag = f"[{args.label}] " if args.label else ""
    res = dict(label=args.label, args=vars(args), partA={}, partB=[], partC=[], check={}, sources={})
    seqs = {}
    for p in args.ps.split(","):
        src = load(args, p)
        if "sweep" not in src:
            print(f"{tag}p = {p}: sweep trace missing, skipped", flush=True); continue
        n = len(src["sweep"]["it"])
        if "flood" in src:
            assert len(src["flood"]["it"]) == n, "sweep/flood traces must be paired"
        res["sources"][p] = {s: dict(path=d["path"], shots=len(d["it"]), has_fail=d["fail"] is not None)
                             for s, d in src.items()}
        if args.check_npy:
            res["check"][p] = {}
            for s in src:
                f = args.check_npy.format(p=p, sched=s)
                if os.path.exists(f) and src[s]["fail"] is not None:
                    ref = np.load(f).astype(np.int64); m = min(len(ref), n)
                    mis = int(np.sum(ref[:m] != src[s]["it"][:m]))
                    res["check"][p][s] = dict(compared=m, mismatches=mis, match=mis == 0 and len(ref) == n)
                    print(f"{tag}check p = {p} {s}: npz vs npy iterations, {mis} mismatches in {m} shots", flush=True)
        res["partA"][p] = part_a(src)
        rng = np.random.default_rng(args.seed)
        per_shot = src["sweep"]["it"].shape[1] if src["sweep"]["it"].ndim == 2 else 1
        idx = rng.integers(0, n, -(-args.jobs // per_shot))   # same shots for sweep and flood (paired)
        seqs[p] = {s: np.ascontiguousarray(src[s]["it"][idx].ravel()[:args.jobs]) for s in src}
    # Part B
    jobs = []
    for p in seqs:
        for s in seqs[p]:
            cfg = [(K, t, ov, T, "grid") for K in KS for t in T_ITER_NS for ov in OVERHEADS_NS for T in TS_US]
            if s == "flood":
                cfg += [(K, IBM_T_ITER, ov, T, "ibm") for K in KS for ov in OVERHEADS_NS for T in TS_US]
            # split each (p, sched) into chunks so 2 workers stay busy
            for k in range(0, len(cfg), 40):
                jobs.append((p, s, seqs[p][s], cfg[k:k + 40]))
    from multiprocessing import Pool
    with Pool(args.workers) as pool:
        for rows in pool.imap_unordered(worker, jobs):
            res["partB"] += rows
        print(f"{tag}Part B: {len(res['partB'])} configurations x {args.jobs:,} jobs in {time.time() - t0:.0f} s",
              flush=True)
        # Part C (sweep): candidate K = LER(K) <= 1.1 x uncapped (if per-shot fails exist), else all K
        cjobs = []
        for p in seqs:
            A = res["partA"][p].get("sweep")
            Kc = [K for K in KS if A[str(K)]["ler"] <= 1.1 * A["uncapped_ler"]] if isinstance(A, dict) else list(KS)
            cjobs.append((p, seqs[p]["sweep"], [(K, ov, T) for K in Kc for ov in OVERHEADS_NS for T in TS_US]))
        for rows in pool.imap_unordered(refine, cjobs):
            res["partC"] += rows
    for r in res["partC"]:
        A = res["partA"][r["p"]].get("sweep")
        r["ler_condition"] = "applied" if isinstance(A, dict) else "NOT applied (no per-shot fail data)"
        if isinstance(A, dict):
            r["ler_ratio"] = A[str(r["K"])]["ratio"]
        g = [x for x in res["partB"] if x["p"] == r["p"] and x["sched"] == "sweep" and x["K"] == r["K"]
             and x["overhead_ns"] == r["overhead_ns"] and x["T_us"] == r["T_us"] and x["kind"] == "grid"
             and x["util"] < 0.7 and x["lat_p999_us"] < 100]
        r["t_iter_max_grid_ns"] = max((x["t_iter_ns"] for x in g), default=None)
    res["seconds"] = round(time.time() - t0, 1)
    json.dump(res, open(os.path.join(args.out, "queue_results.json"), "w"), indent=1, default=float)
    plots(res, args.out, args.label)
    write_tables(res, args.out)
    print(f"{tag}DONE in {res['seconds']} s", flush=True)


if __name__ == "__main__":
    main()
