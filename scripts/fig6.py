"""Eval task 4: figures/fig_results.pdf (3.5 in wide, 2 panels stacked, Times New Roman 7-8 pt, vector PDF), from logged
data only. Prints the data table used for each panel.

Red-black engine numbers: RB (LUT, clock, ns per iteration) is defined once, at the top of scripts/eval_scaling.py.
This script imports it and re-runs eval_scaling first, so after the timing-closure run edit RB there and run
`python fig6.py`: results/eval/scaling.{json,md} and the figure are both regenerated.

(a) ns per 13-round iteration (log) vs LUT (log), gross-code X decoder:
    IBM fully parallel (2,106,738 LUT, 24 ns, as given; square)
    SORTQ sweep k = 1 measured (pf2fix: 448,213 LUT, 188.2 ns; filled circle)
    SORTQ sweep k = 2-4 model (results/test2d/refix/pareto.csv, "SORTQ pf2 P1"; hollow circles)
    SORTQ red-black measured (RB; filled star)
    dashed lines: throughput (a) and 1 ms (c) targets, p = 0.002 and 0.003, rb13 traces, T = 12 us
    (results/test1g/criteria/criteria.json)
(b) code vs LUT per code block (X + Z decoders, log): fully parallel from our blocks vs SORTQ red-black
    (results/eval/scaling.json), VU19P LUT count; annotated with logical qubits per FPGA (<= 80% LUT).
Font: Times New Roman (system font, or times*.ttf from FIG_FONT_DIR, default /mnt/c/Windows/Fonts); text embedded
as TrueType (pdf.fonttype 42).   Usage: python fig6.py
"""
import os, sys, csv, json, glob
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.ticker import LogLocator, NullFormatter, FuncFormatter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import eval_scaling  # noqa: E402
from eval_scaling import RB  # noqa: E402  red-black engine numbers (edit them in eval_scaling.py)

IDEAS = os.path.join(HERE, "..")
FIG = os.path.join(IDEAS, "figures", "fig_results.pdf")
IBM = dict(lut=2106738, ns=24.0)
SWEEP_K1 = dict(lut=448213, ns=188.2)            # engine_top_pf2fix, 138.1 MHz post-route, 26 cycles
DEV_LUT = 4085760
# colours: categorical slots 1-3 of the dataviz reference palette (light); identity also carried by marker shape
C_SWEEP, C_PAR, C_RB, INK, MUTED = "#2a78d6", "#eb6834", "#1baf7a", "#0b0b0b", "#52514e"


def font():
    names = {f.name for f in font_manager.fontManager.ttflist}
    if "Times New Roman" not in names:
        d = os.environ.get("FIG_FONT_DIR", "/mnt/c/Windows/Fonts")
        files = [f for f in glob.glob(os.path.join(d, "times*.ttf"))]
        if not files:
            raise SystemExit(f"Times New Roman not found (system fonts or {d}/times*.ttf); set FIG_FONT_DIR")
        for f in files:
            font_manager.fontManager.addfont(f)
    plt.rcParams.update({"font.family": "Times New Roman", "mathtext.fontset": "stix", "font.size": 7.5,
                         "axes.labelsize": 8, "xtick.labelsize": 7, "ytick.labelsize": 7, "legend.fontsize": 7,
                         "pdf.fonttype": 42, "ps.fonttype": 42, "axes.linewidth": 0.5,
                         "xtick.major.width": 0.5, "ytick.major.width": 0.5, "xtick.minor.width": 0.4,
                         "ytick.minor.width": 0.4, "lines.linewidth": 1.0, "axes.edgecolor": MUTED})


