// engine_top_rb.sv — Test 2f: red-black pipelined round engine (VNU_PASSES 1, LUTRAM), one round step per cycle in the
// order 0, 2, ..., 12, 1, 3, ..., 11, no forwarding. Same decoder as engine_top_pf2 (ARITHMETIC.md, int4.2.8); only the
// round order is the red-black one (Test 1g: bit-identical to the 2-layer even / odd schedule).
// Blocks: ctrl_rb -> (memory reads) -> round_step_rb -> (memory writes); conv_check (overlapped with the next
// iteration); commit; 720 gamma lanes (gamma_src, unchanged); prior register file inside round_step_rb.
//
// Why no forwarding: two steps that touch a common error are >= HAZ_DIST = 6 issue slots apart (rb_pkg, from H;
// consecutive steps never share an error). Every field is read at a fixed stage and written at a fixed later stage;
// the latest write is 4 cycles after the earliest read (v2c: read S2, write S6), so a dependent step always reads
// after the write. LUTRAM = synchronous write, asynchronous read: a write in cycle t is seen by a read in t + 1, not t;
// so read-to-write <= HAZ_DIST - 1 = 5 cycles is the maximum this order allows with no stall and no bypass.
//
// Memory: banked by home-round parity (window index i: bank i[0], address i >> 1, 7 slots). A step on round g reads and
// writes the errors homed g ("cur", bank g[0]) and g - 1 ("prev", the other bank): one read and one write per bank and
// field per cycle. Partial writes use separate instances per type class (write enables per type class), so the
// one-round types are never overwritten by the prev write-back (the Test 3d bug cannot occur, no merge register).
//   field  per home h                                   read (stage, role)          write (stage, role)
//   VHP    v2c of the 7 two-round types, 23 edges        S2: o0 part cur, o1 part prev   S6: cur and prev (bank mux)
//   VNP    v2c of the 3 one-round types, 12 edges        S2: cur                         S6: cur
//   C0     c2v round h -> two-round types (10 o0 edges)  S4: prev (c2v_prev_o0)          S5: cur (CNU output)
//   C1     c2v round h+1 -> errors homed h (13 o1 edges) S4: cur (late c2v)              S5: prev (CNU output)
//   MHP/MNP marginals, 2 copies by iteration parity      S3: copy ~par (= M(t-1))       S6: copy par
//   G      g8 + 2 (3 bits), all 10 types                 S3: cur and prev                S3 (even rounds, init step,
//                                                                                        lanes) / prefill (odd rounds)
// Decode start (no extra cycles): first iteration M(t-1) = prior (M(-1) = L0, in round_step_rb); leg 0 g8 = G0 constant.
// Relay legs >= 1: the even pass needs the new g8 of two home rounds per step (g and g - 1), so the lanes pre-draw the
// odd rounds during the leg-end wait (prefill, 6 cycles, after the last step's g8 read) and draw the even rounds at the
// even init steps (S2; value used and written at S3). 13 draws per leg, as engine_top_pf2.
// Simplifications as engine_top_pf2 / Test 3d: one window (win_t = 0, W = 13 = NRND, slot = window index = prior row),
// syndromes by window index, commit's syndrome carry goes to an output port.
module engine_top_rb
  import round_wiring_pkg::*;
  import engine_tables_pkg::*;
  import rb_pkg::*;
