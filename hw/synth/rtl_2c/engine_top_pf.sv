// engine_top_pf.sv — Test 2c timing variant of engine_top.sv (SYNTHESIS ONLY, like engine_top.sv):
//   1. round_step_pf: priors prefetched one step ahead (the next round in the static order: g + 1, after the window's
//      last round the window's first round), registered, and fanned out through duplicated registers. The prefetch
//      for a step is issued in the start cycle of the step before it (and at `start` for the first step).
//   2. ctrl_pf: the convergence check of iteration t overlaps iteration t + 1 (same leg). Hard decisions get two
//      banks by iteration parity (like the marginals): conv_check and commit read the bank of the checked iteration,
//      so the writes of a discarded speculative iteration never reach the decode outputs. The prev write-back of the
//      marginals / hard decisions uses the bank latched with the step (pw_par), since the next step may belong to the
//      next iteration (in engine_top.sv the conv wait kept them apart).
// Everything else is engine_top.sv.
//
// (from engine_top.sv) Test 2c SYNTHESIS-ONLY integration of the Test 2a blocks (not functionally verified).
// One W-round window engine: ctrl -> (memory reads) -> round_step -> (memory writes), conv_check over the window,
// commit after the decode, 720 gamma_src lanes + g8 memory, prior register file (inside round_step).
//
// Memory layout (user-approved 2026-11-13; one state_mem per field, W slots, slot = window index i = g - win_t):
//   field        bits/slot                      read (step of round g)   write
//   v2c_o0       NE0 x 72 x 5  = 7,920          slot i                   cur v2c (offset-0 slots) -> i,
//                                                                         prev v2c (offset-0 slots) -> i - 1
//   c2v_o1       NE1 x 72 x 5  = 4,680          slot i + 1 (late)        CNU output, offset-1 edges -> i
//   marg A / B   ping-pong per iteration (write bank = iteration parity, M(t-1) read from the other bank):
//     HP_r       504 x 7 = 3,528 (7 two-round types)  slot i (cur)    cur -> i, prev -> i - 1
//     HP_rm1     504 x 7 = 3,528 (copy)               slot i - 1      same writes
//     NP         216 x 7 = 1,512 (3 one-round types)  slot i          cur -> i
//   g8_r         720 x 3 = 2,160 (g8 + 2, 3 bits)     slot i          lanes' draw at an init step -> i
//   g8_rm1       504 x 3 = 1,512 (copy, HP types)     slot i - 1      same
// Forwarded (no memory: read only by the next step of the same sweep, which follows immediately):
//   v2c_o1 (errors homed g on offset-1 edges -> check g + 1) and c2v_o0 (check g -> errors homed g on offset-0
//   edges, used as c2v_prev_o0_st by step g + 1). Captured at cur_valid; bypassed in that cycle.
// Registers: syndromes [W][72], hard decisions [W][720] (conv_check needs the whole window at once), emask [W][35].
// Timing: ctrl STEP_CYCLES = VNU_PASSES + 1. ctrl step at T -> memory reads at T (RD_LAT 1) -> round_step start at
// T + 1 -> cur results at T + 3, prev at T + 3 (P1, written at T + 4) / T + 4 (P2, written at T + 5).
// conv_req is delayed by VNU_PASSES + 3 cycles (all writes of the last step done) before conv_check.
// Simplifications (synthesis only): the window does not slide (slot = window index), syndromes are written by
// window index, commit's syndrome carry goes to an output port, prior register file rows = global round mod NRND.
module engine_top_pf
  import round_wiring_pkg::*;
  import engine_tables_pkg::*;
