"""Test 2c: generate synthesis harnesses h_<run>.sv for out-of-context runs of single blocks.

Harness = DUT (instance `dut`, keep_hierarchy) with
  - every input driven by a flip-flop of one long shift chain (serial input `sin`; shreg_extract off, so they are
    real FFs, not SRLs), so every input path starts at a register;
  - every output captured in a flip-flop of an XOR chain (oq <= {oq << 1} ^ outputs; serial output `sout`), so
    every output path ends at a register, no output is removable, and there is no high-fanout control net.
Resources are reported for the `dut` instance only (report_utilization -hierarchical); timing includes the
harness registers at both ends (the realistic case: inputs come from memories / registers).
Usage: python gen_harness.py OUTDIR      (writes h_<run>.sv for every run in RUNS, and runs.txt)
"""
import os, sys

PK = "  import round_wiring_pkg::*;\n  import engine_tables_pkg::*;\n"

# port lists: (name, dir, packed type). Types may use package constants and the localparams given in `lp`.
CNU = [("in_valid", "i", ""), ("syn", "i", ""), ("mask", "i", "[DEG-1:0]"), ("in_sign", "i", "[DEG-1:0]"),
       ("in_mag", "i", "[DEG-1:0][N-1:0]"), ("out_valid", "o", ""), ("out_sign", "o", "[DEG-1:0]"),
       ("out_mag", "o", "[DEG-1:0][N-1:0]"), ("min1", "o", "[N-1:0]"), ("min2", "o", "[N-1:0]"),
       ("min1_idx", "o", "[$clog2(DEG)-1:0]"), ("parity", "o", "")]
VNU = [("in_valid", "i", ""), ("init", "i", ""), ("mask", "i", "[DV-1:0]"), ("late", "i", "[DV-1:0]"),
       ("prior", "i", "[N:0]"), ("g8", "i", "[3:0]"), ("mpost", "i", "[N+2:0]"), ("c2v_sign", "i", "[DV-1:0]"),
       ("c2v_mag", "i", "[DV-1:0][N-1:0]"), ("out_valid", "o", ""), ("bias", "o", "[N+2:0]"),
       ("marg", "o", "[N+2:0]"), ("hard", "o", ""), ("v2c_sign", "o", "[DV-1:0]"), ("v2c_mag", "o", "[DV-1:0][N-1:0]")]
GAM = [("rst", "i", ""), ("start", "i", ""), ("next", "i", ""), ("load", "i", ""), ("load_g8", "i", "[3:0]"),
       ("g8", "o", "[3:0]"), ("state", "o", "[15:0]")]
PRF = [("pr_we", "i", ""), ("pr_wround", "i", "[3:0]"), ("pr_wtype", "i", "[3:0]"), ("pr_wdata", "i", "[N:0]"),
       ("round_idx", "i", "[3:0]"), ("prior_cur", "o", "[NTYPES-1:0][NPOS-1:0][N:0]"),
       ("prior_prev", "o", "[NTYPES-1:0][NPOS-1:0][N:0]")]