#(
  parameter int    N         = 4,
  parameter string STORAGE   = "LUTRAM",
  parameter int    W         = 13,
  parameter int    C         = 13,
  parameter int    NRND      = 13,
  parameter int    RW        = 8,
  parameter bit    LFSR_MODE = 1'b1,
  parameter int    V_WB_DLY  = 0,        // experiment only: extra register stages on the v2c (VHP / VNP) write-back
  localparam int   MB = N + 3, MW = N + 1,
  localparam int   IW = $clog2(W), PRW = $clog2(NRND), TW = $clog2(NTYPES),
  localparam int   NBK = (W + 1) / 2, AW = $clog2(NBK)
) (
  input  logic                clk,
  input  logic                rst,
  input  logic                start,
  input  logic [RW-1:0]       win_t,
  input  logic [RW-1:0]       last_r,
  input  logic                arr_valid,
  input  logic [IW-1:0]       arr_idx,
  input  logic [NPOS-1:0]     arr_data,
  input  logic                pr_we,
  input  logic [PRW-1:0]      pr_wround,
  input  logic [TW-1:0]       pr_wtype,
  input  logic [MW-1:0]       pr_wdata,
`ifdef RB_G8LOAD
  input  logic [NTYPES-1:0][NPOS-1:0][3:0] g8_ld_data,      // simulation: g8 of (lane_leg, lane_home)
`endif
  output logic                lane_draw,
  output logic [8:0]          lane_leg,
  output logic [IW-1:0]       lane_home,
  output logic                done,
  output logic                success,
  output logic [15:0]         iter_total,
  output logic [NOBS-1:0]     obs,
  output logic                obs_valid,
  output logic [NPOS-1:0]     syn_corr,
  output logic                syn_corr_valid
);
  // ------------------------------------------------------------------ type / edge classes (compile time)
  function automatic int n_hp();
    int n = 0; for (int t = 0; t < NTYPES; t++) if (HAS_PREV[t]) n++; return n;
  endfunction
  localparam int NHP = n_hp(), NNP = NTYPES - NHP;
  function automatic int hp_idx(input int t);
    int n = 0; for (int u = 0; u < t; u++) if (HAS_PREV[u] == HAS_PREV[t]) n++; return n;
  endfunction
  function automatic int k_of_e0(input int e0);           // base edge of offset-0 index e0
    for (int k = 0; k < NBASE; k++) if (BE_OFF[k] == 0 && BE_IDX[k] == e0) return k;
    return -1;
  endfunction
  function automatic bit e0_hp(input int e0); return HAS_PREV[BE_TYPE[k_of_e0(e0)]]; endfunction
  function automatic int e0_rank(input int e0);           // rank among offset-0 edges of the same type class
    int n = 0; for (int u = 0; u < e0; u++) if (e0_hp(u) == e0_hp(e0)) n++; return n;
  endfunction
  function automatic int n_e0hp();
    int n = 0; for (int u = 0; u < NE0; u++) if (e0_hp(u)) n++; return n;
  endfunction
  localparam int NE0HP = n_e0hp(), NE0NP = NE0 - NE0HP;

  typedef struct packed { logic [NE1-1:0][NPOS-1:0][MW-1:0] o1; logic [NE0HP-1:0][NPOS-1:0][MW-1:0] o0; } vhp_t;
  typedef logic [NE0NP-1:0][NPOS-1:0][MW-1:0] vnp_t;
  typedef logic [NE0HP-1:0][NPOS-1:0][MW-1:0] c0_t;
  typedef logic [NE1-1:0][NPOS-1:0][MW-1:0]   c1_t;
  typedef logic [NHP-1:0][NPOS-1:0][MB-1:0]   mhp_t;
  typedef logic [NNP-1:0][NPOS-1:0][MB-1:0]   mnp_t;
  typedef logic [NTYPES-1:0][NPOS-1:0][2:0]   g_t;

  // ------------------------------------------------------------------ ctrl
  localparam int NDUP = 4;
  logic conv_valid, conv, busy, gamma_next, iter_start, conv_req, conv_par, pre_go, pre_busy, c_done;
  logic [8:0] leg;
  logic [NDUP-1:0] step_valid, c_init, c_first, c_leg0, c_pass, c_par, prev_active;
  logic [NDUP-1:0][RW-1:0] step_g;
  logic [NDUP-1:0][NBASE-1:0] c_cnu_mask;
  logic [NDUP-1:0][NTYPES-1:0][DVMAX-1:0] c_vmask_cur, c_vmask_prev;
  ctrl_rb #(.W(W), .NDUP(NDUP), .RW(RW)) u_ctrl (
    .clk, .rst, .start, .win_t, .last_r, .conv_valid, .conv, .pre_busy, .busy, .done(c_done), .success, .iter_total,
    .leg, .gamma_next, .iter_start, .conv_req, .conv_par, .pre_go, .step_valid, .init(c_init), .first(c_first),
    .leg0(c_leg0), .pass(c_pass), .par(c_par), .step_g, .cnu_mask(c_cnu_mask), .vnu_mask_cur(c_vmask_cur),
    .vnu_mask_prev(c_vmask_prev), .prev_active);
  assign done = c_done;

  // ------------------------------------------------------------------ step pipeline (memory side), S0 = ctrl outputs
  typedef struct packed { logic v; logic [IW-1:0] i; logic init, leg0, pass, par, pa; } sp_t;
  sp_t sp [7];
  assign sp[0] = '{v: step_valid[1], i: IW'(step_g[1] - win_t), init: c_init[1], leg0: c_leg0[1], pass: c_pass[1],
                   par: c_par[1], pa: prev_active[1]};
  for (genvar s = 1; s < 7; s++) begin : g_sp
    always_ff @(posedge clk) if (rst) sp[s] <= '0; else sp[s] <= sp[s-1];
  end
  function automatic logic [AW-1:0] baddr(input logic [IW-1:0] i, input int b);   // bank b address of the step
    if (b == int'(i[0])) return AW'(i >> 1);
    else return (i == '0) ? '0 : AW'((i - 1'b1) >> 1);
  endfunction

  // ------------------------------------------------------------------ syndromes, emask (registers)
  logic [W-1:0][NPOS-1:0] syn_r;
  logic [W-1:0][NBASE-1:0] emask_r;
  always_ff @(posedge clk) begin
    if (arr_valid) syn_r[arr_idx] <= arr_data;
    if (step_valid[2]) emask_r[IW'(step_g[2] - win_t)] <= c_cnu_mask[2];
  end

  // ------------------------------------------------------------------ memories (two banks)
  vhp_t vhp_rd [2]; vnp_t vnp_rd [2]; c0_t c0_rd [2]; c1_t c1_rd [2]; g_t g_rd [2];
  mhp_t mhp_rd [2][2]; mnp_t mnp_rd [2][2];                        // [bank][copy]
  vhp_t vhp_wd [2]; vnp_t vnp_wd; c0_t c0_wd; c1_t c1_wd; g_t g_wd [2]; mhp_t mhp_wd [2]; mnp_t mnp_wd;
  logic vhp_we [2], vnp_we [2], c0_we [2], c1_we [2], g_we [2], mhp_we [2][2], mnp_we [2][2];
  logic [AW-1:0] a2 [2], a3 [2], a4 [2], a5 [2], a6 [2], g_wa [2];
  logic vhp_we_x [2], vnp_we_x [2]; logic [AW-1:0] va_x [2];      // v2c write ports as seen by the memories
  for (genvar b = 0; b < 2; b++) begin : g_bank
    assign a2[b] = baddr(sp[2].i, b); assign a3[b] = baddr(sp[3].i, b); assign a4[b] = baddr(sp[4].i, b);
    assign a5[b] = baddr(sp[5].i, b); assign a6[b] = baddr(sp[6].i, b);
    /* verilator lint_off PINCONNECTEMPTY */
    // v2c write port, optionally delayed by V_WB_DLY register stages (experiment; 0 in the design)
    logic vhp_we_d [V_WB_DLY+1], vnp_we_d [V_WB_DLY+1]; logic [AW-1:0] va_d [V_WB_DLY+1];
    vhp_t vhp_wd_d [V_WB_DLY+1]; vnp_t vnp_wd_d [V_WB_DLY+1];
    assign vhp_we_d[0] = vhp_we[b]; assign vnp_we_d[0] = vnp_we[b]; assign va_d[0] = a6[b];
    assign vhp_wd_d[0] = vhp_wd[b]; assign vnp_wd_d[0] = vnp_wd;
    for (genvar z = 1; z <= V_WB_DLY; z++) begin : g_dly
      always_ff @(posedge clk) begin
        vhp_we_d[z] <= rst ? 1'b0 : vhp_we_d[z-1]; vnp_we_d[z] <= rst ? 1'b0 : vnp_we_d[z-1];
        va_d[z] <= va_d[z-1]; vhp_wd_d[z] <= vhp_wd_d[z-1]; vnp_wd_d[z] <= vnp_wd_d[z-1];
      end
    end
    assign vhp_we_x[b] = vhp_we_d[V_WB_DLY]; assign vnp_we_x[b] = vnp_we_d[V_WB_DLY]; assign va_x[b] = va_d[V_WB_DLY];
    state_mem #(.DEPTH(NBK), .WIDTH($bits(vhp_t)), .STORAGE(STORAGE), .RD_LAT(0)) u_vhp (
      .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(), .eng_re(1'b1), .eng_raddr(a2[b]),
      .eng_rdata(vhp_rd[b]), .eng_we(vhp_we_d[V_WB_DLY]), .eng_waddr(va_d[V_WB_DLY]), .eng_wdata(vhp_wd_d[V_WB_DLY]),
      .free(1'b0), .free_n('0));
    state_mem #(.DEPTH(NBK), .WIDTH($bits(vnp_t)), .STORAGE(STORAGE), .RD_LAT(0)) u_vnp (
      .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(), .eng_re(1'b1), .eng_raddr(a2[b]),
      .eng_rdata(vnp_rd[b]), .eng_we(vnp_we_d[V_WB_DLY]), .eng_waddr(va_d[V_WB_DLY]), .eng_wdata(vnp_wd_d[V_WB_DLY]),
      .free(1'b0), .free_n('0));
    state_mem #(.DEPTH(NBK), .WIDTH($bits(c0_t)), .STORAGE(STORAGE), .RD_LAT(0)) u_c0 (
      .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(), .eng_re(1'b1), .eng_raddr(a4[b]),
      .eng_rdata(c0_rd[b]), .eng_we(c0_we[b]), .eng_waddr(a5[b]), .eng_wdata(c0_wd), .free(1'b0), .free_n('0));
    state_mem #(.DEPTH(NBK), .WIDTH($bits(c1_t)), .STORAGE(STORAGE), .RD_LAT(0)) u_c1 (
      .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(), .eng_re(1'b1), .eng_raddr(a4[b]),
      .eng_rdata(c1_rd[b]), .eng_we(c1_we[b]), .eng_waddr(a5[b]), .eng_wdata(c1_wd), .free(1'b0), .free_n('0));
    state_mem #(.DEPTH(NBK), .WIDTH($bits(g_t)), .STORAGE(STORAGE), .RD_LAT(0)) u_g (
      .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(), .eng_re(1'b1), .eng_raddr(a3[b]),
      .eng_rdata(g_rd[b]), .eng_we(g_we[b]), .eng_waddr(g_wa[b]), .eng_wdata(g_wd[b]), .free(1'b0), .free_n('0));
    for (genvar c = 0; c < 2; c++) begin : g_cp
      state_mem #(.DEPTH(NBK), .WIDTH($bits(mhp_t)), .STORAGE(STORAGE), .RD_LAT(0)) u_mhp (
        .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(), .eng_re(1'b1), .eng_raddr(a3[b]),
        .eng_rdata(mhp_rd[b][c]), .eng_we(mhp_we[b][c]), .eng_waddr(a6[b]), .eng_wdata(mhp_wd[b]), .free(1'b0),
        .free_n('0));
      state_mem #(.DEPTH(NBK), .WIDTH($bits(mnp_t)), .STORAGE(STORAGE), .RD_LAT(0)) u_mnp (
        .clk, .rst, .arr_valid(1'b0), .arr_data('0), .arr_ready(), .head(), .count(), .eng_re(1'b1), .eng_raddr(a3[b]),
        .eng_rdata(mnp_rd[b][c]), .eng_we(mnp_we[b][c]), .eng_waddr(a6[b]), .eng_wdata(mnp_wd), .free(1'b0),
        .free_n('0));
    end
    /* verilator lint_on PINCONNECTEMPTY */
  end

  // ------------------------------------------------------------------ gamma lanes and prefill
  logic [2:0] pre_dly; logic pre_run, pre_w; logic [AW-1:0] pre_cnt, pre_wcnt;
  localparam int NODD = W / 2;
  always_ff @(posedge clk) begin
    if (rst || start) begin pre_dly <= '0; pre_run <= 1'b0; pre_cnt <= '0; pre_w <= 1'b0; pre_wcnt <= '0; end
    else begin
      pre_dly <= {pre_dly[1:0], pre_go};
      if (pre_dly[2]) begin pre_run <= 1'b1; pre_cnt <= '0; end      // first draw 3 cycles after the last step
      else if (pre_run) begin
        if (pre_cnt == AW'(NODD - 1)) pre_run <= 1'b0;
        pre_cnt <= pre_cnt + 1'b1;
      end
      pre_w <= pre_run; pre_wcnt <= pre_cnt;                          // write one cycle after the draw
    end
  end
  assign pre_busy = pre_go || (|pre_dly) || pre_run || pre_w;
  logic init_draw;
  assign init_draw = sp[2].v && sp[2].init && !sp[2].pass && !sp[2].leg0;     // even init step of leg >= 1, at S2
  assign lane_draw = pre_run || init_draw;
  assign lane_home = pre_run ? IW'({pre_cnt, 1'b1}) : sp[2].i;
  assign lane_leg  = pre_run ? leg + 1'b1 : leg;
  logic [NTYPES-1:0][NPOS-1:0][3:0] lane_g8;
  for (genvar t = 0; t < NTYPES; t++) begin : g_lt
    for (genvar p = 0; p < NPOS; p++) begin : g_lp
      /* verilator lint_off PINCONNECTEMPTY */
`ifdef RB_G8LOAD
      gamma_src #(.LFSR_MODE(1'b0), .SEED(16'(((t * NPOS + p) + 1) * 16'h9E37))) u_g (
        .clk, .rst, .start(start), .next(1'b0), .load(lane_draw), .load_g8(g8_ld_data[t][p]), .g8(lane_g8[t][p]),
        .state());
`else
      gamma_src #(.LFSR_MODE(LFSR_MODE), .SEED(16'(((t * NPOS + p) + 1) * 16'h9E37))) u_g (
        .clk, .rst, .start(start), .next(lane_draw), .load(1'b0), .load_g8('0), .g8(lane_g8[t][p]), .state());
`endif
      /* verilator lint_on PINCONNECTEMPTY */
    end
  end
  g_t lane_enc;
  for (genvar t = 0; t < NTYPES; t++) begin : g_le
    for (genvar p = 0; p < NPOS; p++) begin : g_p
      assign lane_enc[t][p] = 3'(lane_g8[t][p] + 4'sd2);
    end
  end
  // G writes: bank 0 (even rounds) at an even init step (S3), bank 1 (odd rounds) by the prefill
  assign g_we[0] = sp[3].v && sp[3].init && !sp[3].pass && !sp[3].leg0;
  assign g_wa[0] = AW'(sp[3].i >> 1);
  assign g_wd[0] = lane_enc;
  assign g_we[1] = pre_w;
  assign g_wa[1] = pre_wcnt;
  assign g_wd[1] = lane_enc;

  // ------------------------------------------------------------------ round_step_rb
  logic [NE0-1:0][NPOS-1:0][MW-1:0] v2c_o0_st, c2v_prev_o0_st, c2v_o0;
  logic [NE1-1:0][NPOS-1:0][MW-1:0] v2c_o1_st, c2v_cur_late_st, c2v_o1;
  logic [NTYPES-1:0][NPOS-1:0][3:0] g8_cur, g8_prev;
  logic [NTYPES-1:0][NPOS-1:0][MB-1:0] mpost_cur, mpost_prev, cur_bias, prev_bias, cur_marg, prev_marg;
  logic [NTYPES-1:0][NPOS-1:0] cur_hard, prev_hard;
  logic [NTYPES-1:0][NPOS-1:0][DVMAX-1:0][MW-1:0] cur_v2c, prev_v2c;
  logic [NPOS-1:0][NBASE-1:0][MW-1:0] c2v_out;
  logic rs_c2v_valid, rs_out_valid;
  round_step_rb #(.N(N), .NRND(NRND)) u_rs (
    .clk, .rst, .pr_we, .pr_wround, .pr_wtype, .pr_wdata,
    .in_valid(step_valid[0]), .round_idx(PRW'(step_g[0] - win_t)), .init(c_init[0]), .first(c_first[0]),
    .pass(c_pass[0]), .syn(syn_r[IW'(step_g[0] - win_t)]), .cnu_mask(c_cnu_mask[0]), .vmask_cur(c_vmask_cur[0]),
    .vmask_prev(c_vmask_prev[0]), .v2c_o0_st, .v2c_o1_st, .g8_cur, .g8_prev, .mpost_cur, .mpost_prev,
    .c2v_cur_late_st, .c2v_prev_o0_st, .c2v_valid(rs_c2v_valid), .c2v_out, .c2v_o0, .c2v_o1, .cur_bias, .prev_bias,
    .out_valid(rs_out_valid), .cur_marg, .prev_marg, .cur_hard, .prev_hard, .cur_v2c, .prev_v2c);

  // ---- S2: v2c reads, role mux (cur = bank i[0], prev = the other bank)
  vhp_t vhp_cur2, vhp_prev2; vnp_t vnp_cur2;
  assign vhp_cur2  = sp[2].i[0] ? vhp_rd[1] : vhp_rd[0];
  assign vhp_prev2 = sp[2].i[0] ? vhp_rd[0] : vhp_rd[1];
  assign vnp_cur2  = sp[2].i[0] ? vnp_rd[1] : vnp_rd[0];
  for (genvar e = 0; e < NE0; e++) begin : g_r0
    if (e0_hp(e)) begin : g_hp
      assign v2c_o0_st[e] = vhp_cur2.o0[e0_rank(e)];
    end else begin : g_np
      assign v2c_o0_st[e] = vnp_cur2[e0_rank(e)];
    end
  end
  assign v2c_o1_st = vhp_prev2.o1;
  // ---- S3: g8 and M(t-1) reads (M(t-1) = copy ~par)
  g_t g_cur3, g_prev3; mhp_t mhp_cur3, mhp_prev3; mnp_t mnp_cur3;
  logic rc3;                                                         // read copy
  assign rc3 = ~sp[3].par;
  assign g_cur3    = sp[3].i[0] ? g_rd[1] : g_rd[0];
  assign g_prev3   = sp[3].i[0] ? g_rd[0] : g_rd[1];
  assign mhp_cur3  = sp[3].i[0] ? mhp_rd[1][rc3] : mhp_rd[0][rc3];
  assign mhp_prev3 = sp[3].i[0] ? mhp_rd[0][rc3] : mhp_rd[1][rc3];
  assign mnp_cur3  = sp[3].i[0] ? mnp_rd[1][rc3] : mnp_rd[0][rc3];
  logic use_lane3;
  assign use_lane3 = sp[3].init && !sp[3].pass;
  for (genvar t = 0; t < NTYPES; t++) begin : g_r3
    for (genvar p = 0; p < NPOS; p++) begin : g_p
      assign g8_cur[t][p] = sp[3].leg0 ? 4'sd1 : use_lane3 ? lane_g8[t][p] : 4'({1'b0, g_cur3[t][p]} - 4'd2);
      if (HAS_PREV[t]) begin : g_hp
        assign g8_prev[t][p]    = sp[3].leg0 ? 4'sd1 : 4'({1'b0, g_prev3[t][p]} - 4'd2);
        assign mpost_cur[t][p]  = mhp_cur3[hp_idx(t)][p];
        assign mpost_prev[t][p] = mhp_prev3[hp_idx(t)][p];
      end else begin : g_np
        assign g8_prev[t][p]    = '0;
        assign mpost_cur[t][p]  = mnp_cur3[hp_idx(t)][p];
        assign mpost_prev[t][p] = '0;
      end
    end
  end
  // ---- S4: stored c2v reads (late c2v of cur from C1, c2v_o0 of prev from C0)
  c1_t c1_cur4; c0_t c0_prev4;
  assign c1_cur4  = sp[4].i[0] ? c1_rd[1] : c1_rd[0];
  assign c0_prev4 = sp[4].i[0] ? c0_rd[0] : c0_rd[1];
  assign c2v_cur_late_st = c1_cur4;
  for (genvar e = 0; e < NE0; e++) begin : g_r4
    if (e0_hp(e)) begin : g_hp
      assign c2v_prev_o0_st[e] = c0_prev4[e0_rank(e)];
    end else begin : g_np
      assign c2v_prev_o0_st[e] = '0;
    end
  end
  // ---- S5: c2v writes (C0 of cur = CNU output on two-round o0 edges, C1 of prev = CNU output on o1 edges)
  for (genvar e = 0; e < NE0; e++) begin : g_w5
    if (e0_hp(e)) begin : g_hp
      assign c0_wd[e0_rank(e)] = c2v_o0[e];
    end
  end
  assign c1_wd = c2v_o1;
  for (genvar b = 0; b < 2; b++) begin : g_we5
    assign c0_we[b] = sp[5].v && (int'(sp[5].i[0]) == b);
    assign c1_we[b] = sp[5].v && sp[5].pa && (int'(sp[5].i[0]) != b);
  end
  // ---- S6: v2c, marginal and hard-decision writes
  vhp_t vw_cur, vw_prev; vnp_t vw_np; mhp_t mw_cur, mw_prev;
  for (genvar k = 0; k < NBASE; k++) begin : g_w6
    for (genvar p = 0; p < NPOS; p++) begin : g_p
      if (BE_OFF[k] == 0) begin : g_o0
        if (HAS_PREV[BE_TYPE[k]]) begin : g_hp
          assign vw_cur.o0[e0_rank(BE_IDX[k])][p]  = cur_v2c[BE_TYPE[k]][p][BE_SLOT[k]];
          assign vw_prev.o0[e0_rank(BE_IDX[k])][p] = prev_v2c[BE_TYPE[k]][p][BE_SLOT[k]];
        end else begin : g_np
          assign vw_np[e0_rank(BE_IDX[k])][p] = cur_v2c[BE_TYPE[k]][p][BE_SLOT[k]];
        end
      end else begin : g_o1
        assign vw_cur.o1[BE_IDX[k]][p]  = cur_v2c[BE_TYPE[k]][p][BE_SLOT[k]];
        assign vw_prev.o1[BE_IDX[k]][p] = prev_v2c[BE_TYPE[k]][p][BE_SLOT[k]];
      end
    end
  end
  for (genvar t = 0; t < NTYPES; t++) begin : g_mw
    if (HAS_PREV[t]) begin : g_hp
      assign mw_cur[hp_idx(t)] = cur_marg[t]; assign mw_prev[hp_idx(t)] = prev_marg[t];
    end else begin : g_np
      assign mnp_wd[hp_idx(t)] = cur_marg[t];
    end
  end
  assign vnp_wd = vw_np;
  for (genvar b = 0; b < 2; b++) begin : g_we6
    logic is_cur, wv;
    assign is_cur = (int'(sp[6].i[0]) == b);
    assign wv = sp[6].v && (is_cur || sp[6].pa);
    assign vhp_we[b] = wv;
    assign vhp_wd[b] = is_cur ? vw_cur : vw_prev;
    assign vnp_we[b] = sp[6].v && is_cur;
    assign mhp_wd[b] = is_cur ? mw_cur : mw_prev;
    for (genvar c = 0; c < 2; c++) begin : g_c
      assign mhp_we[b][c] = wv && (int'(sp[6].par) == c);
      assign mnp_we[b][c] = sp[6].v && is_cur && (int'(sp[6].par) == c);
    end
  end
  logic [W-1:0][NTYPES-1:0][NPOS-1:0] hard_r [2];                     // bank = iteration parity
  always_ff @(posedge clk) begin
    if (sp[6].v) hard_r[sp[6].par][sp[6].i] <= cur_hard;
    if (sp[6].v && sp[6].pa)
      for (int t = 0; t < NTYPES; t++) if (HAS_PREV[t]) hard_r[sp[6].par][sp[6].i - 1'b1][t] <= prev_hard[t];
  end

  // ------------------------------------------------------------------ convergence check (overlapped)
  localparam int CDLY = 7;                         // conv_req with the last step (S0); its last write is at S6
  logic [CDLY-1:0] creq_d, cpar_d;
  logic cbank;
  always_ff @(posedge clk) begin
    creq_d <= rst ? '0 : {creq_d[CDLY-2:0], conv_req};
    cpar_d <= {cpar_d[CDLY-2:0], conv_par};
    if (creq_d[CDLY-1]) cbank <= cpar_d[CDLY-1];
  end
  logic cbank_now;
  assign cbank_now = creq_d[CDLY-1] ? cpar_d[CDLY-1] : cbank;
  /* verilator lint_off PINCONNECTEMPTY */
  conv_check #(.W(W)) u_conv (
    .clk, .in_valid(creq_d[CDLY-1]), .hard(hard_r[cbank_now]), .syn(syn_r), .emask(emask_r), .out_valid(conv_valid),
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
  logic unused; assign unused = ^{busy, gamma_next, iter_start, rs_c2v_valid, rs_out_valid, cur_bias, prev_bias,
                                  c2v_out, step_valid[3], c_init[3:1], c_first[3:1], c_leg0[3:2], c_pass[3:1],
                                  c_par[3:2], prev_active[3:2], c_cnu_mask[3], c_cnu_mask[1], c_vmask_cur[3:1],
                                  c_vmask_prev[3:1], step_g[3]};
  /* verilator lint_on UNUSEDSIGNAL */

`ifndef SYNTHESIS
  // ------------------------------------------------------------------ hazard assertion (simulation only)
  // Schedule model: at issue (S0) every step registers the cycles at which it will write each memory word
  // (field, bank, address); before that, for every word it reads, the latest write scheduled by an EARLIER step must
  // land before the read (write cycle < read cycle: LUTRAM write in cycle t is visible from t + 1). Every real write
  // port event is checked against the schedule (same cycle), so the model is the RTL's timing.
  // Also write-after-read: no write may be scheduled to land before a read already scheduled (by an earlier step).
  // Fields: 0 VHP, 1 VNP, 2 C0, 3 C1, 4 G, 5/6 MHP copy 0/1, 7/8 MNP copy 0/1.
  longint cyc = 0, haz_reads = 0, haz_viol = 0, wr_checked = 0, wr_unsched = 0, sched_cnt = 0;
  longint sched [9][2][NBK], lastrd [9][2][NBK], war_viol = 0;
  initial for (int f = 0; f < 9; f++) for (int b = 0; b < 2; b++) for (int a = 0; a < NBK; a++) begin
    sched[f][b][a] = -100; lastrd[f][b][a] = -100;
  end
  function automatic void rd_chk(input int f, input int b, input int a, input longint t, input int g, input string nm);
    haz_reads++;
    if (t > lastrd[f][b][a]) lastrd[f][b][a] = t;
    if (sched[f][b][a] >= t) begin
      haz_viol++;
      if (haz_viol <= 10) $display("HAZARD: step g %0d reads %s bank %0d addr %0d at cycle %0d, pending write at %0d",
                                   g, nm, b, a, t, sched[f][b][a]);
    end
  endfunction
  function automatic void wr_sched(input int f, input int b, input int a, input longint t);
    if (t < lastrd[f][b][a]) begin                    // write would land before an earlier-scheduled read
      war_viol++;
      if (war_viol <= 10) $display("HAZARD-WAR: field %0d bank %0d addr %0d write at %0d before read at %0d",
                                   f, b, a, t, lastrd[f][b][a]);
    end
    sched[f][b][a] = t; sched_cnt++;
  endfunction
  function automatic void wr_seen(input int f, input int b, input int a);
    wr_checked++;
    if (sched[f][b][a] != cyc) begin
      wr_unsched++;
      if (wr_unsched <= 10) $display("HAZARD-MODEL: unscheduled write field %0d bank %0d addr %0d at %0d (sched %0d)",
                                     f, b, a, cyc, sched[f][b][a]);
    end
  endfunction
  always @(posedge clk) begin
    if (!rst) begin
      // real writes this cycle
      for (int b = 0; b < 2; b++) begin
        if (vhp_we_x[b]) wr_seen(0, b, int'(va_x[b]));
        if (vnp_we_x[b]) wr_seen(1, b, int'(va_x[b]));
        if (c0_we[b])  wr_seen(2, b, int'(a5[b]));
        if (c1_we[b])  wr_seen(3, b, int'(a5[b]));
        if (g_we[b])   wr_seen(4, b, int'(g_wa[b]));
        for (int c = 0; c < 2; c++) begin
          if (mhp_we[b][c]) wr_seen(5 + c, b, int'(a6[b]));
          if (mnp_we[b][c]) wr_seen(7 + c, b, int'(a6[b]));
        end
      end
      // a new step at S0: reads first (older steps' writes only), then its own writes
      if (sp[0].v) begin
        automatic int i = int'(sp[0].i), g = i, bc = i % 2, bp = 1 - bc, ac = i / 2, ap = (i > 0) ? (i - 1) / 2 : 0;
        automatic int rc = sp[0].par ? 0 : 1, wc = sp[0].par ? 1 : 0;
        rd_chk(0, bc, ac, cyc + 2, g, "VHP cur"); rd_chk(1, bc, ac, cyc + 2, g, "VNP cur");
        rd_chk(5 + rc, bc, ac, cyc + 3, g, "MHP cur"); rd_chk(7 + rc, bc, ac, cyc + 3, g, "MNP cur");
        if (!sp[0].leg0 && !(sp[0].init && !sp[0].pass)) rd_chk(4, bc, ac, cyc + 3, g, "G cur");
        rd_chk(3, bc, ac, cyc + 4, g, "C1 cur");
        if (sp[0].pa) begin
          rd_chk(0, bp, ap, cyc + 2, g, "VHP prev"); rd_chk(5 + rc, bp, ap, cyc + 3, g, "MHP prev");
          if (!sp[0].leg0) rd_chk(4, bp, ap, cyc + 3, g, "G prev");
          rd_chk(2, bp, ap, cyc + 4, g, "C0 prev");
        end
        wr_sched(0, bc, ac, cyc + 6 + V_WB_DLY); wr_sched(1, bc, ac, cyc + 6 + V_WB_DLY);
        wr_sched(5 + wc, bc, ac, cyc + 6); wr_sched(7 + wc, bc, ac, cyc + 6); wr_sched(2, bc, ac, cyc + 5);
        if (sp[0].init && !sp[0].pass && !sp[0].leg0) wr_sched(4, bc, ac, cyc + 3);
        if (sp[0].pa) begin wr_sched(0, bp, ap, cyc + 6 + V_WB_DLY); wr_sched(5 + wc, bp, ap, cyc + 6); wr_sched(3, bp, ap, cyc + 5); end
      end
      // prefill: draw at d (pre_run), write at d + 1
      if (pre_run) wr_sched(4, 1, int'(pre_cnt), cyc + 1);
    end
    cyc <= cyc + 1;
  end
  // engine start with steps in flight would be a hazard of a different kind (state of the previous decode)
  always @(posedge clk) if (!rst && start && (|{sp[1].v, sp[2].v, sp[3].v, sp[4].v, sp[5].v, sp[6].v}))
    $fatal(1, "engine_top_rb: start with steps in flight");
  always @(posedge clk) if (!rst && sp[0].v && win_t != '0) $fatal(1, "engine_top_rb: win_t must be 0 (one window)");
`endif
endmodule
