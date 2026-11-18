"""Test 2e: `sortq build <circuit.stim> --basis {X,Z} [--out DIR] [--window W]` — the SORTQ flow end to end, reusing the
existing pieces (no re-implementation):
  1. decoder matrix (dem_tools.decoder_problem) + symmetry detection (nauty, idea1_symmetry.automorphisms) + template
     extraction + exact reconstruction check  ->  scripts/test1c_engine_params.py  ->  engine_params.json
  2. round wiring + package                 ->  hw/gen/gen_round_wiring.py      ->  round_wiring.sv, round_wiring_pkg.sv
  3. boundary type sets + observable ROM    ->  hw/gen/gen_tables.py            ->  engine_tables_pkg.sv
  4. resource estimate from the Test 2c / 2d measured per-block numbers (hw/synth/results.json)  ->  estimate.json
  5. report.md
  (--order rb, the default) red-black engine package: hw/rb/gen/gen_rb_pkg.py -> rb_pkg.sv, rb_pkg_report.json
     (order, leg-start gating tables, minimum dependency distance, stall cycles per iteration); --order sweep skips it
     and leaves every other output unchanged.
--basis X = X decoder (Z-type detectors; memory_Z circuits); --basis Z = Z decoder (X-type detectors; memory_X).

Resource model (estimate; every input is a post-route measurement from Test 2c / 2d, xcvu19p):
  CNU LUT(d), standalone: measured at d = 16, 25, 35; piecewise linear in d, extrapolated with the last slope.
  VNU LUT(d), standalone: measured at d = 2..6; extrapolated with the least-squares slope above 6.
  In-context factors (measured inside round_step_pf2 of the gross X engine): CNU x 671/810, VNU x 211.5/226.4.
  SORTQ k = 1 engine (engine_top_pf2, VNU_PASSES 1, LUTRAM) =
     round_step: NPOS x [CNU_ic(NBASE) + sum over bulk types VNU_ic(w) + sum over two-round types VNU_ic(w)] + glue
     + shared blocks scaled from the measured gross engine by their natural count:
       state memories (LUT incl. LUTRAM) by state bits per slot x window W; gamma lanes by NTYPES x NPOS;
       conv_check by W x NPOS x NBASE; commit by NTYPES x NPOS x NOBS; ctrl constant.
  Window W (assumption, stated in the report): W = code distance d (the gross code ran W = 12 = d).
  Fully parallel decoder from our blocks: sum over checks CNU(deg) + sum over errors VNU(deg) (as Test 2d), whole
  decoder matrix, standalone (and with the in-context factors).
"""
import sys, os, json, subprocess, argparse, math, time
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
IDEAS = os.path.join(HERE, "..")
GEN = os.path.join(IDEAS, "hw", "gen")
RESULTS = os.path.join(IDEAS, "hw", "synth", "results.json")
DEV_LUT, DEV_FF, DEV_LUTRAM = 4085760, 8171520, 956160
REF = os.environ.get("SORTQ_REF_RUN", "engine_top_pf2_p1_lutram_fmax")   # measured gross X engine


def run(cmd, log):
    t0 = time.time()
    r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    open(log, "a").write(f"$ {' '.join(cmd)}\n{r.stdout}\n[exit {r.returncode}, {time.time() - t0:.1f} s]\n")
    return r.returncode, r.stdout


# ---------------------------------------------------------------- measured block model
def blocks():
    R = json.load(open(RESULTS))
    u = lambda run, k="lut": R[run]["util"].get(k, 0.0)
    sub = {s["inst"]: s for s in R[REF]["sub"]}
    cnu = {16: u("cnu_d16"), 25: u("cnu_d25"), 35: u("cnu")}
    vnu = {2: u("vnu_d2"), 3: u("vnu_d3"), 4: u("vnu_d4"), 5: u("vnu_d5"), 6: u("vnu")}
    lanes = sum(s.get("lut", 0) for k, s in sub.items() if k.startswith("g_lt"))
    mem = sum(s.get("lut", 0) for k, s in sub.items() if k.startswith("u_m_") or k.startswith("g_bank"))
    mem_lutram = sum(s.get("lutram", 0) for k, s in sub.items() if k.startswith("u_m_") or k.startswith("g_bank"))
    rs = sub["u_rs"]["lut"]
    return dict(cnu=cnu, vnu=vnu, ref_total=u(REF), ref_ff=u(REF, "ff"), ref_lutram=u(REF, "lutram"),
                ref_round_step=rs, ref_lanes=lanes, ref_mem=mem, ref_mem_lutram=mem_lutram,
                ref_conv=sub["u_conv"]["lut"], ref_commit=sub["u_commit"]["lut"], ref_ctrl=sub["u_ctrl"]["lut"],
                ref_glue=sub["(dut)"]["lut"], f_cnu=671.0 / 810.0, f_vnu=211.52 / 226.35)


