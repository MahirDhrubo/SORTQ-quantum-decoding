// round_step_pf.sv — Test 2c timing variant of round_step.sv (same arithmetic, same step timing; only the prior
// read path changes). Test 2c found the critical path of round_step / engine_top in the prior register-file read
// (round_idx -> 13:1 read -> broadcast to 72 positions) in front of the CNU init mux and the VNU bias.
//
// Prefetch (the round order is static, so the round of the NEXT step is known one step ahead):
//   stage A  : on nxt_valid, the priors of round nxt_round_idx (cur) and nxt_round_idx - 1 (prev) are read from the
//              register file and registered, in two's complement (VNUs) and sign-magnitude (CNU init mux; the
//              conversion moves from the init mux into stage A).
//   stage B  : NCP = NPOS / PF_PPC duplicated copies (keep, max_fanout 256), copy c feeds positions
//              c*PF_PPC .. c*PF_PPC + PF_PPC - 1 (fan-out tree A -> B -> consumers). B <= A on `adv` = a cycle in
//              which the step in flight no longer reads B: not the start cycle (CNU) and, VNU_PASSES = 2, not
//              pass A (s_cnu); i.e. the step's last cycle, or any idle cycle.
// Contract (replaces round_idx): nxt_valid / nxt_round_idx for step n + 1 are given in the start cycle of step n
// (for the first step: any time before it, while idle). in_ready is also low until A has moved into B, so a step
// never starts on stale priors. With steps back to back this adds no cycle: step = VNU_PASSES + 1 cycles.
// Everything else is unchanged from round_step.sv (original header below).
//
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
// port (pr_we, pr_wround, pr_wtype, pr_wdata) before decoding. round_step_pf: read one step ahead (nxt_round_idx;
// cur = home r, prev = home r - 1) into stage A, then duplicated stage-B registers feed the CNU init mux and the VNUs.
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
// prefetched priors) must be held from the start until out_valid. c2v_out is valid from the cycle after the start until
// out_valid. cur_* are valid while cur_valid, prev_* while prev_valid (VNU_PASSES = 2: cur results one cycle before
// prev results, from the same VNU registers; VNU_PASSES = 1: both together). out_valid = last results of the step.
module round_step_pf
  import round_wiring_pkg::*;