def data_a():
    k = []
    with open(os.path.join(IDEAS, "results/test2d/refix/pareto.csv")) as f:
        for r in csv.DictReader(f):
            if r["design"] == "SORTQ pf2 P1" and r["k"] in ("2", "3", "4"):
                k.append(dict(k=int(r["k"]), lut=float(r["lut"]), ns=float(r["ns_13r"])))
    J = json.load(open(os.path.join(IDEAS, "results/test1g/criteria/criteria.json")))["rows"]
    tg = {(r["p"], r["crit"]): r["t_iter_max_ns"] for r in J
          if r["trace"] == "1g int4.2.8 rb13" and r["T_us"] == 12.0 and r["crit"] in ("a", "c")}
    pts = [("IBM fully parallel (flood)", "measured (published)", IBM["lut"], IBM["ns"]),
           ("SORTQ sweep k = 1 (pf2fix)", "measured", SWEEP_K1["lut"], SWEEP_K1["ns"])]
    pts += [(f"SORTQ sweep k = {x['k']}", "model", x["lut"], x["ns"]) for x in k]
    pts.append(("SORTQ red-black (engine_top_rb)", "measured", RB["lut"], RB["ns_iter"]))
    return pts, tg


def data_b():
    o = eval_scaling.main()
    rows = []
    for tag, name in eval_scaling.CODES:
        r = o["codes"][tag]
        rows.append(dict(code=name, fp=r["fully_parallel"]["block_lut"], fp_lq=r["fully_parallel"]["logical_qubits"],
                         rb=r["rb"]["block_lut"], rb_lq=r["rb"]["logical_qubits"],
                         rb_measured=(tag == "144_12_12")))
    return rows


def lutfmt(y, _):
    return f"{y / 1e6:g}M" if y >= 1e6 else f"{y / 1e3:g}k"