def cnu_lut(B, d):
    pts = sorted(B["cnu"].items())
    for (d0, l0), (d1, l1) in zip(pts, pts[1:]):
        if d <= d1:
            return l0 + (l1 - l0) * (d - d0) / (d1 - d0) if d >= d0 else l0 - (l1 - l0) / (d1 - d0) * (d0 - d)
    (d0, l0), (d1, l1) = pts[-2], pts[-1]
    return l1 + (l1 - l0) / (d1 - d0) * (d - d1)


def vnu_lut(B, d):
    if d in B["vnu"]:
        return B["vnu"][d]
    xs = sorted(B["vnu"]); ys = [B["vnu"][x] for x in xs]
    mx, my = sum(xs) / len(xs), sum(ys) / len(ys)
    s = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
    return B["vnu"][xs[-1]] + s * (d - xs[-1]) if d > xs[-1] else B["vnu"][xs[0]] - s * (xs[0] - d)


# reference (gross X engine) counts used to scale the shared blocks
REF_COUNTS = dict(NPOS=72, NT=10, NHP=7, NE0=22, NE1=13, NBASE=35, NOBS=12, W=12)
REF_WEIGHTS = dict(bulk=[2, 3, 3, 3, 3, 3, 3, 4, 5, 6], hp=[2, 3, 3, 3, 3, 4, 5])   # gross X decoder (Test 1c)


def state_bits(c):
    NNP = c["NT"] - c["NHP"]
    return dict(v2c_o0=c["NE0"] * c["NPOS"] * 5, c2v_o1=c["NE1"] * c["NPOS"] * 5,
                marg=2 * (2 * c["NHP"] + NNP) * c["NPOS"] * 7, g8=(c["NT"] + c["NHP"]) * c["NPOS"] * 3)


def raw_engine(B, c, wb, whp, W):
    """uncalibrated engine LUT: round_step from the in-context per-unit numbers + shared blocks scaled from the gross
    engine (per-instance LUT counts of a hierarchical report add up to slightly more than the parent's total)."""
    r = REF_COUNTS
    cnu_ic = cnu_lut(B, c["NBASE"]) * B["f_cnu"]
    vnu_cur = sum(vnu_lut(B, w) for w in wb) * B["f_vnu"]
    vnu_prev = sum(vnu_lut(B, w) for w in whp) * B["f_vnu"]
    glue = 652.0 * c["NPOS"] / 72
    rs_parts = dict(cnu=c["NPOS"] * cnu_ic, vnu_cur=c["NPOS"] * vnu_cur, vnu_prev=c["NPOS"] * vnu_prev, glue=glue)
    sb, sr = state_bits(c), state_bits(r)
    bits, bits_ref = sum(sb.values()) * W, sum(sr.values()) * r["W"]
    shared = dict(memories=B["ref_mem"] * bits / bits_ref,
                  gamma_lanes=B["ref_lanes"] * (c["NT"] * c["NPOS"]) / (r["NT"] * r["NPOS"]),
                  conv_check=B["ref_conv"] * (W * c["NPOS"] * c["NBASE"]) / (r["W"] * r["NPOS"] * r["NBASE"]),
                  commit=B["ref_commit"] * (c["NT"] * c["NPOS"] * c["NOBS"]) / (r["NT"] * r["NPOS"] * r["NOBS"]),
                  ctrl=B["ref_ctrl"], glue=B["ref_glue"])
    return rs_parts, shared, sb, bits