#(
  parameter int N          = 4,
  parameter int VNU_PASSES = 1,       // 1: 1,224 VNUs, 2 cycles per step; 2: 720 VNUs, 3 cycles per step
  parameter int NRND       = 13,      // home rounds held in the prior register file (12-round circuit: 0..12)
  parameter int PF_PPC     = 4,       // positions per prior copy (stage B): NPOS / PF_PPC copies
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
  input  logic                                   nxt_valid,       // prefetch: round of the next step
  input  logic [RW-1:0]                          nxt_round_idx,
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
  logic a_new;                       // stage A holds priors not yet moved into B
  assign in_ready = !(s_cnu || s_b) && !a_new;
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

  // ---------------------------------------------------------------- prior register file
  logic [NTYPES-1:0][MW-1:0] prf [NRND];
  always_ff @(posedge clk) if (pr_we) prf[pr_wround][pr_wtype] <= pr_wdata;

  // ---------------------------------------------------------------- prefetch stage A (registered read)
  function automatic logic [MW-1:0] to_sm(input logic [MW-1:0] x);    // two's complement -> {sign, magnitude}
    return {x[MW-1], (x[MW-1] ? N'(-x) : N'(x))};
  endfunction
  function automatic bit any_o1_init();
    for (int k = 0; k < NBASE; k++) if (BE_OFF[k] != 0 && INIT_CNU_PRIOR[k]) return 1'b1;
    return 1'b0;
  endfunction
  localparam bit O1_INIT = any_o1_init();     // 0 for the gross code: prev priors only feed the VNUs
  localparam int NCP = NPOS / PF_PPC;
  initial assert (NPOS % PF_PPC == 0) else $fatal(1, "PF_PPC must divide NPOS");
  logic adv;
  assign adv = a_new && !start && !((VNU_PASSES == 2) && s_cnu);
  logic [NTYPES-1:0][MW-1:0] rd_cur, rd_prev, a_cur, a_prev, a_cur_sm, a_prev_sm;
  assign rd_cur  = prf[nxt_round_idx];
  assign rd_prev = (nxt_round_idx == '0) ? '0 : prf[nxt_round_idx - RW'(1)];
  always_ff @(posedge clk) begin
    if (rst) a_new <= 1'b0;
    else if (nxt_valid) a_new <= 1'b1;
    else if (adv) a_new <= 1'b0;
    if (nxt_valid) begin
      a_cur <= rd_cur; a_prev <= rd_prev;
      for (int t = 0; t < NTYPES; t++) begin a_cur_sm[t] <= to_sm(rd_cur[t]); a_prev_sm[t] <= to_sm(rd_prev[t]); end
    end
  end

  // ---------------------------------------------------------------- stage B: duplicated copies (fan-out tree)
  logic [NTYPES-1:0][MW-1:0] pc_cur [NCP], pc_prev [NCP], pc_cur_sm [NCP], pc_prev_sm [NCP];
  for (genvar c = 0; c < NCP; c++) begin : g_cp
    (* keep = "true", max_fanout = 256 *) logic [NTYPES-1:0][MW-1:0] b_cur;
    (* keep = "true", max_fanout = 256 *) logic [NTYPES-1:0][MW-1:0] b_prev;
    (* keep = "true", max_fanout = 256 *) logic [NTYPES-1:0][MW-1:0] b_cur_sm;
    always_ff @(posedge clk) if (adv) begin b_cur <= a_cur; b_prev <= a_prev; b_cur_sm <= a_cur_sm; end
    assign pc_cur[c] = b_cur; assign pc_prev[c] = b_prev; assign pc_cur_sm[c] = b_cur_sm;
    if (O1_INIT) begin : g_psm
      (* keep = "true", max_fanout = 256 *) logic [NTYPES-1:0][MW-1:0] b_prev_sm;
      always_ff @(posedge clk) if (adv) b_prev_sm <= a_prev_sm;
      assign pc_prev_sm[c] = b_prev_sm;
    end else begin : g_npsm
      assign pc_prev_sm[c] = '0;
    end
  end
  /* verilator lint_off UNUSEDSIGNAL */
  logic unused_pf; assign unused_pf = ^{a_prev_sm, pc_prev_sm[0]};
  /* verilator lint_on UNUSEDSIGNAL */

  // ---------------------------------------------------------------- init mux (INIT_CNU_PRIOR edges take the prior)
  logic [NE0-1:0][NPOS-1:0][MW-1:0] v2c_o0_eff;
  logic [NE1-1:0][NPOS-1:0][MW-1:0] v2c_o1_eff;
  for (genvar k = 0; k < NBASE; k++) begin : g_mux
    for (genvar p = 0; p < NPOS; p++) begin : g_p
      if (BE_OFF[k] == 0) begin : g_o0
        if (INIT_CNU_PRIOR[k]) begin : g_pr
          assign v2c_o0_eff[BE_IDX[k]][p] = init ? pc_cur_sm[p / PF_PPC][BE_TYPE[k]] : v2c_o0_st[BE_IDX[k]][p];
        end else begin : g_st
          assign v2c_o0_eff[BE_IDX[k]][p] = v2c_o0_st[BE_IDX[k]][p];
        end
      end else begin : g_o1
        if (INIT_CNU_PRIOR[k]) begin : g_pr      // not reached for the gross code (offset-1 inputs are fresh)
          assign v2c_o1_eff[BE_IDX[k]][p] = init ? pc_prev_sm[p / PF_PPC][BE_TYPE[k]] : v2c_o1_st[BE_IDX[k]][p];
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
          .prior(pc_cur[p / PF_PPC][t]), .g8(g8_cur[t][p]), .mpost(mpost_cur[t][p]), .c2v_sign(cs), .c2v_mag(cm),
          .out_valid(), .bias(u_bias), .marg(u_marg), .hard(u_hard), .v2c_sign(u_vs), .v2c_mag(u_vm));
        /* verilator lint_on PINCONNECTEMPTY */
        assign cur_bias[t][p] = u_bias; assign cur_marg[t][p] = u_marg; assign cur_hard[t][p] = u_hard;
        assign cur_v2c[t][p] = u_v2c;
        if (VNU_PASSES == 1 && HAS_PREV[t]) begin : g_prev_unit
          logic [DVMAX-1:0] qs; logic [DVMAX-1:0][N-1:0] qm;
          /* verilator lint_off PINCONNECTEMPTY */
          vnu #(.N(N), .DV(DVMAX), .OUT_REG(1'b1)) u_prev (
            .clk, .in_valid(s_cnu), .init, .mask(vmask_prev[t]), .late(plate),
            .prior(pc_prev[p / PF_PPC][t]), .g8(g8_prev[t][p]), .mpost(mpost_prev[t][p]), .c2v_sign(ps), .c2v_mag(pm),
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
          .prior(sel ? pc_prev[p / PF_PPC][t] : pc_cur[p / PF_PPC][t]), .g8(sel ? g8_prev[t][p] : g8_cur[t][p]),
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
