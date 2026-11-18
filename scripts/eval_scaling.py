"""Eval task 3: SORTQ resource estimates (Tests 2e / 3f) and logical qubits per FPGA (Test 3g) with the red-black
engine (engine_top_rb, Test 2f) as the measured reference engine for the gross code; the sweep-engine (pf2fix)
estimates are kept from the existing builds. No new synthesis or decoding.

Edit RB below when the timing-closure run (hw/summary_2f.md, "timing closure attempt") finishes, then re-run this
script (fig6.py imports RB from here and re-runs this script first, so one edit updates both).

Inputs (all existing):
  results/test3f/builds_refix/*/engine_params.json, estimate.json   the 6 `sortq build` outputs (pf2fix reference):
                         group, error types, base-edge table, matrix; sweep-engine LUT; fully parallel LUT
  RB["hier"]             post-route hierarchical utilization of the reference rb run (per-block LUT / FF / LUTRAM)
  scripts/sortq.py       raw_engine(): round_step model (per-unit CNU / VNU in-context numbers), reused unchanged

Red-black engine model (estimate; per-block measured numbers of the rb run, scaled to each code):
  round_step_rb   x  sortq round_step model(code) / sortq round_step model(gross X)  (CNU + VNUs per position + glue)
  memories        x  rb state bits per home round (memory width) code / gross. Each bank holds ceil(W/2) <= 32 words
                     and the LUTRAM primitives are 32 deep (rb run: 7 words), so width, not depth, sets the cost.
                     bits per home = NPOS x [5 (all base-edge v2c) + 5 (o0 edges of two-round types, C0)
                     + 5 (o1 edges, C1) + 2 x 7 x NT (marginal, 2 copies) + 3 x NT (g8)] = 33,120 for the gross code
  gamma lanes     x  NT x NPOS            conv_check  x  W x NPOS x NBASE      commit  x  NT x NPOS x NOBS
  ctrl, glue      constant
  W = number of detector rounds of the circuit (one window = the whole circuit, as the rb engine was built and
  measured: W = 13 = rounds for the gross code, win_t = 0 asserted).
  Calibration: RB["lut"] / sum of the hierarchy's per-block LUT (Vivado's per-instance counts add up to slightly more).
Cycles per iteration (computed, not simulated): the rb pipeline reads v2c 4 cycles before writing it, so two steps
  that share an error must issue >= 5 slots apart (cyclic). The minimum issue period with bubbles is searched.
Logical qubits per FPGA: one code block = X engine + Z engine (each complete); budget <= 80% of the xcvu19p LUTs;
  k = 12 for all three codes.
Output: results/eval/scaling.json, results/eval/scaling.md.   Usage: python eval_scaling.py
"""
import os, sys, json, math, re
from collections import defaultdict

# ------------------------------------------------------------------ red-black reference engine (EDIT HERE)
RB = dict(
    run="tc/A_explore_4.76",                                    # post-route run the per-block breakdown comes from
    hier="hw/rb/synth/tc/runs/A_explore_4.76/util_route_hier.rpt",
    lut=520369,          # post-route LUT of dut (measured, timing-closure variant A Explore, 4.76 ns)
    ff=140289, lutram=37868,
    mhz=210.1,           # confirmed post-route clock (WNS +0.009 at 4.76 ns)
    cycles_iter=13,      # cycles per 13-round iteration (measured in closed-loop simulation)
    ns_iter=61.88,       # ns per 13-round iteration = 13 x 4.76 ns
)
# ------------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))
IDEAS = os.path.join(HERE, "..")
BUILDS = os.path.join(IDEAS, "results/test3f/builds_refix")
OUT = os.path.join(IDEAS, "results/eval")
os.environ.setdefault("SORTQ_REF_RUN", "engine_top_pf2fix_p1_lutram_fmax")   # as for builds_refix
sys.path.insert(0, HERE)
import sortq  # noqa: E402

DEV_LUT, DEV_FF, DEV_LUTRAM = sortq.DEV_LUT, sortq.DEV_FF, sortq.DEV_LUTRAM
BUDGET = 0.8 * DEV_LUT
K_LOGICAL = 12
IBM_LUT = 2106738              # IBM X decoder, fully parallel (as given)
CODES = [("72_12_6", "[[72,12,6]]"), ("144_12_12", "[[144,12,12]]"), ("288_12_18", "[[288,12,18]]")]
BASES = [("X", "memory_Z_Xdec"), ("Z", "memory_X_Zdec")]
MIN_DIST = 5                    # v2c read -> write 4 cycles; a write in t is seen at t + 1