def estimate(ep, P, W, B):
    import numpy as np
    NA, NB = ep["group"]["structure"]; NPOS = NA * NB
    bulk = [t for t in ep["error_types"] if t["in_bulk_template"]]
    hp = [t for t in bulk if max(t["round_offsets"]) >= 1]
    be = ep["base_edge_table"]
    c = dict(NPOS=NPOS, NT=len(bulk), NHP=len(hp), NE0=sum(e["round_offset"] == 0 for e in be),
             NE1=sum(e["round_offset"] == 1 for e in be), NBASE=len(be), NOBS=int(P["O"].shape[0]), W=W)
    rs_parts, shared, sb, bits = raw_engine(B, c, [t["weight"] for t in bulk], [t["weight"] for t in hp], W)
    rp, sh, _, _ = raw_engine(B, REF_COUNTS, REF_WEIGHTS["bulk"], REF_WEIGHTS["hp"], REF_COUNTS["W"])
    cal = B["ref_total"] / (sum(rp.values()) + sum(sh.values()))     # = 1 for the gross X engine by construction
    rs = sum(rs_parts.values()) * cal
    shared = {k: v * cal for k, v in shared.items()}
    rs_parts = {k: v * cal for k, v in rs_parts.items()}
    eng = rs + sum(shared.values())
    bits_ref = sum(state_bits(REF_COUNTS).values()) * REF_COUNTS["W"]
    lutram = B["ref_mem_lutram"] * bits / bits_ref
    # fully parallel from our blocks (whole decoder matrix)
    H = P["H"].tocsr()
    rdeg = Counter(np.diff(H.indptr).tolist()); cdeg = Counter(np.diff(H.tocsc().indptr).tolist())
    fp_cnu = sum(n * cnu_lut(B, d) for d, n in rdeg.items()); fp_vnu = sum(n * vnu_lut(B, d) for d, n in cdeg.items())
    fp = fp_cnu + fp_vnu; fp_ic = fp_cnu * B["f_cnu"] + fp_vnu * B["f_vnu"]
    extrap = dict(cnu_degrees_outside_measured=sorted(d for d in set(rdeg) | {c["NBASE"]} if d not in B["cnu"]),
                  vnu_degrees_outside_measured=sorted(d for d in set(cdeg) | {t["weight"] for t in bulk} if d not in B["vnu"]))
    return dict(counts=c, state_bits_per_slot=sb, state_bits_total=bits, round_step_lut=rs, calibration=cal,
                round_step_parts=rs_parts,
                shared_lut=shared, engine_lut=eng, engine_lut_pct=100 * eng / DEV_LUT, engine_lutram=lutram,
                vnu_updates_per_step=(c["NT"] + c["NHP"]) * NPOS, cnus_per_step=NPOS,
                fully_parallel=dict(checks=dict(sorted(rdeg.items())), errors=dict(sorted(cdeg.items())),
                                    cnu_lut=fp_cnu, vnu_lut=fp_vnu, lut=fp, lut_pct=100 * fp / DEV_LUT, lut_in_context=fp_ic,
                                    gamma_lane_per_error_lut=H.shape[1] * B["ref_lanes"] / 720),
                ratio_parallel_over_engine=fp / eng, extrapolated=extrap)