def main():
    font()
    pts, tg = data_a()
    rows = data_b()
    print("Panel (a): gross-code X decoder")
    print(f"{'design':34s} {'source':22s} {'LUT':>10s} {'ns/iter':>8s}")
    for n, s, l, t in pts:
        print(f"{n:34s} {s:22s} {l:10,.0f} {t:8.2f}")
    print("targets (rb13, T = 12 us): " + ", ".join(f"p {p} {'throughput' if c == 'a' else '1 ms'} {v:.0f} ns"
                                                    for (p, c), v in sorted(tg.items())))
    print("\nPanel (b): LUT per code block (X + Z), logical qubits per VU19P at <= 80% LUT")
    print(f"{'code':14s} {'fully parallel':>15s} {'LQ':>4s} {'SORTQ red-black':>16s} {'LQ':>4s}")
    for r in rows:
        print(f"{r['code']:14s} {r['fp']:15,.0f} {r['fp_lq']:4d} {r['rb']:16,.0f} {r['rb_lq']:4d}")
    print(f"VU19P LUT {DEV_LUT:,}")

    fig, (ax, bx) = plt.subplots(2, 1, figsize=(3.5, 4.3), gridspec_kw=dict(height_ratios=[1.15, 1]))
    # ---------------------------------------------------------------- (a)
    for (p, c), v in tg.items():
        ax.axvline(v, color=MUTED, lw=0.6, ls=(0, (3, 2)), zorder=1)
        ax.text(v * 1.03, 2.75e6, f"$p$={p}\n{'throughput' if c == 'a' else '1 ms'}", rotation=90, va="top",
                ha="left", fontsize=6.5, color=MUTED)
    ax.scatter([IBM["ns"]], [IBM["lut"]], marker="s", s=22, color=C_PAR, edgecolor="white", lw=0.5, zorder=3)
    ax.annotate("IBM fully\nparallel", (IBM["ns"], IBM["lut"]), xytext=(0, -6), textcoords="offset points",
                ha="center", va="top", fontsize=7, color=INK)
    kx = [x for x in pts if x[1] == "model"]
    ax.plot([SWEEP_K1["ns"]] + [x[3] for x in kx], [SWEEP_K1["lut"]] + [x[2] for x in kx], color=C_SWEEP, lw=0.6,
            zorder=2)
    ax.scatter([x[3] for x in kx], [x[2] for x in kx], marker="o", s=16, facecolor="white", edgecolor=C_SWEEP,
               lw=0.9, zorder=3, label="model")
    for n, _, l, t in kx:
        ax.annotate(f"k={n[-1]}", (t, l), xytext=(0, 5), textcoords="offset points", ha="center", fontsize=6.5,
                    color=INK)
    ax.scatter([SWEEP_K1["ns"]], [SWEEP_K1["lut"]], marker="o", s=18, color=C_SWEEP, edgecolor="white", lw=0.5,
               zorder=3, label="measured")
    ax.annotate("SORTQ sweep\nk=1", (SWEEP_K1["ns"], SWEEP_K1["lut"]), xytext=(0, -6), textcoords="offset points",
                ha="center", va="top", fontsize=7, color=INK)
    ax.scatter([RB["ns_iter"]], [RB["lut"]], marker="*", s=60, color=C_RB, edgecolor="white", lw=0.5, zorder=4)
    ax.annotate("SORTQ\nred-black", (RB["ns_iter"], RB["lut"]), xytext=(-6, 0), textcoords="offset points",
                ha="right", va="center", fontsize=7, color=INK)
    ax.set_xscale("log"); ax.set_yscale("log")
    ax.set_xlim(15, 700); ax.set_ylim(2.5e5, 3e6)
    ax.set_xlabel("ns per 13-round iteration")
    ax.set_ylabel("LUT (X decoder)")
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x, _: f"{x:g}"))
    ax.xaxis.set_minor_formatter(FuncFormatter(lambda x, _: f"{x:g}" if x in (20, 50, 200, 500) else ""))
    ax.yaxis.set_major_formatter(FuncFormatter(lutfmt))
    ax.yaxis.set_minor_locator(LogLocator(subs=(2, 3, 5)))
    ax.yaxis.set_minor_formatter(FuncFormatter(lambda y, _: lutfmt(y, _) if round(y / 10 ** int(f"{y:e}"[-3:]))
                                               in (3,) else ""))
    leg = ax.legend(loc="lower left", frameon=False, handletextpad=0.3, borderaxespad=0.3, markerscale=0.9)
    for h in leg.legend_handles:
        h.set_edgecolor(MUTED)
        if h.get_label() == "measured":
            h.set_facecolor(MUTED)
    ax.set_title("(a)", loc="left", fontsize=8, pad=3)
    # ---------------------------------------------------------------- (b)
    x = list(range(len(rows)))
    bx.axhline(DEV_LUT, color=MUTED, lw=0.6, ls=(0, (3, 2)), zorder=1)
    bx.text(-0.25, DEV_LUT * 1.12, f"VU19P ({DEV_LUT / 1e6:.2f}M LUT)", fontsize=6.5, color=MUTED, va="bottom")
    bx.plot(x, [r["fp"] for r in rows], color=C_PAR, marker="s", ms=4, mec="white", mew=0.5,
            label="fully parallel")
    bx.plot(x, [r["rb"] for r in rows], color=C_RB, marker="*", ms=7, mec="white", mew=0.5,
            label="SORTQ red-black")
    for i, r in enumerate(rows):
        bx.annotate(f"{r['fp_lq']} LQ", (i, r["fp"]), xytext=(0, 5), textcoords="offset points", ha="center",
                    fontsize=6.5, color=INK)
        bx.annotate(f"{r['rb_lq']} LQ", (i, r["rb"]), xytext=(0, -7), textcoords="offset points", ha="center",
                    va="top", fontsize=6.5, color=INK)
    bx.set_yscale("log")
    bx.set_xticks(x, [r["code"] for r in rows])
    bx.set_xlim(-0.35, len(rows) - 0.65)
    bx.set_ylim(2.5e5, 4e7)
    bx.set_ylabel("LUT per code block (X + Z)")
    bx.yaxis.set_major_formatter(FuncFormatter(lutfmt))
    bx.yaxis.set_minor_formatter(NullFormatter())
    bx.legend(loc="upper left", frameon=False, handletextpad=0.4, borderaxespad=0.3, bbox_to_anchor=(0, 0.93))
    bx.set_title("(b)", loc="left", fontsize=8, pad=3)
    for a in (ax, bx):
        a.spines[["top", "right"]].set_visible(False)
        a.tick_params(colors=MUTED, labelcolor=INK, which="both")
    fig.tight_layout(h_pad=0.8, pad=0.3)
    os.makedirs(os.path.dirname(FIG), exist_ok=True)
    fig.savefig(FIG)
    if os.environ.get("FIG_PREVIEW"):              # optional PNG preview path
        fig.savefig(os.environ["FIG_PREVIEW"], dpi=300)
    print("\nwrote", os.path.normpath(FIG))


if __name__ == "__main__":
    main()