#(
  parameter int    N          = 4,
  parameter int    VNU_PASSES = 1,
  parameter string STORAGE    = "BRAM",
  parameter int    W          = 12,
  parameter int    C          = 8,
  parameter int    NRND       = 13,
  parameter int    RW         = 8,
  localparam int   MB = N + 3, MW = N + 1, P = VNU_PASSES + 1,
  localparam int   IW = $clog2(W), PRW = $clog2(NRND), TW = $clog2(NTYPES)
) (
  input  logic                clk,
  input  logic                rst,
  input  logic                start,
  input  logic [RW-1:0]       win_t,
  input  logic [RW-1:0]       last_r,
  // syndrome arrival (by window index)
  input  logic                arr_valid,
  input  logic [IW-1:0]       arr_idx,
  input  logic [NPOS-1:0]     arr_data,
  // prior register file load port
  input  logic                pr_we,
  input  logic [PRW-1:0]      pr_wround,
  input  logic [TW-1:0]       pr_wtype,
  input  logic [MW-1:0]       pr_wdata,
  // results
  output logic                done,
  output logic                success,
  output logic [15:0]         iter_total,
  output logic [NOBS-1:0]     obs,
  output logic                obs_valid,
  output logic [NPOS-1:0]     syn_corr,
  output logic                syn_corr_valid
);
  // ------------------------------------------------------------------ type groups (compile time)
  function automatic int n_hp();
    int n = 0; for (int t = 0; t < NTYPES; t++) if (HAS_PREV[t]) n++; return n;
  endfunction
  localparam int NHP = n_hp(), NNP = NTYPES - NHP;
  function automatic int hp_idx(input int t);          // rank of t among HAS_PREV types (or among the others)
    int n = 0; for (int u = 0; u < t; u++) if (HAS_PREV[u] == HAS_PREV[t]) n++; return n;
  endfunction

  // ------------------------------------------------------------------ ctrl
  localparam int NDUP = 4;
  logic conv_valid, conv, busy, gamma_start, gamma_next, iter_start, conv_req;
  logic [8:0] leg;
  logic [NDUP-1:0] step_valid, c_init, prev_active;
  logic [NDUP-1:0][RW-1:0] step_g;
  logic [NDUP-1:0][NBASE-1:0] c_cnu_mask;
  logic [NDUP-1:0][NTYPES-1:0][DVMAX-1:0] c_vmask_cur, c_vmask_prev;
  ctrl_pf #(.W(W), .STEP_CYCLES(P), .NDUP(NDUP), .RW(RW)) u_ctrl (
    .clk, .rst, .start, .win_t, .last_r, .conv_valid, .conv, .busy, .done, .success, .iter_total, .leg,
    .gamma_start, .gamma_next, .iter_start, .conv_req, .step_valid, .init(c_init), .step_g, .cnu_mask(c_cnu_mask),
    .vnu_mask_cur(c_vmask_cur), .vnu_mask_prev(c_vmask_prev), .prev_active);

  // window index of the step (copy 1 drives the memory addresses)
  logic [IW-1:0] i_rd, i_rd_m1, i_rd_p1;
  assign i_rd    = IW'(step_g[1] - win_t);
  assign i_rd_m1 = i_rd - 1'b1;
  assign i_rd_p1 = (i_rd == IW'(W - 1)) ? '0 : i_rd + 1'b1;

  logic [RW:0] wend, tw;                                // last round of the window: min(win_t + W - 1, last_r)
  assign tw   = {1'b0, win_t} + (RW+1)'(W - 1);
  assign wend = (tw < {1'b0, last_r}) ? tw : {1'b0, last_r};
  logic [PRW-1:0] win_ridx;
  assign win_ridx = PRW'(win_t % NRND);

  logic par;                                            // iteration parity: marginal / hard-decision write bank
  always_ff @(posedge clk) if (rst) par <= 1'b0; else if (iter_start) par <= ~par;

  // ------------------------------------------------------------------ step registers (round_step inputs, held)
  logic rs_start, rs_init; logic [RW-1:0] rs_g; logic [IW-1:0] rs_i; logic [PRW-1:0] rs_nridx;
  logic [NBASE-1:0] rs_cnu_mask; logic [NTYPES-1:0][DVMAX-1:0] rs_vmc, rs_vmp;
  logic [NPOS-1:0] rs_syn;
  logic [W-1:0][NPOS-1:0] syn_r;
  always_ff @(posedge clk) begin
    rs_start <= step_valid[0] && !rst;
    if (step_valid[0]) begin
      // prefetch: prior row of the NEXT step in the static round order (registered; used at this step's start)
      rs_init <= c_init[0]; rs_g <= step_g[0];
      rs_nridx <= PRW'(((({1'b0, step_g[0]} >= wend) ? {1'b0, win_t} : {1'b0, step_g[0]} + 1'b1)) % NRND);
      rs_i <= IW'(step_g[0] - win_t); rs_cnu_mask <= c_cnu_mask[0];
      rs_vmc <= c_vmask_cur[0]; rs_vmp <= c_vmask_prev[0]; rs_syn <= syn_r[IW'(step_g[0] - win_t)];
    end
  end

  // ------------------------------------------------------------------ gamma lanes (720) and g8 memory
  logic lane_next;
  assign lane_next = step_valid[3] && c_init[3] && (leg != '0);
  logic [NTYPES-1:0][NPOS-1:0][3:0] lane_g8;
  for (genvar t = 0; t < NTYPES; t++) begin : g_lt
    for (genvar p = 0; p < NPOS; p++) begin : g_lp
      /* verilator lint_off PINCONNECTEMPTY */
      gamma_src #(.LFSR_MODE(1'b1), .SEED(16'(((t * NPOS + p) + 1) * 16'h9E37))) u_g (
        .clk, .rst, .start(gamma_start), .next(lane_next), .load(1'b0), .load_g8('0), .g8(lane_g8[t][p]),
        .state());
      /* verilator lint_on PINCONNECTEMPTY */
    end
  end
  localparam int G8R = NTYPES * NPOS * 3, G8P = NHP * NPOS * 3;
  logic [G8R-1:0] g8r_wd, g8r_rd; logic [G8P-1:0] g8p_wd, g8p_rd;
  for (genvar t = 0; t < NTYPES; t++) begin : g_g8w
    for (genvar p = 0; p < NPOS; p++) begin : g_p
      assign g8r_wd[(t * NPOS + p) * 3 +: 3] = 3'(lane_g8[t][p] + 4'sd2);
      if (HAS_PREV[t]) begin : g_hp
        assign g8p_wd[(hp_idx(t) * NPOS + p) * 3 +: 3] = 3'(lane_g8[t][p] + 4'sd2);
      end
    end
  end
  /* verilator lint_off PINCONNECTEMPTY */
  state_mem #(.DEPTH(W), .WIDTH(G8R), .STORAGE(STORAGE), .RD_LAT(1)) u_m_g8r (
    .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(),
    .eng_re(step_valid[1]), .eng_raddr(i_rd), .eng_rdata(g8r_rd),
    .eng_we(rs_start && rs_init), .eng_waddr(rs_i), .eng_wdata(g8r_wd), .free(1'b0), .free_n('0));
  state_mem #(.DEPTH(W), .WIDTH(G8P), .STORAGE(STORAGE), .RD_LAT(1)) u_m_g8p (
    .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(),
    .eng_re(step_valid[1]), .eng_raddr(i_rd_m1), .eng_rdata(g8p_rd),
    .eng_we(rs_start && rs_init), .eng_waddr(rs_i), .eng_wdata(g8p_wd), .free(1'b0), .free_n('0));
  /* verilator lint_on PINCONNECTEMPTY */
  // g8 into round_step: at an init step the lanes' fresh draw (also written), else the memory
  logic [NTYPES-1:0][NPOS-1:0][3:0] g8_cur, g8_prev;
  for (genvar t = 0; t < NTYPES; t++) begin : g_g8r
    for (genvar p = 0; p < NPOS; p++) begin : g_p
      assign g8_cur[t][p] = rs_init ? lane_g8[t][p] : 4'({1'b0, g8r_rd[(t * NPOS + p) * 3 +: 3]} - 4'd2);
      if (HAS_PREV[t]) begin : g_hp
        assign g8_prev[t][p] = 4'({1'b0, g8p_rd[(hp_idx(t) * NPOS + p) * 3 +: 3]} - 4'd2);
      end else begin : g_np
        assign g8_prev[t][p] = '0;
      end
    end
  end

  // ------------------------------------------------------------------ round_step
  logic rs_ready, cur_valid, prev_valid, out_valid;
  logic [NE0-1:0][NPOS-1:0][MW-1:0] v2c_o0_st, c2v_prev_o0_st;
  logic [NE1-1:0][NPOS-1:0][MW-1:0] v2c_o1_st, c2v_cur_late_st;
  logic [NTYPES-1:0][NPOS-1:0][MB-1:0] mpost_cur, mpost_prev, cur_bias, cur_marg, prev_bias, prev_marg;
  logic [NPOS-1:0][NBASE-1:0][MW-1:0] c2v_out;
  logic [NTYPES-1:0][NPOS-1:0] cur_hard, prev_hard;
  logic [NTYPES-1:0][NPOS-1:0][DVMAX-1:0][MW-1:0] cur_v2c, prev_v2c;
  round_step_pf #(.N(N), .VNU_PASSES(VNU_PASSES), .NRND(NRND)) u_rs (
    .clk, .rst, .pr_we, .pr_wround, .pr_wtype, .pr_wdata,
    .in_valid(rs_start), .in_ready(rs_ready), .init(rs_init),
    .nxt_valid(rs_start || start), .nxt_round_idx(start ? win_ridx : rs_nridx), .syn(rs_syn),
    .cnu_mask(rs_cnu_mask), .v2c_o0_st, .v2c_o1_st, .g8_cur, .mpost_cur, .c2v_cur_late_st, .vmask_cur(rs_vmc),
    .g8_prev, .mpost_prev, .c2v_prev_o0_st, .vmask_prev(rs_vmp),
    .cur_valid, .prev_valid, .out_valid, .c2v_out, .cur_bias, .cur_marg, .prev_bias, .prev_marg,
    .cur_hard, .prev_hard, .cur_v2c, .prev_v2c);

  // back wiring of the CNU outputs to the error side (pure wiring, same generated module)
  logic [0:0][NPOS-1:0][NBASE-1:0][MW-1:0] bw_cnu_in, bw_cnu_out;
  logic [0:0][NE0-1:0][NPOS-1:0][MW-1:0]   bw_c2v_o0;
  logic [0:0][NE1-1:0][NPOS-1:0][MW-1:0]   bw_c2v_o1;
  assign bw_cnu_out[0] = c2v_out;
  /* verilator lint_off UNUSEDSIGNAL */
  logic [0:0][NPOS-1:0][NBASE-1:0][MW-1:0] bw_unused; assign bw_unused = bw_cnu_in;
  /* verilator lint_on UNUSEDSIGNAL */
  round_wiring #(.W(MW), .K_ROUNDS(1)) u_bw (
    .v2c_o0('0), .v2c_o1('0), .cnu_in(bw_cnu_in), .cnu_out(bw_cnu_out), .c2v_o0(bw_c2v_o0), .c2v_o1(bw_c2v_o1));

  // error-side views of the VNU outputs, by base edge
  logic [NE0-1:0][NPOS-1:0][MW-1:0] cur_v2c_o0, prev_v2c_o0;
  logic [NE1-1:0][NPOS-1:0][MW-1:0] cur_v2c_o1;
  for (genvar k = 0; k < NBASE; k++) begin : g_ev
    for (genvar p = 0; p < NPOS; p++) begin : g_p
      if (BE_OFF[k] == 0) begin : g_o0
        assign cur_v2c_o0[BE_IDX[k]][p]  = cur_v2c[BE_TYPE[k]][p][BE_SLOT[k]];
        assign prev_v2c_o0[BE_IDX[k]][p] = prev_v2c[BE_TYPE[k]][p][BE_SLOT[k]];
      end else begin : g_o1
        assign cur_v2c_o1[BE_IDX[k]][p]  = cur_v2c[BE_TYPE[k]][p][BE_SLOT[k]];
      end
    end
  end

  // ------------------------------------------------------------------ forwarding (v2c_o1, c2v_o0)
  logic [NE1-1:0][NPOS-1:0][MW-1:0] fw_v2c_o1;
  logic [NE0-1:0][NPOS-1:0][MW-1:0] fw_c2v_o0;
  always_ff @(posedge clk) if (cur_valid) begin fw_v2c_o1 <= cur_v2c_o1; fw_c2v_o0 <= bw_c2v_o0[0]; end
  assign v2c_o1_st      = cur_valid ? cur_v2c_o1   : fw_v2c_o1;
  assign c2v_prev_o0_st = cur_valid ? bw_c2v_o0[0] : fw_c2v_o0;

  // ------------------------------------------------------------------ write-back sequencing
  // cur results written at cur_valid; prev results registered at prev_valid and written one cycle later.
  logic wpar;                                            // bank written by the step in flight
  always_ff @(posedge clk) if (rs_start) wpar <= par;
  logic [IW-1:0] wb_i; logic pw_v; logic [IW-1:0] pw_i; logic pw_par;
  always_ff @(posedge clk) if (rs_start) wb_i <= rs_i;
  logic [NE0-1:0][NPOS-1:0][MW-1:0] pw_v2c_o0;
  logic [NHP-1:0][NPOS-1:0][MB-1:0] pw_marg;
  always_ff @(posedge clk) begin
    pw_v <= prev_valid && !rst;
    if (prev_valid) begin pw_i <= wb_i - 1'b1; pw_v2c_o0 <= prev_v2c_o0; pw_par <= wpar; end
  end

  // v2c_o0 memory
  localparam int WV0 = NE0 * NPOS * MW, WC1 = NE1 * NPOS * MW;
  logic [WV0-1:0] v2c_o0_rd;
  /* verilator lint_off PINCONNECTEMPTY */
  state_mem #(.DEPTH(W), .WIDTH(WV0), .STORAGE(STORAGE), .RD_LAT(1)) u_m_v2c_o0 (
    .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(),
    .eng_re(step_valid[1]), .eng_raddr(i_rd), .eng_rdata(v2c_o0_rd),
    .eng_we(cur_valid || pw_v), .eng_waddr(cur_valid ? wb_i : pw_i),
    .eng_wdata(cur_valid ? WV0'(cur_v2c_o0) : WV0'(pw_v2c_o0)), .free(1'b0), .free_n('0));
  assign v2c_o0_st = v2c_o0_rd;
  // c2v_o1 memory (error-indexed, slot = check round), read at i + 1 (late edges of the errors homed g)
  logic [WC1-1:0] c2v_o1_rd;
  state_mem #(.DEPTH(W), .WIDTH(WC1), .STORAGE(STORAGE), .RD_LAT(1)) u_m_c2v_o1 (
    .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(),
    .eng_re(step_valid[1]), .eng_raddr(i_rd_p1), .eng_rdata(c2v_o1_rd),
    .eng_we(cur_valid), .eng_waddr(wb_i), .eng_wdata(WC1'(bw_c2v_o1[0])), .free(1'b0), .free_n('0));
  /* verilator lint_on PINCONNECTEMPTY */
  assign c2v_cur_late_st = c2v_o1_rd;

  // ------------------------------------------------------------------ marginal ping-pong banks
  localparam int WHP = NHP * NPOS * MB, WNP = NNP * NPOS * MB;
  logic [NHP-1:0][NPOS-1:0][MB-1:0] cur_marg_hp, prev_marg_hp;
  logic [NNP-1:0][NPOS-1:0][MB-1:0] cur_marg_np;
  logic [NHP-1:0][NPOS-1:0][MB-1:0] mp_hp_r [2], mp_hp_rm1 [2];
  logic [NNP-1:0][NPOS-1:0][MB-1:0] mp_np_r [2];
  for (genvar t = 0; t < NTYPES; t++) begin : g_mg
    if (HAS_PREV[t]) begin : g_hp
      assign cur_marg_hp[hp_idx(t)]  = cur_marg[t];
      assign prev_marg_hp[hp_idx(t)] = prev_marg[t];
    end else begin : g_np
      assign cur_marg_np[hp_idx(t)]  = cur_marg[t];
    end
  end
  always_ff @(posedge clk) if (prev_valid) pw_marg <= prev_marg_hp;

  for (genvar b = 0; b < 2; b++) begin : g_bank
    logic we_cur, we_prev;
    assign we_cur  = cur_valid && (wpar == 1'(b));
    assign we_prev = pw_v && (pw_par == 1'(b));
    logic re;
    assign re = step_valid[1] && (par != 1'(b));         // M(t-1) = the bank not written this iteration
    /* verilator lint_off PINCONNECTEMPTY */
    state_mem #(.DEPTH(W), .WIDTH(WHP), .STORAGE(STORAGE), .RD_LAT(1)) u_m_hp_r (
      .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(),
      .eng_re(re), .eng_raddr(i_rd), .eng_rdata(mp_hp_r[b]),
      .eng_we(we_cur || we_prev), .eng_waddr(we_cur ? wb_i : pw_i),
      .eng_wdata(we_cur ? WHP'(cur_marg_hp) : WHP'(pw_marg)), .free(1'b0), .free_n('0));
    state_mem #(.DEPTH(W), .WIDTH(WHP), .STORAGE(STORAGE), .RD_LAT(1)) u_m_hp_rm1 (
      .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(),
      .eng_re(re), .eng_raddr(i_rd_m1), .eng_rdata(mp_hp_rm1[b]),
      .eng_we(we_cur || we_prev), .eng_waddr(we_cur ? wb_i : pw_i),
      .eng_wdata(we_cur ? WHP'(cur_marg_hp) : WHP'(pw_marg)), .free(1'b0), .free_n('0));
    state_mem #(.DEPTH(W), .WIDTH(WNP), .STORAGE(STORAGE), .RD_LAT(1)) u_m_np_r (
      .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(),
      .eng_re(re), .eng_raddr(i_rd), .eng_rdata(mp_np_r[b]),
      .eng_we(we_cur), .eng_waddr(wb_i), .eng_wdata(WNP'(cur_marg_np)), .free(1'b0), .free_n('0));
    /* verilator lint_on PINCONNECTEMPTY */
  end
  logic rpar;                                            // read bank of the step in flight
  always_ff @(posedge clk) if (step_valid[1]) rpar <= ~par;
  for (genvar t = 0; t < NTYPES; t++) begin : g_mp
    if (HAS_PREV[t]) begin : g_hp
      assign mpost_cur[t]  = rpar ? mp_hp_r[1][hp_idx(t)]   : mp_hp_r[0][hp_idx(t)];
      assign mpost_prev[t] = rpar ? mp_hp_rm1[1][hp_idx(t)] : mp_hp_rm1[0][hp_idx(t)];
    end else begin : g_np
      assign mpost_cur[t]  = rpar ? mp_np_r[1][hp_idx(t)] : mp_np_r[0][hp_idx(t)];
      assign mpost_prev[t] = '0;
    end
  end

  // ------------------------------------------------------------------ hard decisions, syndromes, emask (registers)
  logic [W-1:0][NTYPES-1:0][NPOS-1:0] hard_r [2];          // bank = iteration parity
  logic cbank;                                             // bank of the iteration being checked / committed
  always_ff @(posedge clk) if (conv_req) cbank <= par;
  logic [W-1:0][NBASE-1:0] emask_r;
  logic [NTYPES-1:0][NPOS-1:0] pw_hard;
  always_ff @(posedge clk) begin
    if (prev_valid) pw_hard <= prev_hard;
    if (cur_valid) hard_r[wpar][wb_i] <= cur_hard;
    if (pw_v) for (int t = 0; t < NTYPES; t++) if (HAS_PREV[t]) hard_r[pw_par][pw_i][t] <= pw_hard[t];
    if (step_valid[2]) emask_r[IW'(step_g[2] - win_t)] <= c_cnu_mask[2];
    if (arr_valid) syn_r[arr_idx] <= arr_data;
  end

  // ------------------------------------------------------------------ convergence check
  localparam int CDLY = VNU_PASSES + 3;
  logic [CDLY-1:0] creq_d;
  always_ff @(posedge clk) creq_d <= rst ? '0 : {creq_d[CDLY-2:0], conv_req};
  /* verilator lint_off PINCONNECTEMPTY */
  conv_check #(.W(W)) u_conv (
    .clk, .in_valid(creq_d[CDLY-1]), .hard(hard_r[cbank]), .syn(syn_r), .emask(emask_r), .out_valid(conv_valid),
    .conv, .unsat());
  /* verilator lint_on PINCONNECTEMPTY */

  // ------------------------------------------------------------------ commit (after the decode, one round per beat)
  logic done_q, cm_run; logic [IW-1:0] cm_i;
  always_ff @(posedge clk) begin
    done_q <= done;
    if (rst || start) begin cm_run <= 1'b0; cm_i <= '0; end
    else if (done && !done_q) begin cm_run <= 1'b1; cm_i <= '0; end
    else if (cm_run) begin if (cm_i == IW'(C - 1)) cm_run <= 1'b0; else cm_i <= cm_i + 1'b1; end
  end
  logic [RW:0] cm_h;
  assign cm_h = {1'b0, win_t} + (RW+1)'(cm_i);
  logic [NTYPES-1:0] cm_tp;
  assign cm_tp = (cm_h == '0) ? TP_FIRST : (cm_h == {1'b0, last_r}) ? TP_LAST : '1;
  commit u_commit (
    .clk, .clear(start), .in_valid(cm_run), .hard(hard_r[cbank][cm_i]), .types_present(cm_tp),
    .last(cm_i == IW'(C - 1)), .carry_en(({1'b0, win_t} + (RW+1)'(C)) <= {1'b0, last_r}),
    .obs, .obs_valid, .syn_corr_valid, .syn_corr);

  /* verilator lint_off UNUSEDSIGNAL */
  logic unused; assign unused = ^{busy, rs_ready, out_valid, prev_active, cur_bias, prev_bias, step_valid[3:2]};
  /* verilator lint_on UNUSEDSIGNAL */
endmodule