def report(out, circ, basis, ep, est, log_ok, W, wiring_msg, tables_msg):
    NA, NB = ep["group"]["structure"]; m = ep["matrix"]
    bulk = [t for t in ep["error_types"] if t["in_bulk_template"]]
    hp = [t for t in bulk if max(t["round_offsets"]) >= 1]
    per = {int(k): len(v) for k, v in ep["error_types_per_home_round"].items()}
    cls = ep["boundary"]["classes"]
    ncls = Counter(c["cls"] for r in cls for c in cls[r])
    fp = est["fully_parallel"]
    L = [f"# sortq build: {os.path.basename(circ)} — {basis} decoder", "",
         "## Flow", "", *[f"- {s}: {'ok' if ok else 'FAILED'}" for s, ok in log_ok], "",
         "## Decoder matrix and symmetry",
         f"- matrix {m['rows']:,} x {m['cols']:,}, nnz {m['nnz']:,}, {m['rounds']} detector rounds (check type {ep['check_type']})",
         f"- group (nauty, rows coloured by round): order {ep['group']['order']}, abelian, Z{NA} x Z{NB}, free and transitive "
         f"on the {NA * NB} checks of every round",
         f"- reconstruction from the templates: **{'exact' if ep['reconstruction']['exact'] else 'NOT exact'}** "
         f"({ep['reconstruction']['columns_rec']:,} columns, nnz {ep['reconstruction']['nnz_rec']:,})",
         f"- bulk reference round {ep['bulk_ref_round']}; rounds with the bulk type set: {ep['bulk_rounds_same_type_set']}",
         f"- error types per home round: {per}; distinct error types {len(ep['error_types'])}, bulk types {len(bulk)}",
         f"- boundary types: class a {ncls.get('a', 0)}, class b (embedded in a bulk type, masked) {ncls.get('b', 0)}, "
         f"class c (own edges) {ncls.get('c', 0)}; slot conflicts {ep['boundary']['slot_conflicts']}",
         f"- base edges (bulk check degree) {len(ep['base_edge_table'])}: offset 0: {est['counts']['NE0']}, offset 1: {est['counts']['NE1']}",
         f"- max check degree {ep['check_degree']['max']}; check degree histogram {fp['checks']}",
         f"- error degrees (max {max(fp['errors'])}): {fp['errors']}; bulk type weights {sorted(t['weight'] for t in bulk)}",
         f"- distinct shifts: bulk table {ep['rotator']['n_shifts_bulk']}, whole matrix {ep['rotator']['n_shifts_all']}",
         f"- two-round error types (updated again in layer home + 1): {len(hp)} -> VNU updates per round step "
         f"{est['vnu_updates_per_step']:,} ({len(bulk)} + {len(hp)} types x {NA * NB}); CNUs per step {est['cnus_per_step']}",
         "", "## Generated", f"- engine_params.json, round_wiring_pkg.sv, round_wiring.sv ({wiring_msg.strip()})",
         f"- engine_tables_pkg.sv ({tables_msg.strip()})", "",
         "## Resource estimate (from the Test 2c / 2d measured blocks; estimate, not synthesized)",
         f"- window W = {W} rounds (assumption: W = d), VNU_PASSES 1, LUTRAM state memory",
         f"- calibration factor {est['calibration']:.4f} (model / measured on the gross X engine, applied to every code)",
         f"- SORTQ k = 1 engine: **{est['engine_lut']:,.0f} LUT ({est['engine_lut_pct']:.1f}%)**, LUTRAM {est['engine_lutram']:,.0f}",
         f"  - round_step {est['round_step_lut']:,.0f} (CNU {est['round_step_parts']['cnu']:,.0f}, VNU cur "
         f"{est['round_step_parts']['vnu_cur']:,.0f}, VNU prev {est['round_step_parts']['vnu_prev']:,.0f})",
         "  - shared: " + ", ".join(f"{k} {v:,.0f}" for k, v in est["shared_lut"].items()),
         f"  - state bits per slot {sum(est['state_bits_per_slot'].values()):,} ({est['state_bits_per_slot']}), x W = {est['state_bits_total']:,}",
         f"- fully parallel decoder from our blocks: **{fp['lut']:,.0f} LUT ({fp['lut_pct']:.1f}%)** standalone "
         f"(CNU {fp['cnu_lut']:,.0f} + VNU {fp['vnu_lut']:,.0f}); with in-context factors {fp['lut_in_context']:,.0f}; "
         f"one gamma lane per error would add {fp['gamma_lane_per_error_lut']:,.0f}",
         f"- ratio fully parallel / SORTQ engine: {est['ratio_parallel_over_engine']:.2f}",
         f"- degrees outside the measured range (linear extrapolation): {est['extrapolated']}", ""]
    open(os.path.join(out, "report.md"), "w").write("\n".join(L) + "\n")


RBGEN = os.path.join(IDEAS, "hw", "rb", "gen", "gen_rb_pkg.py")


