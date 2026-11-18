// round_step_rb.sv — Test 2f: pipelined round step for the red-black order, one step issued per cycle, no forwarding.
// Same decoder arithmetic as round_step_pf2 (ARITHMETIC.md, int4.2.8); 72 checks of round g, 720 error updates of the
// errors homed g ("cur") + 504 of the two-round types homed g - 1 ("prev"), VNU_PASSES = 1.
//
// Pipeline (stage Sk = k cycles after in_valid; every stage takes a new step every cycle):
//   S0  control in (round, init, first, pass, syn, masks); prior register file read (stage A, registered)
//   S1  prior copies A2 (PF_NA2)
//   S2  prior copies B (NCP = NPOS / PF_PPC); v2c inputs (memory read, combinational) registered
//   S3  init mux (leg start: CNU input = prior) -> wiring -> CNU stage 1: NG cnu.sv per check (min1 / min2 / index /
//       parity of each edge group), registered; M(t-1) and g8 inputs registered (first iteration of a decode:
//       M(t-1) = prior, i.e. M(-1) = L0); prior copies B2
//   S4  CNU stage 2 (cnu_merge_rb), registered = c2v of round g;  bias = vnu_nosat bias (prior, g8, M(t-1)),
//       registered (in parallel with the CNU merge);  stored c2v inputs (memory read, combinational) registered
//   S5  c2v outputs valid (c2v_out, error-side c2v_o0 / c2v_o1); wiring back -> vnu_post_rb (bias + c2v) registered
//   S6  VNU outputs valid (marginals, hard decisions, v2c of both groups)
// Inputs must be given in their stage: S0 control, S2 v2c_o*_st, S3 g8_* / mpost_*, S4 c2v_*_st.
// Leg-start gating from rb_pkg (generated from H and the red-black order): CNU edge k is gated (input = prior) iff
// init && CNU_GATE_P{pass}[k]; VNU slot j of type t is gated (c2v = 0) iff init && VG_{CUR,PREV}_P{pass}[t][j].
// Control is fanned out through NCP registered copies per stage (keep), one per PF_PPC positions.
module round_step_rb
  import round_wiring_pkg::*;
  import rb_pkg::*;
