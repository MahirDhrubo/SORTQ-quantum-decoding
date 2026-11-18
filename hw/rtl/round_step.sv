// round_step.sv — one round step of the round sweep (layer = check round r), K_ROUNDS = 1:
//   prior register file -> init mux -> round_wiring -> 72 CNUs (35 base edges) -> round_wiring (back) -> error-node
//   updates of the layer: 720 errors homed r (all 10 types, "cur") + 504 errors homed r - 1 (the 7 types with an
//   offset-1 edge, HAS_PREV, "prev") — ARITHMETIC.md section 4.
//
// VNU_PASSES = 1: 1,224 VNUs (720 cur + 504 prev), both groups in one cycle.   Step = 2 cycles (CNU, VNU).
// VNU_PASSES = 2: 720 VNUs (one per (type, position)), time-shared: pass A = cur group, pass B = prev group (the
//                 HAS_PREV units take the prev inputs through a 2:1 input mux).               Step = 3 cycles.
// Both orders are exact: the cur and prev groups of one layer are different errors and read only this layer's
// CNU outputs and stored values, never each other's results.
//
// Priors: register file of NRND home rounds x NTYPES entries (N + 1 bits, two's complement), written through the load
// port (pr_we, pr_wround, pr_wtype, pr_wdata) before decoding. Read with round_idx (cur = home r, prev = home r - 1),
// broadcast to the 72 positions, into the CNU init mux and the VNUs. The read is combinational, in the same cycle as
// the CNU (the path measured by Test 2c).
// Leg-start (init) gating comes only from compile-time constants of round_wiring_pkg, generated from the round
// offsets: INIT_CNU_PRIOR (CNU input = prior), INIT_ZERO_CUR / INIT_ZERO_PREV (VNU c2v slot = 0), HAS_PREV.
//
// Message ports in sign-magnitude {sign, mag[N-1:0]}; priors / marginals / bias two's complement.
// Inputs are the hardware memory contents (no clearing at a leg start):
//   v2c_o0_st [k0][p]        stored v2c of errors homed r, offset-0 slot k0 (edge to round r)
//   v2c_o1_st [k1][p]        stored v2c of errors homed r - 1, offset-1 slot k1 (edge to round r)
//   c2v_cur_late_st [k1][p]  stored c2v of errors homed r on offset-1 slots (from round r + 1)
//   c2v_prev_o0_st [k0][p]   stored c2v of errors homed r - 1 on offset-0 slots (from round r - 1)
// Masks (from ctrl): cnu_mask[k]; vmask_cur / vmask_prev [type][slot].
// Handshake: a step starts on in_valid && in_ready (in_ready = not busy). All step inputs (including init and
// round_idx) must be held from the start until out_valid. c2v_out is valid from the cycle after the start until
// out_valid. cur_* are valid while cur_valid, prev_* while prev_valid (VNU_PASSES = 2: cur results one cycle before
// prev results, from the same VNU registers; VNU_PASSES = 1: both together). out_valid = last results of the step.
module round_step
  import round_wiring_pkg::*;