def rb_section(out):
    R = json.load(open(os.path.join(out, "rb_pkg_report.json")))
    ok = R["meets_pipeline"]
    return ["## Red-black engine package (--order rb)",
            f"- rb_pkg.sv, rb_pkg_report.json (hw/rb/gen/gen_rb_pkg.py); order {', '.join(map(str, R['order']))}",
            f"- leg-start gating: CNU inputs gated per pass {[len(R['cnu_gated'][k]) for k in sorted(R['cnu_gated'])]} of "
            f"{len(R['cnu_gated']['0']) + len(R['cnu_not_gated']['0'])} base edges; VNU tables per pass and group "
            f"{ {k: len(v) for k, v in R['vnu_gated'].items()} }",
            f"- minimum dependency distance {R['min_dependency_distance']} slots (required >= {R['required_distance']}: "
            f"v2c read -> write 4 cycles): **{'met' if ok else 'NOT met'}**; stall cycles per iteration "
            f"**{R['stall_cycles_per_iteration']}** -> {R['cycles_per_iteration']} cycles per iteration"
            + ("" if ok else f" (issue cycles {R['issue_cycles']}; the RTL has no stall logic, a modified ctrl_rb is needed)"),
            f"- consecutive steps sharing an error: {R['consecutive_steps_sharing_an_error'] or 'none'}", ""]


def build(circ, basis, out, W, order="rb"):
    os.makedirs(out, exist_ok=True)
    log = os.path.join(out, "build.log"); open(log, "w").close()
    py = sys.executable
    steps = []
    rc, _ = run([py, os.path.join(HERE, "test1c_engine_params.py"), circ, out, basis], log)
    steps.append(("1 decoder matrix, symmetry (nauty), templates, exact reconstruction (test1c_engine_params.py)", rc == 0))
    if rc:
        print(open(log).read()[-3000:]); raise SystemExit(f"sortq build: step 1 failed, see {log}")
    epf = os.path.join(out, "engine_params.json")
    rc, wmsg = run([py, os.path.join(GEN, "gen_round_wiring.py"), epf, out], log)
    steps.append(("2 round wiring + package (gen_round_wiring.py)", rc == 0))
    rc2, tmsg = run([py, os.path.join(GEN, "gen_tables.py"), circ, epf, out], log)
    steps.append(("3 boundary type sets + observable ROM (gen_tables.py)", rc2 == 0))
    sys.path.insert(0, HERE)
    from dem_tools import decoder_problem
    ep = json.load(open(epf))
    P = decoder_problem(circ, ep["check_type"])
    est = estimate(ep, P, W, blocks())
    json.dump(est, open(os.path.join(out, "estimate.json"), "w"), indent=1, default=float)
    steps.append(("4 resource estimate (Test 2d block model)", True))
    if order == "rb":
        rc3, _ = run([py, RBGEN, circ, out, epf], log)
        steps.append(("5 red-black package: order, gating tables, dependency distance (gen_rb_pkg.py)", rc3 == 0))
    report(out, circ, basis, ep, est, steps, W, wmsg.splitlines()[-1] if wmsg else "", tmsg.splitlines()[-1] if tmsg else "")
    if order == "rb" and rc3 == 0:
        open(os.path.join(out, "report.md"), "a").write("\n".join(rb_section(out)) + "\n")
    print(f"sortq build: {out} ({'all steps ok' if all(ok for _, ok in steps) else 'SOME STEPS FAILED'})")
    return all(ok for _, ok in steps)


def main():
    ap = argparse.ArgumentParser(prog="sortq")
    sp = ap.add_subparsers(dest="cmd", required=True)
    b = sp.add_parser("build", help="SORTQ flow for one circuit and decoder basis")
    b.add_argument("circuit"); b.add_argument("--basis", choices=["X", "Z"], required=True)
    b.add_argument("--out", default=None); b.add_argument("--window", type=int, default=None,
                                                           help="window W in rounds (default: code distance d)")
    b.add_argument("--order", choices=["sweep", "rb"], default="rb",
                   help="rb (default): also generate the red-black engine package; sweep: sweep-engine outputs only")
    a = ap.parse_args()
    import stim
    name = os.path.basename(a.circuit).split(",")[0].replace("circuit=", "")
    d = int(os.path.basename(a.circuit).split("distance=")[1].split(",")[0]) if "distance=" in a.circuit else 12
    out = a.out or os.path.join(IDEAS, "results", "test3f", "builds", f"{name}_{a.basis}dec")
    ok = build(os.path.abspath(a.circuit), a.basis, out, a.window or d, a.order)
    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