RS = [("rst", "i", ""), ("pr_we", "i", ""), ("pr_wround", "i", "[3:0]"), ("pr_wtype", "i", "[3:0]"),
      ("pr_wdata", "i", "[N:0]"), ("in_valid", "i", ""), ("in_ready", "o", ""), ("init", "i", ""),
      ("round_idx", "i", "[3:0]"), ("syn", "i", "[NPOS-1:0]"), ("cnu_mask", "i", "[NBASE-1:0]"),
      ("v2c_o0_st", "i", "[NE0-1:0][NPOS-1:0][N:0]"), ("v2c_o1_st", "i", "[NE1-1:0][NPOS-1:0][N:0]"),
      ("g8_cur", "i", "[NTYPES-1:0][NPOS-1:0][3:0]"), ("mpost_cur", "i", "[NTYPES-1:0][NPOS-1:0][N+2:0]"),
      ("c2v_cur_late_st", "i", "[NE1-1:0][NPOS-1:0][N:0]"), ("vmask_cur", "i", "[NTYPES-1:0][DVMAX-1:0]"),
      ("g8_prev", "i", "[NTYPES-1:0][NPOS-1:0][3:0]"), ("mpost_prev", "i", "[NTYPES-1:0][NPOS-1:0][N+2:0]"),
      ("c2v_prev_o0_st", "i", "[NE0-1:0][NPOS-1:0][N:0]"), ("vmask_prev", "i", "[NTYPES-1:0][DVMAX-1:0]"),
      ("cur_valid", "o", ""), ("prev_valid", "o", ""), ("out_valid", "o", ""),
      ("c2v_out", "o", "[NPOS-1:0][NBASE-1:0][N:0]"),
      ("cur_bias", "o", "[NTYPES-1:0][NPOS-1:0][N+2:0]"), ("cur_marg", "o", "[NTYPES-1:0][NPOS-1:0][N+2:0]"),
      ("prev_bias", "o", "[NTYPES-1:0][NPOS-1:0][N+2:0]"), ("prev_marg", "o", "[NTYPES-1:0][NPOS-1:0][N+2:0]"),
      ("cur_hard", "o", "[NTYPES-1:0][NPOS-1:0]"), ("prev_hard", "o", "[NTYPES-1:0][NPOS-1:0]"),
      ("cur_v2c", "o", "[NTYPES-1:0][NPOS-1:0][DVMAX-1:0][N:0]"),
      ("prev_v2c", "o", "[NTYPES-1:0][NPOS-1:0][DVMAX-1:0][N:0]")]
RSPF = [(("nxt_valid", "i", ""), ("nxt_round_idx", "i", "[3:0]")) if n == "round_idx" else ((n, d, t),) for n, d, t in RS]
RSPF = [x for grp in RSPF for x in grp]
CONV = [("in_valid", "i", ""), ("hard", "i", "[W-1:0][NTYPES-1:0][NPOS-1:0]"), ("syn", "i", "[W-1:0][NPOS-1:0]"),
        ("emask", "i", "[W-1:0][NBASE-1:0]"), ("out_valid", "o", ""), ("conv", "o", ""),
        ("unsat", "o", "[W-1:0][NPOS-1:0]")]
CTRL = [("rst", "i", ""), ("start", "i", ""), ("win_t", "i", "[7:0]"), ("last_r", "i", "[7:0]"),
        ("conv_valid", "i", ""), ("conv", "i", ""), ("busy", "o", ""), ("done", "o", ""), ("success", "o", ""),
        ("iter_total", "o", "[15:0]"), ("leg", "o", "[8:0]"), ("gamma_start", "o", ""), ("gamma_next", "o", ""),
        ("iter_start", "o", ""), ("conv_req", "o", ""), ("step_valid", "o", "[3:0]"), ("init", "o", "[3:0]"),
        ("step_g", "o", "[3:0][7:0]"), ("cnu_mask", "o", "[3:0][NBASE-1:0]"),
        ("vnu_mask_cur", "o", "[3:0][NTYPES-1:0][DVMAX-1:0]"), ("vnu_mask_prev", "o", "[3:0][NTYPES-1:0][DVMAX-1:0]"),
        ("prev_active", "o", "[3:0]")]
COMMIT = [("clear", "i", ""), ("in_valid", "i", ""), ("hard", "i", "[NTYPES-1:0][NPOS-1:0]"),
          ("types_present", "i", "[NTYPES-1:0]"), ("last", "i", ""), ("carry_en", "i", ""),
          ("obs", "o", "[NOBS-1:0]"), ("obs_valid", "o", ""), ("syn_corr_valid", "o", ""),
          ("syn_corr", "o", "[NPOS-1:0]")]
ROT = [("sa", "i", "[3:0]"), ("sb", "i", "[2:0]"), ("din", "i", "[71:0][4:0]"), ("dout", "o", "[71:0][4:0]")]
SMEM = [("rst", "i", ""), ("arr_valid", "i", ""), ("arr_data", "i", "[WIDTH-1:0]"), ("arr_ready", "o", ""),
        ("head", "o", "[3:0]"), ("count", "o", "[4:0]"), ("eng_re", "i", ""), ("eng_raddr", "i", "[3:0]"),
        ("eng_rdata", "o", "[WIDTH-1:0]"), ("eng_we", "i", ""), ("eng_waddr", "i", "[3:0]"),
        ("eng_wdata", "i", "[WIDTH-1:0]"), ("free", "i", ""), ("free_n", "i", "[4:0]")]