#(
  parameter int N      = 4,
  parameter int NRND   = 13,
  parameter int PF_PPC = 4,
  parameter int PF_NA2 = 6,
  localparam int MB = N + 3,
  localparam int MW = N + 1,
  localparam int RW = $clog2(NRND),
  localparam int TW = $clog2(NTYPES),
  localparam int NCP = NPOS / PF_PPC
) (
  input  logic                                   clk,
  input  logic                                   rst,
  input  logic                                   pr_we,
  input  logic [RW-1:0]                          pr_wround,
  input  logic [TW-1:0]                          pr_wtype,
  input  logic [MW-1:0]                          pr_wdata,
  // S0
  input  logic                                   in_valid,
  input  logic [RW-1:0]                          round_idx,     // prior row of home g (prev group: g - 1)
  input  logic                                   init,
  input  logic                                   first,         // first iteration of the decode: M(t-1) = prior
  input  logic                                   pass,          // 0: even round (first colour), 1: odd round
  input  logic [NPOS-1:0]                        syn,
  input  logic [NBASE-1:0]                       cnu_mask,
  input  logic [NTYPES-1:0][DVMAX-1:0]           vmask_cur,
  input  logic [NTYPES-1:0][DVMAX-1:0]           vmask_prev,
  // S2
  input  logic [NE0-1:0][NPOS-1:0][MW-1:0]       v2c_o0_st,
  input  logic [NE1-1:0][NPOS-1:0][MW-1:0]       v2c_o1_st,
  // S3
  input  logic [NTYPES-1:0][NPOS-1:0][3:0]       g8_cur,
  input  logic [NTYPES-1:0][NPOS-1:0][3:0]       g8_prev,
  input  logic [NTYPES-1:0][NPOS-1:0][MB-1:0]    mpost_cur,
  input  logic [NTYPES-1:0][NPOS-1:0][MB-1:0]    mpost_prev,
  // S4
  input  logic [NE1-1:0][NPOS-1:0][MW-1:0]       c2v_cur_late_st,
  input  logic [NE0-1:0][NPOS-1:0][MW-1:0]       c2v_prev_o0_st,
  // S5
  output logic                                   c2v_valid,
  output logic [NPOS-1:0][NBASE-1:0][MW-1:0]     c2v_out,
  output logic [NE0-1:0][NPOS-1:0][MW-1:0]       c2v_o0,        // error side: errors homed g, offset-0 edges
  output logic [NE1-1:0][NPOS-1:0][MW-1:0]       c2v_o1,        // error side: errors homed g - 1, offset-1 edges
  output logic [NTYPES-1:0][NPOS-1:0][MB-1:0]    cur_bias, prev_bias,
  // S6
  output logic                                   out_valid,
  output logic [NTYPES-1:0][NPOS-1:0][MB-1:0]    cur_marg, prev_marg,
  output logic [NTYPES-1:0][NPOS-1:0]            cur_hard, prev_hard,
  output logic [NTYPES-1:0][NPOS-1:0][DVMAX-1:0][MW-1:0] cur_v2c, prev_v2c
);
  initial begin
    assert (NPOS % PF_PPC == 0 && NCP % PF_NA2 == 0) else $fatal(1, "bad prior copy split");
    assert (NG * GSZ >= NBASE) else $fatal(1, "CNU groups do not cover the base edges");
  end
  localparam int NB_PER_A2 = NCP / PF_NA2;
  localparam int LW = (GSZ > 1) ? $clog2(GSZ) : 1;

  // ---------------------------------------------------------------- control pipeline (single copies)
  logic [6:1] v;
  logic i1, i2, i4, f1, f2, p1, p2, p4;
  logic [NPOS-1:0] syn1, syn2, syn3;
  logic [NBASE-1:0] cm1, cm2;
  logic [NTYPES-1:0][DVMAX-1:0] vc1, vc2, vc3, vc4, vp1, vp2, vp3, vp4;
  logic i3s, p3s;
  always_ff @(posedge clk) begin
    if (rst) v <= '0; else v <= {v[5:1], in_valid};
    i1 <= init; f1 <= first; p1 <= pass; syn1 <= syn; cm1 <= cnu_mask; vc1 <= vmask_cur; vp1 <= vmask_prev;
    i2 <= i1; f2 <= f1; p2 <= p1; syn2 <= syn1; cm2 <= cm1; vc2 <= vc1; vp2 <= vp1;
    i3s <= i2; p3s <= p2; syn3 <= syn2; vc3 <= vc2; vp3 <= vp2;
    i4 <= i3s; p4 <= p3s; vc4 <= vc3; vp4 <= vp3;
  end
  assign c2v_valid = v[5];
  assign out_valid = v[6];

  // ---------------------------------------------------------------- prior register file + fan-out tree A -> A2 -> B -> B2
  logic [NTYPES-1:0][MW-1:0] prf [NRND];
  always_ff @(posedge clk) if (pr_we) prf[pr_wround][pr_wtype] <= pr_wdata;
  function automatic logic [MW-1:0] to_sm(input logic [MW-1:0] x);
    return {x[MW-1], (x[MW-1] ? N'(-x) : N'(x))};
  endfunction
  logic [NTYPES-1:0][MW-1:0] rd_cur, rd_prev, a_cur, a_prev, a_cur_sm, a_prev_sm;
  assign rd_cur  = prf[round_idx];
  assign rd_prev = (round_idx == '0) ? '0 : prf[round_idx - RW'(1)];
  always_ff @(posedge clk) begin
    a_cur <= rd_cur; a_prev <= rd_prev;
    for (int t = 0; t < NTYPES; t++) begin a_cur_sm[t] <= to_sm(rd_cur[t]); a_prev_sm[t] <= to_sm(rd_prev[t]); end
  end
  typedef struct packed {
    logic [NTYPES-1:0][MW-1:0] cur, prev, cur_sm, prev_sm;
  } pri_t;
  pri_t qa2 [PF_NA2];
  for (genvar c = 0; c < PF_NA2; c++) begin : g_a2
    (* keep = "true", max_fanout = 256 *) pri_t a2;
    always_ff @(posedge clk) a2 <= '{cur: a_cur, prev: a_prev, cur_sm: a_cur_sm, prev_sm: a_prev_sm};
    assign qa2[c] = a2;
  end
  pri_t pb [NCP];                              // valid in S3
  logic [NTYPES-1:0][MW-1:0] pb2_cur [NCP], pb2_prev [NCP];   // valid in S4
  // S3 control copies: init-mux select per base edge, first, CNU mask; S4: merge mask; S5: VNU masks and gates
  logic [NBASE-1:0] sel3 [NCP], cm3 [NCP], cm4 [NCP];
  logic f3 [NCP];
  logic [NTYPES-1:0][DVMAX-1:0] vmc5 [NCP], vmp5 [NCP], gc5 [NCP], gp5 [NCP];
  function automatic logic [NBASE-1:0] cnu_sel(input logic ini, input logic ps);
    logic [NBASE-1:0] s;
    for (int k = 0; k < NBASE; k++) s[k] = ini && (ps ? CNU_GATE_P1[k] : CNU_GATE_P0[k]);
    return s;
  endfunction
  function automatic logic [NTYPES-1:0][DVMAX-1:0] vgate(input logic ini, input logic ps, input bit prv);
    logic [NTYPES-1:0][DVMAX-1:0] s;
    for (int t = 0; t < NTYPES; t++)
      for (int j = 0; j < DVMAX; j++)
        s[t][j] = ini && (prv ? (ps ? VG_PREV_P1[t][j] : VG_PREV_P0[t][j]) : (ps ? VG_CUR_P1[t][j] : VG_CUR_P0[t][j]));
    return s;
  endfunction
  for (genvar c = 0; c < NCP; c++) begin : g_cp
    (* keep = "true", max_fanout = 256 *) pri_t b;
    (* keep = "true", max_fanout = 256 *) logic [NTYPES-1:0][MW-1:0] b2_cur, b2_prev;
    (* keep = "true", max_fanout = 256 *) logic [NBASE-1:0] s3, m3, m4;
    (* keep = "true", max_fanout = 256 *) logic ff3;
    (* keep = "true", max_fanout = 256 *) logic [NTYPES-1:0][DVMAX-1:0] mc5, mp5, c5, q5;
    always_ff @(posedge clk) begin
      b <= qa2[c / NB_PER_A2];
      b2_cur <= b.cur; b2_prev <= b.prev;
      s3 <= cnu_sel(i2, p2); m3 <= cm2; ff3 <= f2;
      m4 <= m3;
      mc5 <= vc4; mp5 <= vp4; c5 <= vgate(i4, p4, 1'b0); q5 <= vgate(i4, p4, 1'b1);
    end
    assign pb[c] = b; assign pb2_cur[c] = b2_cur; assign pb2_prev[c] = b2_prev;
    assign sel3[c] = s3; assign cm3[c] = m3; assign cm4[c] = m4; assign f3[c] = ff3;
    assign vmc5[c] = mc5; assign vmp5[c] = mp5; assign gc5[c] = c5; assign gp5[c] = q5;
  end

  // ---------------------------------------------------------------- S2 -> S3: v2c input registers
  logic [NE0-1:0][NPOS-1:0][MW-1:0] r_o0;
  logic [NE1-1:0][NPOS-1:0][MW-1:0] r_o1;
  always_ff @(posedge clk) begin r_o0 <= v2c_o0_st; r_o1 <= v2c_o1_st; end

  // ---------------------------------------------------------------- S3: init mux, wiring, CNU stage 1
  logic [NE0-1:0][NPOS-1:0][MW-1:0] v2c_o0_eff;
  logic [NE1-1:0][NPOS-1:0][MW-1:0] v2c_o1_eff;
  for (genvar k = 0; k < NBASE; k++) begin : g_mux
    for (genvar p = 0; p < NPOS; p++) begin : g_p
      if (BE_OFF[k] == 0) begin : g_o0
        assign v2c_o0_eff[BE_IDX[k]][p] = sel3[p / PF_PPC][k] ? pb[p / PF_PPC].cur_sm[BE_TYPE[k]] : r_o0[BE_IDX[k]][p];
      end else begin : g_o1
        assign v2c_o1_eff[BE_IDX[k]][p] = sel3[p / PF_PPC][k] ? pb[p / PF_PPC].prev_sm[BE_TYPE[k]] : r_o1[BE_IDX[k]][p];
      end
    end
  end
  logic [0:0][NPOS-1:0][NBASE-1:0][MW-1:0] cnu_in, cnu_out;
  logic [0:0][NE0-1:0][NPOS-1:0][MW-1:0]   w_c2v_o0;
  logic [0:0][NE1-1:0][NPOS-1:0][MW-1:0]   w_c2v_o1;
  round_wiring #(.W(MW), .K_ROUNDS(1)) u_wire (
    .v2c_o0(v2c_o0_eff), .v2c_o1(v2c_o1_eff), .cnu_in, .cnu_out, .c2v_o0(w_c2v_o0), .c2v_o1(w_c2v_o1));
  for (genvar x = 0; x < NPOS; x++) begin : g_cnu
    logic [NBASE-1:0] g_os; logic [NG-1:0][N-1:0] g_m1, g_m2; logic [NG-1:0][LW-1:0] g_ix; logic [NG-1:0] g_pr;
    logic [NBASE-1:0] osg; logic [NBASE-1:0][N-1:0] omag;
    for (genvar g = 0; g < NG; g++) begin : g_grp
      localparam int K0 = g * GSZ, D = GSIZE[g];
      localparam int IW = (D > 1) ? $clog2(D) : 1;
      logic [D-1:0] isg, os_g; logic [D-1:0][N-1:0] imag;
      logic [IW-1:0] ix;
      for (genvar e = 0; e < D; e++) begin : g_e
        assign isg[e] = cnu_in[0][x][K0 + e][N];
        assign imag[e] = cnu_in[0][x][K0 + e][N-1:0];
        assign g_os[K0 + e] = os_g[e];
      end
      /* verilator lint_off PINCONNECTEMPTY */
      cnu #(.N(N), .DEG(D), .OUT_REG(1'b1)) u_c (
        .clk, .in_valid(v[3]), .syn((g == 0) ? syn3[x] : 1'b0), .mask(cm3[x / PF_PPC][K0 +: D]),
        .in_sign(isg), .in_mag(imag), .out_valid(), .out_sign(os_g), .out_mag(), .min1(g_m1[g]), .min2(g_m2[g]),
        .min1_idx(ix), .parity(g_pr[g]));
      /* verilator lint_on PINCONNECTEMPTY */
      assign g_ix[g] = LW'(ix);
    end
    // ------------------------------------------------------------ S4: CNU stage 2
    /* verilator lint_off PINCONNECTEMPTY */
    cnu_merge_rb #(.N(N), .DEG(NBASE), .NG(NG), .GSZ(GSZ), .OUT_REG(1'b1)) u_m (
      .clk, .in_valid(v[4]), .mask(cm4[x / PF_PPC]), .g_osign(g_os), .g_min1(g_m1), .g_min2(g_m2), .g_idx(g_ix),
      .g_par(g_pr), .out_valid(), .out_sign(osg), .out_mag(omag));
    /* verilator lint_on PINCONNECTEMPTY */
    for (genvar k = 0; k < NBASE; k++) begin : g_k
      assign cnu_out[0][x][k] = {osg[k], omag[k]};
    end
  end
  assign c2v_out = cnu_out[0];
  assign c2v_o0  = w_c2v_o0[0];
  assign c2v_o1  = w_c2v_o1[0];

  // ---------------------------------------------------------------- S3 -> S4: M(t-1) (with M(-1) = L0) and g8 registers
  logic [NTYPES-1:0][NPOS-1:0][MB-1:0] r_mc, r_mp;
  logic [NTYPES-1:0][NPOS-1:0][3:0]    r_gc, r_gp;
  always_ff @(posedge clk) begin
    r_gc <= g8_cur; r_gp <= g8_prev;
    for (int t = 0; t < NTYPES; t++)
      for (int p = 0; p < NPOS; p++) begin
        r_mc[t][p] <= f3[p / PF_PPC] ? MB'(signed'(pb[p / PF_PPC].cur[t]))  : mpost_cur[t][p];
        r_mp[t][p] <= f3[p / PF_PPC] ? MB'(signed'(pb[p / PF_PPC].prev[t])) : mpost_prev[t][p];
      end
  end
  // S4 -> S5: stored c2v registers
  logic [NE1-1:0][NPOS-1:0][MW-1:0] r_late;
  logic [NE0-1:0][NPOS-1:0][MW-1:0] r_po0;
  always_ff @(posedge clk) begin r_late <= c2v_cur_late_st; r_po0 <= c2v_prev_o0_st; end

  // ---------------------------------------------------------------- VNUs: S4 bias (vnu_nosat), S5 post (vnu_post_rb)
  for (genvar t = 0; t < NTYPES; t++) begin : g_t
    for (genvar p = 0; p < NPOS; p++) begin : g_p
      localparam int CP = p / PF_PPC;
      logic [DVMAX-1:0] cs, ps; logic [DVMAX-1:0][N-1:0] cm, pm;
      for (genvar j = 0; j < DVMAX; j++) begin : g_j
        if (TS_EDGE[t][j] < 0) begin : g_none
          assign {cs[j], cm[j]} = '0; assign {ps[j], pm[j]} = '0;
        end else if (BE_OFF[TS_EDGE[t][j]] == 0) begin : g_o0
          assign {cs[j], cm[j]} = w_c2v_o0[0][BE_IDX[TS_EDGE[t][j]]][p];     // this layer
          assign {ps[j], pm[j]} = r_po0[BE_IDX[TS_EDGE[t][j]]][p];           // round g - 1 (stored)
        end else begin : g_o1
          assign {cs[j], cm[j]} = r_late[BE_IDX[TS_EDGE[t][j]]][p];          // round g + 1 (stored)
          assign {ps[j], pm[j]} = w_c2v_o1[0][BE_IDX[TS_EDGE[t][j]]][p];     // this layer
        end
      end
      // ---- cur group
      logic [MB-1:0] cb; logic [DVMAX-1:0] cvs; logic [DVMAX-1:0][N-1:0] cvm;
      /* verilator lint_off PINCONNECTEMPTY */
      vnu_nosat #(.N(N), .DV(DVMAX), .OUT_REG(1'b1)) u_cb (            // bias only (mask 0: no c2v)
        .clk, .in_valid(v[4]), .init(1'b0), .mask('0), .late('0), .prior(pb2_cur[CP][t]), .g8(r_gc[t][p]),
        .mpost(r_mc[t][p]), .c2v_sign('0), .c2v_mag('0), .out_valid(), .bias(cb), .marg(), .hard(), .v2c_sign(),
        .v2c_mag());
      vnu_post_rb #(.N(N), .DV(DVMAX), .OUT_REG(1'b1)) u_cv (
        .clk, .in_valid(v[5]), .mask(vmc5[CP][t]), .gate(gc5[CP][t]), .bias(cb), .c2v_sign(cs), .c2v_mag(cm),
        .out_valid(), .marg(cur_marg[t][p]), .hard(cur_hard[t][p]), .v2c_sign(cvs), .v2c_mag(cvm));
      /* verilator lint_on PINCONNECTEMPTY */
      assign cur_bias[t][p] = cb;
      for (genvar j = 0; j < DVMAX; j++) begin : g_cv
        assign cur_v2c[t][p][j] = {cvs[j], cvm[j]};
      end
      // ---- prev group (two-round types)
      if (HAS_PREV[t]) begin : g_prev
        logic [MB-1:0] pbias; logic [DVMAX-1:0] pvs; logic [DVMAX-1:0][N-1:0] pvm;
        /* verilator lint_off PINCONNECTEMPTY */
        vnu_nosat #(.N(N), .DV(DVMAX), .OUT_REG(1'b1)) u_pb (
          .clk, .in_valid(v[4]), .init(1'b0), .mask('0), .late('0), .prior(pb2_prev[CP][t]), .g8(r_gp[t][p]),
          .mpost(r_mp[t][p]), .c2v_sign('0), .c2v_mag('0), .out_valid(), .bias(pbias), .marg(), .hard(), .v2c_sign(),
          .v2c_mag());
        vnu_post_rb #(.N(N), .DV(DVMAX), .OUT_REG(1'b1)) u_pv (
          .clk, .in_valid(v[5]), .mask(vmp5[CP][t]), .gate(gp5[CP][t]), .bias(pbias), .c2v_sign(ps), .c2v_mag(pm),
          .out_valid(), .marg(prev_marg[t][p]), .hard(prev_hard[t][p]), .v2c_sign(pvs), .v2c_mag(pvm));
        /* verilator lint_on PINCONNECTEMPTY */
        assign prev_bias[t][p] = pbias;
        for (genvar j = 0; j < DVMAX; j++) begin : g_pv
          assign prev_v2c[t][p][j] = {pvs[j], pvm[j]};
        end
      end else begin : g_noprev
        /* verilator lint_off UNUSEDSIGNAL */
        logic unused_p; assign unused_p = ^{ps, pm, r_gp[t][p], r_mp[t][p], vmp5[CP][t], gp5[CP][t]};
        /* verilator lint_on UNUSEDSIGNAL */
        assign prev_bias[t][p] = '0; assign prev_marg[t][p] = '0; assign prev_hard[t][p] = 1'b0;
        assign prev_v2c[t][p] = '0;
      end
    end
  end
  /* verilator lint_off UNUSEDSIGNAL */
  logic unused; assign unused = ^{v[2:1], i3s, p3s};
  /* verilator lint_on UNUSEDSIGNAL */
endmodule