#(
  parameter int N          = 4,
  parameter int VNU_PASSES = 1,       // 1: 1,224 VNUs, 2 cycles per step; 2: 720 VNUs, 3 cycles per step
  parameter int NRND       = 13,      // home rounds held in the prior register file (12-round circuit: 0..12)
  localparam int MB = N + 3,
  localparam int MW = N + 1,          // message word: {sign, magnitude}; prior word: two's complement
  localparam int RW = $clog2(NRND),
  localparam int TW = $clog2(NTYPES)
) (
  input  logic                                   clk,
  input  logic                                   rst,
  // prior load port
  input  logic                                   pr_we,
  input  logic [RW-1:0]                          pr_wround,
  input  logic [TW-1:0]                          pr_wtype,
  input  logic [MW-1:0]                          pr_wdata,
  // step
  input  logic                                   in_valid,
  output logic                                   in_ready,
  input  logic                                   init,
  input  logic [RW-1:0]                          round_idx,
  input  logic [NPOS-1:0]                        syn,
  input  logic [NBASE-1:0]                       cnu_mask,
  input  logic [NE0-1:0][NPOS-1:0][MW-1:0]       v2c_o0_st,
  input  logic [NE1-1:0][NPOS-1:0][MW-1:0]       v2c_o1_st,
  input  logic [NTYPES-1:0][NPOS-1:0][3:0]       g8_cur,
  input  logic [NTYPES-1:0][NPOS-1:0][MB-1:0]    mpost_cur,
  input  logic [NE1-1:0][NPOS-1:0][MW-1:0]       c2v_cur_late_st,
  input  logic [NTYPES-1:0][DVMAX-1:0]           vmask_cur,
  input  logic [NTYPES-1:0][NPOS-1:0][3:0]       g8_prev,
  input  logic [NTYPES-1:0][NPOS-1:0][MB-1:0]    mpost_prev,
  input  logic [NE0-1:0][NPOS-1:0][MW-1:0]       c2v_prev_o0_st,
  input  logic [NTYPES-1:0][DVMAX-1:0]           vmask_prev,
  output logic                                   cur_valid,
  output logic                                   prev_valid,
  output logic                                   out_valid,
  output logic [NPOS-1:0][NBASE-1:0][MW-1:0]     c2v_out,
  output logic [NTYPES-1:0][NPOS-1:0][MB-1:0]    cur_bias, cur_marg, prev_bias, prev_marg,
  output logic [NTYPES-1:0][NPOS-1:0]            cur_hard, prev_hard,
  output logic [NTYPES-1:0][NPOS-1:0][DVMAX-1:0][MW-1:0] cur_v2c, prev_v2c
);
  initial assert (VNU_PASSES == 1 || VNU_PASSES == 2) else $fatal(1, "VNU_PASSES must be 1 or 2");

  // ---------------------------------------------------------------- step sequencing
  logic start, s_cnu, s_b;           // s_cnu: CNU registers hold this step (VNU pass A runs); s_b: pass B runs
  logic v_a, v_b;                    // VNU results of pass A / pass B registered
  assign in_ready = !(s_cnu || s_b);
  assign start    = in_valid && in_ready;
  always_ff @(posedge clk) begin
    if (rst) begin
      s_cnu <= 1'b0; s_b <= 1'b0; v_a <= 1'b0; v_b <= 1'b0;
    end else begin
      s_cnu <= start;
      s_b   <= (VNU_PASSES == 2) && s_cnu;
      v_a   <= s_cnu;
      v_b   <= s_b;
    end
  end
  assign cur_valid  = v_a;
  assign prev_valid = (VNU_PASSES == 2) ? v_b : v_a;
  assign out_valid  = prev_valid;

  // ---------------------------------------------------------------- prior register file (broadcast read)
  logic [NTYPES-1:0][MW-1:0] prf [NRND];
  always_ff @(posedge clk) if (pr_we) prf[pr_wround][pr_wtype] <= pr_wdata;
  logic [NTYPES-1:0][MW-1:0] prior_cur_t, prior_prev_t;
  assign prior_cur_t  = prf[round_idx];
  assign prior_prev_t = (round_idx == '0) ? '0 : prf[round_idx - RW'(1)];

  // ---------------------------------------------------------------- init mux (INIT_CNU_PRIOR edges take the prior)
  logic [NE0-1:0][NPOS-1:0][MW-1:0] v2c_o0_eff;
  logic [NE1-1:0][NPOS-1:0][MW-1:0] v2c_o1_eff;
  for (genvar k = 0; k < NBASE; k++) begin : g_mux
    for (genvar p = 0; p < NPOS; p++) begin : g_p
      if (BE_OFF[k] == 0) begin : g_o0
        if (INIT_CNU_PRIOR[k]) begin : g_pr
          logic signed [MW-1:0] pr;
          assign pr = prior_cur_t[BE_TYPE[k]];
          assign v2c_o0_eff[BE_IDX[k]][p] = init ? {pr[MW-1], (pr[MW-1] ? N'(-pr) : N'(pr))} : v2c_o0_st[BE_IDX[k]][p];
        end else begin : g_st
          assign v2c_o0_eff[BE_IDX[k]][p] = v2c_o0_st[BE_IDX[k]][p];
        end
      end else begin : g_o1
        if (INIT_CNU_PRIOR[k]) begin : g_pr      // not reached for the gross code (offset-1 inputs are fresh)
          logic signed [MW-1:0] pr;
          assign pr = prior_prev_t[BE_TYPE[k]];
          assign v2c_o1_eff[BE_IDX[k]][p] = init ? {pr[MW-1], (pr[MW-1] ? N'(-pr) : N'(pr))} : v2c_o1_st[BE_IDX[k]][p];
        end else begin : g_st
          assign v2c_o1_eff[BE_IDX[k]][p] = v2c_o1_st[BE_IDX[k]][p];
        end
      end
    end
  end

  // ---------------------------------------------------------------- wiring + CNUs
  logic [0:0][NPOS-1:0][NBASE-1:0][MW-1:0] cnu_in, cnu_out;
  logic [0:0][NE0-1:0][NPOS-1:0][MW-1:0]   c2v_o0;
  logic [0:0][NE1-1:0][NPOS-1:0][MW-1:0]   c2v_o1;
  round_wiring #(.W(MW), .K_ROUNDS(1)) u_wire (
    .v2c_o0(v2c_o0_eff), .v2c_o1(v2c_o1_eff), .cnu_in, .cnu_out, .c2v_o0, .c2v_o1);
  for (genvar x = 0; x < NPOS; x++) begin : g_cnu
    logic [NBASE-1:0] isg, osg;
    logic [NBASE-1:0][N-1:0] imag, omag;
    for (genvar k = 0; k < NBASE; k++) begin : g_k
      assign isg[k] = cnu_in[0][x][k][N];
      assign imag[k] = cnu_in[0][x][k][N-1:0];
      assign cnu_out[0][x][k] = {osg[k], omag[k]};
    end
    /* verilator lint_off PINCONNECTEMPTY */
    cnu #(.N(N), .DEG(NBASE), .OUT_REG(1'b1)) u_cnu (
      .clk, .in_valid(start), .syn(syn[x]), .mask(cnu_mask), .in_sign(isg), .in_mag(imag),
      .out_valid(), .out_sign(osg), .out_mag(omag), .min1(), .min2(), .min1_idx(), .parity());
    /* verilator lint_on PINCONNECTEMPTY */
  end
  assign c2v_out = cnu_out[0];

  // ---------------------------------------------------------------- VNUs
  for (genvar t = 0; t < NTYPES; t++) begin : g_t
    for (genvar p = 0; p < NPOS; p++) begin : g_p
      // ---- input bundle of the error homed r (group cur)
      logic [DVMAX-1:0] cs, clate; logic [DVMAX-1:0][N-1:0] cm;
      // ---- input bundle of the error homed r - 1 (group prev)
      logic [DVMAX-1:0] ps, plate; logic [DVMAX-1:0][N-1:0] pm;
      for (genvar j = 0; j < DVMAX; j++) begin : g_j
        assign clate[j] = INIT_ZERO_CUR[t][j];
        assign plate[j] = INIT_ZERO_PREV[t][j];
        if (TS_EDGE[t][j] < 0) begin : g_none
          assign {cs[j], cm[j]} = '0; assign {ps[j], pm[j]} = '0;
        end else if (BE_OFF[TS_EDGE[t][j]] == 0) begin : g_o0
          assign {cs[j], cm[j]} = c2v_o0[0][BE_IDX[TS_EDGE[t][j]]][p];        // this layer
          assign {ps[j], pm[j]} = c2v_prev_o0_st[BE_IDX[TS_EDGE[t][j]]][p];   // layer r - 1 (stored)
        end else begin : g_o1
          assign {cs[j], cm[j]} = c2v_cur_late_st[BE_IDX[TS_EDGE[t][j]]][p];  // layer r + 1 (stored)
          assign {ps[j], pm[j]} = c2v_o1[0][BE_IDX[TS_EDGE[t][j]]][p];        // this layer
        end
      end
      // ---- unit outputs
      logic [MB-1:0] u_bias, u_marg; logic u_hard;
      logic [DVMAX-1:0] u_vs; logic [DVMAX-1:0][N-1:0] u_vm;
      logic [DVMAX-1:0][MW-1:0] u_v2c;
      for (genvar j = 0; j < DVMAX; j++) begin : g_o
        assign u_v2c[j] = {u_vs[j], u_vm[j]};
      end

      if (VNU_PASSES == 1 || !HAS_PREV[t]) begin : g_cur_unit
        // dedicated unit for the cur group (VNU_PASSES = 2: types without a prev group are not time-shared)
        /* verilator lint_off PINCONNECTEMPTY */
        vnu #(.N(N), .DV(DVMAX), .OUT_REG(1'b1)) u_cur (
          .clk, .in_valid(s_cnu), .init, .mask(vmask_cur[t]), .late(clate),
          .prior(prior_cur_t[t]), .g8(g8_cur[t][p]), .mpost(mpost_cur[t][p]), .c2v_sign(cs), .c2v_mag(cm),
          .out_valid(), .bias(u_bias), .marg(u_marg), .hard(u_hard), .v2c_sign(u_vs), .v2c_mag(u_vm));
        /* verilator lint_on PINCONNECTEMPTY */
        assign cur_bias[t][p] = u_bias; assign cur_marg[t][p] = u_marg; assign cur_hard[t][p] = u_hard;
        assign cur_v2c[t][p] = u_v2c;
        if (VNU_PASSES == 1 && HAS_PREV[t]) begin : g_prev_unit
          logic [DVMAX-1:0] qs; logic [DVMAX-1:0][N-1:0] qm;
          /* verilator lint_off PINCONNECTEMPTY */
          vnu #(.N(N), .DV(DVMAX), .OUT_REG(1'b1)) u_prev (
            .clk, .in_valid(s_cnu), .init, .mask(vmask_prev[t]), .late(plate),
            .prior(prior_prev_t[t]), .g8(g8_prev[t][p]), .mpost(mpost_prev[t][p]), .c2v_sign(ps), .c2v_mag(pm),
            .out_valid(), .bias(prev_bias[t][p]), .marg(prev_marg[t][p]), .hard(prev_hard[t][p]),
            .v2c_sign(qs), .v2c_mag(qm));
          /* verilator lint_on PINCONNECTEMPTY */
          for (genvar j = 0; j < DVMAX; j++) begin : g_q
            assign prev_v2c[t][p][j] = {qs[j], qm[j]};
          end
        end else begin : g_no_prev
          /* verilator lint_off UNUSEDSIGNAL */
          logic [DVMAX-1:0] unused_p; assign unused_p = ps ^ plate ^ {DVMAX{^pm}};
          /* verilator lint_on UNUSEDSIGNAL */
          assign prev_bias[t][p] = '0; assign prev_marg[t][p] = '0; assign prev_hard[t][p] = 1'b0;
          assign prev_v2c[t][p] = '0;
        end
      end else begin : g_shared_unit
        // VNU_PASSES = 2, HAS_PREV type: one unit, pass A (s_cnu) = cur inputs, pass B (s_b) = prev inputs
        logic sel;
        assign sel = s_b;
        logic [DVMAX-1:0] m_s, m_late, m_mask; logic [DVMAX-1:0][N-1:0] m_m;
        assign m_s    = sel ? ps : cs;
        assign m_m    = sel ? pm : cm;
        assign m_late = sel ? plate : clate;
        assign m_mask = sel ? vmask_prev[t] : vmask_cur[t];
        /* verilator lint_off PINCONNECTEMPTY */
        vnu #(.N(N), .DV(DVMAX), .OUT_REG(1'b1)) u_shared (
          .clk, .in_valid(s_cnu || s_b), .init, .mask(m_mask), .late(m_late),
          .prior(sel ? prior_prev_t[t] : prior_cur_t[t]), .g8(sel ? g8_prev[t][p] : g8_cur[t][p]),
          .mpost(sel ? mpost_prev[t][p] : mpost_cur[t][p]), .c2v_sign(m_s), .c2v_mag(m_m),
          .out_valid(), .bias(u_bias), .marg(u_marg), .hard(u_hard), .v2c_sign(u_vs), .v2c_mag(u_vm));
        /* verilator lint_on PINCONNECTEMPTY */
        // same registers drive both groups: cur_* are read at cur_valid, prev_* at prev_valid
        assign cur_bias[t][p]  = u_bias; assign cur_marg[t][p]  = u_marg; assign cur_hard[t][p]  = u_hard;
        assign cur_v2c[t][p]   = u_v2c;
        assign prev_bias[t][p] = u_bias; assign prev_marg[t][p] = u_marg; assign prev_hard[t][p] = u_hard;
        assign prev_v2c[t][p]  = u_v2c;
      end
    end
  end
endmodule