TOP = [("rst", "i", ""), ("start", "i", ""), ("win_t", "i", "[7:0]"), ("last_r", "i", "[7:0]"),
       ("arr_valid", "i", ""), ("arr_idx", "i", "[3:0]"), ("arr_data", "i", "[NPOS-1:0]"),
       ("pr_we", "i", ""), ("pr_wround", "i", "[3:0]"), ("pr_wtype", "i", "[3:0]"), ("pr_wdata", "i", "[N:0]"),
       ("done", "o", ""), ("success", "o", ""), ("iter_total", "o", "[15:0]"), ("obs", "o", "[NOBS-1:0]"),
       ("obs_valid", "o", ""), ("syn_corr", "o", "[NPOS-1:0]"), ("syn_corr_valid", "o", "")]

SMEM_W = 7920   # widest engine_top field (v2c_o0: 22 x 72 x 5)
# run name: (module, parameter overrides, harness localparams, ports)
RUNS = {
    "cnu":            ("cnu", ".N(4), .DEG(35), .OUT_REG(1'b1)", "N = 4, DEG = 35", CNU),
    "vnu":            ("vnu", ".N(4), .DV(6), .OUT_REG(1'b1)", "N = 4, DV = 6", VNU),
    "vnu_nosat":      ("vnu_nosat", ".N(4), .DV(6), .OUT_REG(1'b1)", "N = 4, DV = 6", VNU),
    "gamma_src":      ("gamma_src", ".LFSR_MODE(1'b1)", "N = 4", GAM),
    "prior_rf":       ("prior_rf", ".N(4), .NRND(13)", "N = 4", PRF),
    "round_step_p1":  ("round_step", ".N(4), .VNU_PASSES(1), .NRND(13)", "N = 4", RS),
    "round_step_p2":  ("round_step", ".N(4), .VNU_PASSES(2), .NRND(13)", "N = 4", RS),
    "conv_check":     ("conv_check", ".W(12)", "W = 12", CONV),
    "ctrl":           ("ctrl", ".W(12), .STEP_CYCLES(2), .NDUP(4), .RW(8)", "N = 4", CTRL),
    "commit":         ("commit", "", "N = 4", COMMIT),
    "rot2d":          ("rot2d", ".W(5), .A(12), .B(6), .PIPE(1'b1)", "N = 4", ROT),
    "state_mem_reg":    ("state_mem", f'.DEPTH(12), .WIDTH({SMEM_W}), .STORAGE("REG"), .RD_LAT(1)', f"WIDTH = {SMEM_W}", SMEM),
    "state_mem_lutram": ("state_mem", f'.DEPTH(12), .WIDTH({SMEM_W}), .STORAGE("LUTRAM"), .RD_LAT(1)', f"WIDTH = {SMEM_W}", SMEM),
    "state_mem_bram":   ("state_mem", f'.DEPTH(12), .WIDTH({SMEM_W}), .STORAGE("BRAM"), .RD_LAT(1)', f"WIDTH = {SMEM_W}", SMEM),
    "engine_top_p1_lutram": ("engine_top", '.N(4), .VNU_PASSES(1), .STORAGE("LUTRAM")', "N = 4", TOP),
    "engine_top_p1_bram":   ("engine_top", '.N(4), .VNU_PASSES(1), .STORAGE("BRAM")', "N = 4", TOP),
    "engine_top_p2_lutram": ("engine_top", '.N(4), .VNU_PASSES(2), .STORAGE("LUTRAM")', "N = 4", TOP),
    "engine_top_p2_bram":   ("engine_top", '.N(4), .VNU_PASSES(2), .STORAGE("BRAM")', "N = 4", TOP),
    # timing variant (prior prefetch + fan-out tree, convergence check overlapped with the next iteration)
    "round_step_pf_p1":  ("round_step_pf", ".N(4), .VNU_PASSES(1), .NRND(13)", "N = 4", RSPF),
    "round_step_pf_p2":  ("round_step_pf", ".N(4), .VNU_PASSES(2), .NRND(13)", "N = 4", RSPF),
    "ctrl_pf":           ("ctrl_pf", ".W(12), .STEP_CYCLES(2), .NDUP(4), .RW(8)", "N = 4", CTRL),
    "engine_top_pf_p1_lutram": ("engine_top_pf", '.N(4), .VNU_PASSES(1), .STORAGE("LUTRAM")', "N = 4", TOP),
    "engine_top_pf_p1_bram":   ("engine_top_pf", '.N(4), .VNU_PASSES(1), .STORAGE("BRAM")', "N = 4", TOP),
    "engine_top_pf_p2_lutram": ("engine_top_pf", '.N(4), .VNU_PASSES(2), .STORAGE("LUTRAM")', "N = 4", TOP),
    # follow-up: cur_valid copies for the forwarding muxes, two-level prior tree (2 steps ahead), vnu_nosat
    "engine_top_pf2_p1_lutram": ("engine_top_pf2", '.N(4), .VNU_PASSES(1), .STORAGE("LUTRAM")', "N = 4", TOP),
    "engine_top_pf2_p2_lutram": ("engine_top_pf2", '.N(4), .VNU_PASSES(2), .STORAGE("LUTRAM")', "N = 4", TOP),
    # Test 3d fixes (v2c_o0 write-back merge, no step-0 prev write, decode-start M(-1) = L0 fill), same module
    "engine_top_pf2fix_p1_lutram": ("engine_top_pf2", '.N(4), .VNU_PASSES(1), .STORAGE("LUTRAM")', "N = 4", TOP),
    # Test 2d calibration: the other check / error degrees of the X decoder (936 checks: 792 x 35, 72 x 25, 72 x 16;
    # 8,784 errors: degrees 2..6)
    "cnu_d16": ("cnu", ".N(4), .DEG(16), .OUT_REG(1'b1)", "N = 4, DEG = 16", CNU),
    "cnu_d25": ("cnu", ".N(4), .DEG(25), .OUT_REG(1'b1)", "N = 4, DEG = 25", CNU),
    **{f"vnu_d{d}": ("vnu", f".N(4), .DV({d}), .OUT_REG(1'b1)", f"N = 4, DV = {d}", VNU) for d in (2, 3, 4, 5)},
}