def rb_blocks(path):
    """dut children of the hierarchical report, grouped: (lut, lutram, ff) per block."""
    g = defaultdict(lambda: [0, 0, 0])
    for line in open(os.path.join(IDEAS, path)):
        f = line.split("|")
        if len(f) < 8:
            continue
        m = re.match(r"^(\s*)(\S.*?)\s*$", f[1])
        if not m or len(m.group(1)) != 5:
            continue
        name = m.group(2)
        key = {"g_bank": "memories", "g_lt": "gamma_lanes", "u_rs": "round_step", "u_conv": "conv_check",
               "u_commit": "commit", "u_ctrl": "ctrl", "(dut)": "glue"}[re.sub(r"[\[.].*", "", name)]
        try:
            v = [int(f[3]), int(f[5]), int(f[7])]
        except ValueError:
            continue
        for i in range(3):
            g[key][i] += v[i]
    return {k: dict(lut=v[0], lutram=v[1], ff=v[2]) for k, v in g.items()}


def counts(ep, est):
    bulk = {t["type"]: t for t in ep["error_types"] if t["in_bulk_template"]}
    hp = {k for k, t in bulk.items() if max(t["round_offsets"]) >= 1}
    be = ep["base_edge_table"]
    o0hp = sum(e["round_offset"] == 0 and e["error_type"] in hp for e in be)
    o1 = sum(e["round_offset"] == 1 for e in be)
    c = dict(est["counts"])
    c.update(R=ep["matrix"]["rounds"], o0_two_round=o0hp, o1=o1,
             weights_bulk=[bulk[k]["weight"] for k in bulk], weights_hp=[bulk[k]["weight"] for k in bulk if k in hp])
    c["rb_bits_per_home"] = c["NPOS"] * (5 * c["NBASE"] + 5 * o0hp + 5 * o1 + 2 * 7 * c["NT"] + 3 * c["NT"])
    return c


def rb_order(R):
    return list(range(0, R, 2)) + list(range(1, R, 2))


def min_period(R, dmin=MIN_DIST):
    """smallest issue period P (cycles per iteration) for the rb order with bubbles, such that every pair of steps
    sharing an error (rounds r, r + 1; and a step with itself one iteration later) is >= dmin slots apart, cyclic."""
    order = rb_order(R)
    pos = {r: i for i, r in enumerate(order)}
    pairs = [(pos[r], pos[r + 1]) for r in range(R - 1)]
    base_dist = min(min((b - a) % R, (a - b) % R) for a, b in pairs)
    for P in range(max(R, dmin), 4 * R + dmin):
        c = [0]

        def ok_partial(c):
            j = len(c) - 1
            for a, b in pairs:
                if max(a, b) == j and min(a, b) < j:
                    lo, hi = sorted((a, b))
                    if c[hi] - c[lo] < dmin:
                        return False
            return True

        def full_ok(c):
            return all(min((c[b] - c[a]) % P, (c[a] - c[b]) % P) >= dmin for a, b in pairs)

        def dfs(c):
            if len(c) == R:
                return full_ok(c)
            for t in range(c[-1] + 1, P - (R - len(c)) + 1):
                c.append(t)
                if ok_partial(c) and dfs(c):
                    return True
                c.pop()
            return False

        if dfs(c):
            return dict(rounds=R, order=order, hazard_distance_no_bubbles=base_dist, cycles_per_iteration=P,
                        bubbles=P - R, issue_cycles=list(c))
    raise RuntimeError(R)


