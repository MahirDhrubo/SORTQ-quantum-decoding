// tb_engine_3d.sv — Test 3d (reduced): closed-loop simulation of engine_top_pf2 (VNU_PASSES 1, LUTRAM model),
// complete shots decoded end to end by the engine (ctrl_pf -> memories -> round_step_pf2 -> conv_check -> commit).
// Problem: W = 13 rounds, win_t = 0, last_r = 12: one window = the whole 12-round circuit (= Test 1b X decoder);
// commit over C = 13 rounds. Gamma lanes in LOAD mode: whenever ctrl issues an init step (first iteration of a
// leg) for round g, the lanes are loaded with the software g8 of the errors of home round g in the current leg.
// Decode-start state that engine_top_pf2 has no hardware path for (Test 3d finding, see summary): the marginal
// memory M(-1) = L0 of leg 0 is written into both marginal banks by the testbench (backdoor) before `start`.
// Per shot (+LIST=<file of shot files>): reset, prior file (load port), syndromes (arrival port), M(-1), start; then
// compare iter_total, success, all hard decisions (bank of the last checked iteration) and the 12 observables
// (commit) with the software decoder; and measure cycles per iteration (iter_start to iter_start), leg starts
// separately.
`timescale 1ns/1ps
module tb_engine_3d;
  import round_wiring_pkg::*;
  import engine_tables_pkg::*;
  localparam int N = 4, MB = N + 3, MW = N + 1, W = 13, C = 13, NRND = 13, RW = 8, LEGMAX = 10;
  localparam int IW = $clog2(W), PRW = $clog2(NRND), TW = $clog2(NTYPES);
  localparam int NV = NTYPES * NPOS;
  logic clk = 0, rst = 1, start = 0, arr_valid = 0, pr_we = 0;
  logic [RW-1:0] win_t = '0, last_r = 8'd12;
  logic [IW-1:0] arr_idx = '0; logic [NPOS-1:0] arr_data = '0;
  logic [PRW-1:0] pr_wround = '0; logic [TW-1:0] pr_wtype = '0; logic [MW-1:0] pr_wdata = '0;
  logic g8_ld; logic [NTYPES-1:0][NPOS-1:0][3:0] g8_ld_data;
  logic done, success, obs_valid, syn_corr_valid; logic [15:0] iter_total; logic [NOBS-1:0] obs;
  logic [NPOS-1:0] syn_corr;
  always #5 clk = ~clk;

  engine_top_pf2_sim #(.N(N), .VNU_PASSES(1), .STORAGE("LUTRAM"), .W(W), .C(C), .NRND(NRND), .RW(RW)) dut (.*);

  // shot data
  int e_it, e_succ, nlegs; logic [NOBS-1:0] e_obs;
  int ptab [NRND][NTYPES];
  logic [NPOS-1:0] syn [NRND];
  logic [NV-1:0] e_hard [NRND], e_mask [NRND];
  logic [NV*4-1:0] g8tab [LEGMAX][NRND];

  // gamma LOAD: at an init step of round g, load the current leg's g8 of home round g
  assign g8_ld = dut.step_valid[0] & dut.c_init[0];
  assign g8_ld_data = g8tab[(int'(dut.leg) < LEGMAX) ? int'(dut.leg) : 0][dut.step_g[0][3:0]];
  int bad_leg = 0;
  always @(posedge clk) if (!rst && g8_ld && int'(dut.leg) >= nlegs) bad_leg++;

  function automatic int hp_rank(int t, bit hp);   // rank of t among types with HAS_PREV == hp
    int n = 0; for (int u = 0; u < t; u++) if (HAS_PREV[u] == hp) n++; return n;
  endfunction

  // cycle accounting: iteration length = iter_start to the next iter_start. An iteration whose successor starts a
  // relay leg (init) is a "leg-end" iteration: its check is not overlapped (ctrl_pf waits), so the wait lands there.
  longint cyc = 0; int last_is = -1, last_delta = -1;
  int d_norm_sum = 0, d_norm_n = 0, d_end_sum = 0, d_end_n = 0, first_is = -1, done_cyc = -1, obs_cyc = -1;
  bit pend_is;
  always @(posedge clk) begin
    cyc <= cyc + 1;
    if (!rst && !done) begin
      if (dut.iter_start) begin
        if (last_is >= 0) last_delta = int'(cyc) - last_is; else first_is = int'(cyc);
        last_is = int'(cyc); pend_is = 1;
      end
      if (pend_is && dut.step_valid[0]) begin
        pend_is = 0;
        if (last_delta >= 0) begin
          if (dut.c_init[0]) begin d_end_sum += last_delta; d_end_n++; end
          else begin d_norm_sum += last_delta; d_norm_n++; end
        end
      end
    end
  end

  // ---------------------------------------------------------------- +VEC debug: live round_step inputs vs the
  // Test 2a golden step vectors (same shot, same step order); compared in the step's second cycle (inputs held).
  string VEC; int vf = 0, vstep = 0, vbad_steps = 0, vmax = 1 << 30;
  int vg, vini; logic [NPOS-1:0] v_syn; logic [NBASE-1:0] v_cm;
  logic [NE0-1:0][NPOS-1:0][MW-1:0] v_v2c_o0, v_c2v_prev_o0, x_e0;
  logic [NE1-1:0][NPOS-1:0][MW-1:0] v_v2c_o1, v_c2v_late, x_e1;
  logic [NTYPES-1:0][NPOS-1:0][MW-1:0] v_pc, v_pp;
  logic [NTYPES-1:0][NPOS-1:0][3:0] v_g8c, v_g8p;
  logic [NTYPES-1:0][NPOS-1:0][MB-1:0] v_mc, v_mp, x_b1, x_b2, x_b3, x_b4;
  logic [NTYPES-1:0][DVMAX-1:0] v_vc, v_vp;
  logic [NPOS-1:0][NBASE-1:0][MW-1:0] v_ec2v;
  logic [NTYPES-1:0][NPOS-1:0] v_cmpc, v_cmpp, x_h1, x_h2;
  logic [NTYPES-1:0][NPOS-1:0][DVMAX-1:0][MW-1:0] x_v1, x_v2;
  function automatic bit sm_eq(input logic [MW-1:0] a, input logic [MW-1:0] b);   // -0 == +0
    return (a[MW-2:0] == b[MW-2:0]) && (a[MW-2:0] == '0 || a[MW-1] == b[MW-1]);
  endfunction
  always @(posedge clk) if (vf != 0 && !rst && dut.rs_start && vstep < vmax) begin
    if ($fscanf(vf, "%d %d %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h",
                vg, vini, v_syn, v_cm, v_v2c_o0, v_v2c_o1, v_pc, v_g8c, v_mc, v_c2v_late, v_vc, v_pp, v_g8p, v_mp,
                v_c2v_prev_o0, v_vp, v_ec2v, x_b1, x_b2, x_h1, x_v1, x_b3, x_b4, x_h2, x_v2, v_cmpc, v_cmpp) == 27) begin
      #1;   // second cycle of the step (C1): all step inputs held
      begin
        automatic int nb = 0;
        automatic int d_syn = 0, d_cm = 0, d_ini = 0, d_g = 0, d_o0 = 0, d_o1 = 0, d_g8c = 0, d_mc = 0, d_late = 0,
                      d_g8p = 0, d_mp = 0, d_po0 = 0, d_vc = 0, d_vp = 0, d_c2v = 0;
        if (int'(dut.rs_g) != vg) d_g++;
        if (dut.rs_init !== vini[0]) d_ini++;
        if (dut.rs_syn !== v_syn) d_syn++;
        if (dut.rs_cnu_mask !== v_cm) d_cm++;
        if (dut.rs_vmc !== v_vc) d_vc++;
        if (dut.rs_vmp !== v_vp) d_vp++;
        for (int k = 0; k < NBASE; k++) for (int q = 0; q < NPOS; q++) if (v_cm[k]) begin
          if (BE_OFF[k] == 0) begin
            if (!(vini[0] && INIT_CNU_PRIOR[k]) && !sm_eq(dut.v2c_o0_st[BE_IDX[k]][q], v_v2c_o0[BE_IDX[k]][q])) d_o0++;
          end else if (!sm_eq(dut.v2c_o1_st[BE_IDX[k]][q], v_v2c_o1[BE_IDX[k]][q])) d_o1++;
        end
        for (int t = 0; t < NTYPES; t++) for (int q = 0; q < NPOS; q++) begin
          if (v_cmpc[t][q]) begin
            if (dut.g8_cur[t][q] !== v_g8c[t][q]) d_g8c++;
            if (dut.mpost_cur[t][q] !== v_mc[t][q]) d_mc++;
            for (int j = 0; j < DVMAX; j++) if (TS_EDGE[t][j] >= 0 && v_vc[t][j] && BE_OFF[TS_EDGE[t][j]] == 1
                                               && !(vini[0] && INIT_ZERO_CUR[t][j])
                                               && !sm_eq(dut.c2v_cur_late_st[BE_IDX[TS_EDGE[t][j]]][q], v_c2v_late[BE_IDX[TS_EDGE[t][j]]][q])) d_late++;
          end
          if (v_cmpp[t][q]) begin
            if (dut.g8_prev[t][q] !== v_g8p[t][q]) d_g8p++;
            if (dut.mpost_prev[t][q] !== v_mp[t][q]) d_mp++;
            for (int j = 0; j < DVMAX; j++) if (TS_EDGE[t][j] >= 0 && v_vp[t][j] && BE_OFF[TS_EDGE[t][j]] == 0
                                               && !sm_eq(dut.c2v_prev_o0_st[BE_IDX[TS_EDGE[t][j]]][q], v_c2v_prev_o0[BE_IDX[TS_EDGE[t][j]]][q])) d_po0++;
          end
        end
        if (dut.c2v_out !== v_ec2v) d_c2v++;
        nb = d_g + d_ini + d_syn + d_cm + d_vc + d_vp + d_o0 + d_o1 + d_g8c + d_mc + d_late + d_g8p + d_mp + d_po0 + d_c2v;
        if (nb) begin
          vbad_steps++;
          if (vbad_steps <= 3 && d_po0)
            for (int tt = 0; tt < NTYPES; tt++) for (int q = 0; q < NPOS; q++) if (v_cmpp[tt][q])
              for (int j = 0; j < DVMAX; j++) if (TS_EDGE[tt][j] >= 0 && v_vp[tt][j] && BE_OFF[TS_EDGE[tt][j]] == 0
                  && dut.c2v_prev_o0_st[BE_IDX[TS_EDGE[tt][j]]][q] !== v_c2v_prev_o0[BE_IDX[TS_EDGE[tt][j]]][q])
                $display("   prev c2v_o0 t %0d p %0d slot %0d: engine %h golden %h", tt, q, j,
                         dut.c2v_prev_o0_st[BE_IDX[TS_EDGE[tt][j]]][q], v_c2v_prev_o0[BE_IDX[TS_EDGE[tt][j]]][q]);
          if (vbad_steps <= 12)
            $display("VEC step %0d (iter %0d, g %0d/%0d, init %0d): g %0d init %0d syn %0d cnu_mask %0d vmask %0d/%0d | v2c_o0 %0d v2c_o1 %0d | cur: g8 %0d mpost %0d late_c2v %0d | prev: g8 %0d mpost %0d c2v_o0 %0d | c2v_out %0d",
                     vstep, vstep / 13, dut.rs_g, vg, vini, d_g, d_ini, d_syn, d_cm, d_vc, d_vp, d_o0, d_o1, d_g8c, d_mc, d_late,
                     d_g8p, d_mp, d_po0, d_c2v);
        end
      end
    end
    vstep++;
  end

  string LIST, fn, line, name;
  int lf, fd, nshots = 0, nbad = 0, n_leg0 = 0, tot_it = 0;
  initial begin
    if (!$value$plusargs("LIST=%s", LIST)) LIST = "shots.txt";
    if ($value$plusargs("VEC=%s", VEC)) begin vf = $fopen(VEC, "r"); if (vf == 0) begin $display("FAIL: no %s", VEC); $finish; end end
    begin   // +VSKIP=n: skip the first n step vectors (steps of the shots before this one); +VSTEPS=m: compare m steps
      automatic int sk = 0; string ln;
      if (vf != 0 && $value$plusargs("VSKIP=%d", sk)) repeat (sk) void'($fgets(ln, vf));
      if (!$value$plusargs("VSTEPS=%d", vmax)) vmax = 1 << 30;
    end
    lf = $fopen(LIST, "r");
    if (lf == 0) begin $display("FAIL: no list %s", LIST); $finish; end
    while ($fscanf(lf, "%s", fn) == 1) begin
      automatic int bad_hard = 0, n_hard = 0, bad = 0, guard = 0;
      fd = $fopen(fn, "r");
      if (fd == 0) begin $display("FAIL: no shot file %s", fn); $finish; end
      void'($fscanf(fd, "%d %d %d %h", e_it, e_succ, nlegs, e_obs));
      for (int h = 0; h < NRND; h++) for (int t = 0; t < NTYPES; t++) void'($fscanf(fd, "%d", ptab[h][t]));
      for (int h = 0; h < NRND; h++) void'($fscanf(fd, "%h", syn[h]));
      for (int h = 0; h < NRND; h++) void'($fscanf(fd, "%h %h", e_hard[h], e_mask[h]));
      for (int l = 0; l < nlegs; l++) for (int h = 0; h < NRND; h++) void'($fscanf(fd, "%h", g8tab[l][h]));
      $fclose(fd);
      if (nlegs > LEGMAX) begin $display("FAIL: %s needs %0d legs", fn, nlegs); $finish; end
      // ---- reset, priors, syndromes
      rst = 1; start = 0; repeat (4) @(negedge clk);
      for (int h = 0; h < NRND; h++) for (int t = 0; t < NTYPES; t++) begin
        pr_we = 1; pr_wround = PRW'(h); pr_wtype = TW'(t); pr_wdata = MW'(ptab[h][t]); @(negedge clk);
      end
      pr_we = 0;
      for (int h = 0; h < NRND; h++) begin arr_valid = 1; arr_idx = IW'(h); arr_data = syn[h]; @(negedge clk); end
      arr_valid = 0;
      // ---- M(-1) = L0 into both marginal banks (backdoor; no hardware init path in engine_top_pf2)
      if ($test$plusargs("BACKDOOR")) for (int h = 0; h < NRND; h++) begin   // only with +BACKDOOR (engine fills M(-1))
        automatic logic [7*NPOS*MB-1:0] whp = '0; automatic logic [3*NPOS*MB-1:0] wnp = '0;
        for (int t = 0; t < NTYPES; t++) for (int p = 0; p < NPOS; p++) begin
          if (HAS_PREV[t]) whp[(hp_rank(t, 1'b1) * NPOS + p) * MB +: MB] = MB'(ptab[h][t]);
          else             wnp[(hp_rank(t, 1'b0) * NPOS + p) * MB +: MB] = MB'(ptab[h][t]);
        end
        dut.g_bank[0].u_m_hp_r.g_lutram.mem[h] = whp; dut.g_bank[1].u_m_hp_r.g_lutram.mem[h] = whp;
        dut.g_bank[0].u_m_hp_rm1.g_lutram.mem[h] = whp; dut.g_bank[1].u_m_hp_rm1.g_lutram.mem[h] = whp;
        dut.g_bank[0].u_m_np_r.g_lutram.mem[h] = wnp; dut.g_bank[1].u_m_np_r.g_lutram.mem[h] = wnp;
      end
      @(negedge clk); rst = 0; @(negedge clk); @(negedge clk);
      last_is = -1; last_delta = -1; d_norm_sum = 0; d_norm_n = 0; d_end_sum = 0; d_end_n = 0; first_is = -1; bad_leg = 0;
      begin
        automatic int c0;
        start = 1; c0 = int'(cyc); @(negedge clk); start = 0;
        while (!done && guard < (e_it + 10) * 60 + 5000) begin @(negedge clk); guard++; end
        done_cyc = int'(cyc);
        // commit: C beats after done (cm_run), obs valid 2 cycles after the last beat
        while (!dut.cm_run && guard < (e_it + 10) * 60 + 6000) begin @(negedge clk); guard++; end
        while (dut.cm_run && guard < (e_it + 10) * 60 + 6000) begin @(negedge clk); guard++; end
        repeat (2) @(negedge clk);
        obs_cyc = int'(cyc);
        // hard decisions of the bank the commit reads
        for (int h = 0; h < NRND; h++) begin
          automatic logic [NV-1:0] g = dut.hard_r[dut.cbank][h];
          for (int k = 0; k < NV; k++) if (e_mask[h][k]) begin n_hard++; if (g[k] !== e_hard[h][k]) bad_hard++; end
        end
        if (!done) bad++;
        if (int'(iter_total) != e_it) bad++;
        if (success !== e_succ[0]) bad++;
        if (bad_hard) bad++;
        if (!obs_valid || obs !== e_obs) bad++;
        if (bad_leg) bad++;
        nshots++; if (bad) nbad++; if (e_it <= 80) n_leg0++; tot_it += e_it;
        $display("SHOT %s it %0d/%0d succ %0d/%0d hard_bad %0d/%0d obs %h/%h legs %0d cycles start->done %0d done->obs %0d first_iter_start %0d norm_iters %0d mean %.3f leg_end_iters %0d mean %.3f last_iter_to_done %0d %s",
                 fn, iter_total, e_it, success, e_succ, bad_hard, n_hard, obs, e_obs, nlegs, done_cyc - c0,
                 obs_cyc - done_cyc, first_is - c0, d_norm_n, d_norm_n ? real'(d_norm_sum) / d_norm_n : 0.0,
                 d_end_n, d_end_n ? real'(d_end_sum) / d_end_n : 0.0, done_cyc - last_is, bad ? "MISMATCH" : "OK");
      end
    end
    if (vf != 0) $display("VEC: steps compared %0d, steps with input differences %0d", vstep, vbad_steps);
    $display("tb_engine_3d: shots %0d, mismatching %0d, converged in leg 0 %0d, iterations %0d", nshots, nbad, n_leg0, tot_it);
    $display("%s", (nshots > 0 && nbad == 0) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