def harness(run, mod, params, lp, ports):
    ins = [p for p in ports if p[1] == "i"]; outs = [p for p in ports if p[1] == "o"]
    L = [f"// GENERATED by hw/synth/gen_harness.py — synthesis harness for run '{run}' ({mod}).",
         f"module h_{run} (input logic clk, input logic sin, output logic sout);", PK.rstrip("\n")]
    L.append(f"  localparam int {lp};")
    for n, d, t in ports:
        L.append(f"  logic {t} {n};")
    # input chain
    L.append("  (* shreg_extract = \"no\" *) logic [" + " + ".join(f"$bits({n})" for n, _, _ in ins) + " - 1:0] ich;")
    L.append("  always_ff @(posedge clk) ich <= {ich, sin};")
    L.append("  assign {" + ", ".join(n for n, _, _ in ins) + "} = ich;")
    # output chain
    L.append("  localparam int OW = " + " + ".join(f"$bits({n})" for n, _, _ in outs) + ";")
    L.append("  logic [OW-1:0] oq;")
    L.append("  always_ff @(posedge clk) oq <= {oq[OW-2:0], 1'b0} ^ {" + ", ".join(n for n, _, _ in outs) + "};")
    L.append("  assign sout = oq[OW-1];")
    pr = f" #({params})" if params else ""
    L.append(f"  (* keep_hierarchy = \"yes\" *) {mod}{pr} dut (.clk, " + ", ".join(f".{n}" for n, _, _ in ports) + ");")
    L.append("endmodule")
    return "\n".join(L) + "\n"


def main():
    out = sys.argv[1]
    os.makedirs(out, exist_ok=True)
    with open(os.path.join(out, "runs.txt"), "w") as f:
        for run, (mod, params, lp, ports) in RUNS.items():
            open(os.path.join(out, f"h_{run}.sv"), "w").write(harness(run, mod, params, lp, ports))
            f.write(f"{run} {mod}\n")
    print(f"{len(RUNS)} harnesses -> {out}")


if __name__ == "__main__":
    main()