def main():
    B = sortq.blocks()
    blk = rb_blocks(RB["hier"])
    hier_sum = sum(v["lut"] for v in blk.values())
    cal = RB["lut"] / hier_sum
    ref_ep = json.load(open(os.path.join(BUILDS, "bicycle_bivariate_144_12_12_memory_Z_Xdec/engine_params.json")))
    ref_est = json.load(open(os.path.join(BUILDS, "bicycle_bivariate_144_12_12_memory_Z_Xdec/estimate.json")))
    ref = counts(ref_ep, ref_est); ref["W"] = ref["R"]
    assert ref["rb_bits_per_home"] == 33120, ref["rb_bits_per_home"]

    def rs_model(c):
        parts, _, _, _ = sortq.raw_engine(B, c, c["weights_bulk"], c["weights_hp"], c["W"])
        return sum(parts.values())

    rs_ref = rs_model(ref)
    out = dict(rb_reference=RB, rb_hierarchy=blk, rb_hierarchy_lut_sum=hier_sum, calibration=cal,
               budget_lut=BUDGET, codes={})
    for tag, name in CODES:
        row = dict(name=name, basis={})
        for basis, suf in BASES:
            d = os.path.join(BUILDS, f"bicycle_bivariate_{tag}_{suf}")
            ep = json.load(open(os.path.join(d, "engine_params.json")))
            est = json.load(open(os.path.join(d, "estimate.json")))
            c = counts(ep, est); c["W"] = c["R"]
            f = dict(round_step=rs_model(c) / rs_ref,
                     memories=c["rb_bits_per_home"] / ref["rb_bits_per_home"],
                     gamma_lanes=(c["NT"] * c["NPOS"]) / (ref["NT"] * ref["NPOS"]),
                     conv_check=(c["W"] * c["NPOS"] * c["NBASE"]) / (ref["W"] * ref["NPOS"] * ref["NBASE"]),
                     commit=(c["NT"] * c["NPOS"] * c["NOBS"]) / (ref["NT"] * ref["NPOS"] * ref["NOBS"]),
                     ctrl=1.0, glue=1.0)
            parts = {k: blk[k]["lut"] * f[k] * cal for k in blk}
            lut = sum(parts.values())
            ff = sum(blk[k]["ff"] * f[k] for k in blk) * RB["ff"] / sum(v["ff"] for v in blk.values())
            lutram = blk["memories"]["lutram"] * f["memories"]
            per = min_period(c["R"])
            fp = est["fully_parallel"]["lut"]
            row["basis"][basis] = dict(
                counts={k: v for k, v in c.items() if not k.startswith("weights")}, scale=f,
                rb_lut=lut, rb_lut_parts=parts, rb_lut_pct=100 * lut / DEV_LUT, rb_ff=ff, rb_lutram=lutram,
                rb_measured=(tag == "144_12_12" and basis == "X"),
                rb_cycles=per, rb_ns_iter_at_ref_clock=per["cycles_per_iteration"] * 1000 / RB["mhz"],
                sweep_lut=est["engine_lut"], sweep_W=est["counts"]["W"], fully_parallel_lut=fp,
                ratio_fp_over_rb=fp / lut, ratio_fp_over_sweep=fp / est["engine_lut"])
        X, Z = row["basis"]["X"], row["basis"]["Z"]
        for kind, key in (("rb", "rb_lut"), ("sweep", "sweep_lut"), ("fully_parallel", "fully_parallel_lut")):
            blkl = X[key] + Z[key]
            n = int(BUDGET // blkl)
            row[kind] = dict(block_lut=blkl, block_pct=100 * blkl / DEV_LUT, blocks_fractional=BUDGET / blkl,
                             blocks=n, logical_qubits=K_LOGICAL * n)
        n = row["rb"]["blocks"]
        row["rb"]["at_blocks"] = dict(ff=n * (X["rb_ff"] + Z["rb_ff"]), ff_pct=100 * n * (X["rb_ff"] + Z["rb_ff"]) / DEV_FF,
                                      lutram=n * (X["rb_lutram"] + Z["rb_lutram"]),
                                      lutram_pct=100 * n * (X["rb_lutram"] + Z["rb_lutram"]) / DEV_LUTRAM)
        out["codes"][tag] = row
    ibm = 2 * IBM_LUT
    out["ibm_gross"] = dict(block_lut=ibm, block_pct=100 * ibm / DEV_LUT, blocks=int(BUDGET // ibm),
                            blocks_fractional=BUDGET / ibm)
    os.makedirs(OUT, exist_ok=True)
    json.dump(out, open(os.path.join(OUT, "scaling.json"), "w"), indent=1, default=float)
    write_md(out)
    return out


def fmt(x):
    return f"{x:,.0f}"


def write_md(o):
    C = o["codes"]; rb = o["rb_reference"]
    L = ["# Scaling: SORTQ red-black engine vs fully parallel, logical qubits per FPGA", "",
         "Generated by `scripts/eval_scaling.py` (estimates from measured blocks; no new synthesis).", "",
         "## Setup",
         f"- **Reference engine (measured):** engine_top_rb ({rb['run']}), gross-code X decoder, post-route on xcvu19p: "
         f"**{fmt(rb['lut'])} LUT**, {fmt(rb['ff'])} FF, {fmt(rb['lutram'])} LUTRAM, **{rb['mhz']} MHz**, "
         f"{rb['cycles_iter']} cycles = **{rb['ns_iter']} ns per 13-round iteration**.",
         f"- **Per-block breakdown** from that run's hierarchical report "
         f"(sum {fmt(o['rb_hierarchy_lut_sum'])} LUT; calibration {o['calibration']:.5f} to the measured total):", "",
         "  | Block | LUT | LUTRAM | FF | Scaled by |", "  |---|---|---|---|---|"]
    how = dict(round_step="sortq round_step model (CNU + VNUs per position + glue)",
               memories="rb state bits per home round (memory width)", gamma_lanes="NT × NPOS",
               conv_check="W × NPOS × NBASE", commit="NT × NPOS × NOBS", ctrl="constant", glue="constant")
    for k in ("round_step", "memories", "gamma_lanes", "conv_check", "commit", "ctrl", "glue"):
        v = o["rb_hierarchy"][k]
        L.append(f"  | {k} | {fmt(v['lut'])} | {fmt(v['lutram'])} | {fmt(v['ff'])} | {how[k]} |")
    L += ["",
          "- **Assumptions (stated):**",
          "  - **Window:** W = number of detector rounds (7 / 13 / 19), one window over the whole circuit. This is how the rb "
          "engine was built and measured (W = 13, win_t = 0 asserted). The sweep-engine numbers keep W = d (6 / 12 / 18) from Test 3f.",
          "  - **Memories scale with width, not depth:** each parity bank holds ⌈W/2⌉ words (4 / 7 / 10), and the LUTRAM "
          "primitives are 32 deep, so the measured cost (7 words) depends on the bits per word. "
          "(The Test 3f sweep model scaled memories by bits × W; those numbers are kept unchanged.)",
          "  - **Same per-position content:** all six decoders have 10 error types (7 two-round), 35 base edges and the same "
          "type weights. So the round step scales with the number of positions (36 / 72 / 144), and X and Z engines get the same estimate.",
          "  - **Clock:** measured for the gross X engine only. The ns figures for other codes use the same clock, which is an assumption, "
          "not a measurement (the 288 engine has twice the positions).",
          "  - **Code block** = X engine + Z engine, each complete. Budget ≤ 80% of 4,085,760 LUT = 3,268,608. k = 12 logical qubits per block.",
          "  - **Fully parallel** = Σ CNU(deg) + Σ VNU(deg) over the whole decoder matrix from our standalone blocks (Test 2d / 3f), one basis.",
          "",
          "## Per code (one basis; X and Z are equal)", "",
          "| Code | W (rb) | SORTQ red-black LUT | SORTQ sweep LUT (pf2fix, W = d) | Fully parallel LUT | Fully parallel / red-black | Fully parallel / sweep |",
          "|---|---|---|---|---|---|---|"]
    for tag, name in CODES:
        x = C[tag]["basis"]["X"]
        rbl = f"{fmt(x['rb_lut'])} ({x['rb_lut_pct']:.1f}%)" + (" **measured X**" if tag == "144_12_12" else "")
        swl = f"{fmt(x['sweep_lut'])}" + (" measured X" if tag == "144_12_12" else "")
        L.append(f"| {name} | {x['counts']['W']} | {rbl} | {swl} | {fmt(x['fully_parallel_lut'])} "
                 f"({100 * x['fully_parallel_lut'] / DEV_LUT:.0f}%) | **{x['ratio_fp_over_rb']:.1f}×** | {x['ratio_fp_over_sweep']:.1f}× |")
    L += ["", "Red-black LUT parts (X engine):", "",
          "| Code | round_step | memories | gamma lanes | conv_check | commit | ctrl + glue | LUTRAM | FF |", "|---|---|---|---|---|---|---|---|---|"]
    for tag, name in CODES:
        x = C[tag]["basis"]["X"]; p = x["rb_lut_parts"]
        L.append(f"| {name} | {fmt(p['round_step'])} | {fmt(p['memories'])} | {fmt(p['gamma_lanes'])} | {fmt(p['conv_check'])} | "
                 f"{fmt(p['commit'])} | {fmt(p['ctrl'] + p['glue'])} | {fmt(x['rb_lutram'])} | {fmt(x['rb_ff'])} |")
    L += ["", "## Logical qubits per VU19P (X + Z per block, ≤ 80% LUT)", "",
          "| Code | Design | LUT per block (X + Z) | % of device | Blocks (fractional) | Logical qubits per FPGA |",
          "|---|---|---|---|---|---|"]
    for tag, name in CODES:
        r = C[tag]
        for kind, lab in (("rb", "SORTQ red-black"), ("sweep", "SORTQ sweep (pf2fix)"), ("fully_parallel", "fully parallel (our blocks)")):
            v = r[kind]
            q = f"**{v['logical_qubits']}**" if kind == "rb" else str(v["logical_qubits"])
            L.append(f"| {name} | {lab} | {fmt(v['block_lut'])} | {v['block_pct']:.1f}% | {v['blocks']} ({v['blocks_fractional']:.2f}) | {q} |")
    ib = o["ibm_gross"]
    L.append(f"| [[144,12,12]] | IBM fully parallel (2 × {fmt(IBM_LUT)}, Z assumed = X) | {fmt(ib['block_lut'])} | "
             f"{ib['block_pct']:.1f}% | {ib['blocks']} ({ib['blocks_fractional']:.2f}) | 0 |")
    L += ["", "**Other resources at the red-black block count** (estimates; not binding):", ""]
    for tag, name in CODES:
        a = C[tag]["rb"]["at_blocks"]; n = C[tag]["rb"]["blocks"]
        L.append(f"- {name}, {n} block{'' if n == 1 else 's'}: FF {fmt(a['ff'])} ({a['ff_pct']:.1f}%), LUTRAM {fmt(a['lutram'])} ({a['lutram_pct']:.1f}%); no BRAM / DSP.")
    L += ["", "## Cycles per iteration for the other codes (computed from the order, not simulated)", "",
          "The rb pipeline writes v2c 4 cycles after reading it, so two steps that share an error must issue ≥ 5 slots apart "
          "(cyclic). The search below finds the fewest cycles per iteration, inserting bubbles where needed.", "",
          f"| Code | Rounds | Order | Distance without bubbles | Cycles / iteration | Bubbles | ns / iteration at {RB['mhz']} MHz (assumed clock) |",
          "|---|---|---|---|---|---|---|"]
    for tag, name in CODES:
        x = C[tag]["basis"]["X"]; c = x["rb_cycles"]
        L.append(f"| {name} | {c['rounds']} | {', '.join(map(str, c['order']))} | {c['hazard_distance_no_bubbles']} | "
                 f"{c['cycles_per_iteration']} | {c['bubbles']} | {x['rb_ns_iter_at_ref_clock']:.1f} |")
    L += ["", "- [[72,12,6]] needs bubbles: the as-built engine has no stall logic, so a 72 engine would need a modified ctrl_rb. "
          "Its LUT estimate does not include that.",
          "", "## Not covered",
          "- No rb RTL was generated, linted or synthesized for the 72 or 288 codes or for any Z decoder "
          "(`rb/gen/gen_rb_pkg.py` was not run on them). All of these numbers are model estimates except the gross X engine.",
          "- The clock of the other code sizes was not measured.",
          "- The IBM number is the published X-decoder total; Z is assumed equal.", ""]
    open(os.path.join(OUT, "scaling.md"), "w").write("\n".join(L))


if __name__ == "__main__":
    o = main()
    for tag, _ in CODES:
        r = o["codes"][tag]; x = r["basis"]["X"]
        print(tag, f"rb {x['rb_lut']:.0f}  sweep {x['sweep_lut']:.0f}  fp {x['fully_parallel_lut']:.0f}  "
              f"fp/rb {x['ratio_fp_over_rb']:.2f}  blocks rb {r['rb']['blocks']} ({r['rb']['blocks_fractional']:.2f}) "
              f"LQ rb {r['rb']['logical_qubits']} sweep {r['sweep']['logical_qubits']} fp {r['fully_parallel']['logical_qubits']}  "
              f"cycles {x['rb_cycles']['cycles_per_iteration']}")
