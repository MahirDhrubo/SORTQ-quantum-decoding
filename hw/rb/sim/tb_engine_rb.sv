// tb_engine_rb.sv — Test 2f: closed-loop simulation of engine_top_rb (LUTRAM model), the Test 3d testbench adapted to
// the red-black order. Complete shots decoded end to end (ctrl_rb -> banked memories -> round_step_rb -> conv_check ->
// commit) and compared with the rb13 software decoder: iterations, success, all hard decisions (bank of the last checked
// iteration) and the 12 observables. No backdoor: M(-1) = L0 and leg-0 g8 come from the engine's own paths.
// Gamma lanes in LOAD mode (+define+RB_G8LOAD): whenever the engine draws (prefill or even init step), the lanes load
// the software g8 of (lane_leg, lane_home).
// Cycle accounting per shot: iteration length = iter_start to the next iter_start; an iteration followed by a relay-leg
// start is a "leg-end" iteration. Hazard checker counters (engine, simulation only) are printed at the end.
`timescale 1ns/1ps
module tb_engine_rb;
  import round_wiring_pkg::*;
  import engine_tables_pkg::*;
  localparam int N = 4, MB = N + 3, MW = N + 1, W = 13, C = 13, NRND = 13, RW = 8, LEGMAX = 10;
  localparam int IW = $clog2(W), PRW = $clog2(NRND), TW = $clog2(NTYPES);
  localparam int NV = NTYPES * NPOS;
  logic clk = 0, rst = 1, start = 0, arr_valid = 0, pr_we = 0;
  logic [RW-1:0] win_t = '0, last_r = 8'd12;
  logic [IW-1:0] arr_idx = '0; logic [NPOS-1:0] arr_data = '0;
  logic [PRW-1:0] pr_wround = '0; logic [TW-1:0] pr_wtype = '0; logic [MW-1:0] pr_wdata = '0;
  logic [NTYPES-1:0][NPOS-1:0][3:0] g8_ld_data;
  logic lane_draw; logic [8:0] lane_leg; logic [IW-1:0] lane_home;
  logic done, success, obs_valid, syn_corr_valid; logic [15:0] iter_total; logic [NOBS-1:0] obs;
  logic [NPOS-1:0] syn_corr;
  always #5 clk = ~clk;

  engine_top_rb #(.N(N), .STORAGE("LUTRAM"), .W(W), .C(C), .NRND(NRND), .RW(RW)) dut (.*);

  int e_it, e_succ, nlegs; logic [NOBS-1:0] e_obs;
  int ptab [NRND][NTYPES];
  logic [NPOS-1:0] syn [NRND];
  logic [NV-1:0] e_hard [NRND], e_mask [NRND];
  logic [NV*4-1:0] g8tab [LEGMAX][NRND];

  assign g8_ld_data = g8tab[(int'(lane_leg) < LEGMAX) ? int'(lane_leg) : 0][lane_home];
  int bad_leg = 0, n_draws = 0, n_pre = 0;
  always @(posedge clk) if (!rst && lane_draw) begin
    n_draws++; if (dut.pre_run) n_pre++;
    // a prefill draw is speculative (the decode may converge in the leg-end iteration): only draws for legs that
    // actually run must have software g8; the prefill leg is checked at the end of the shot (dut.leg < nlegs)
    if (!dut.pre_run && int'(lane_leg) >= nlegs) bad_leg++;
  end

  // cycle accounting
  longint cyc = 0; int last_is = -1, last_delta = -1;
  int d_norm_sum = 0, d_norm_n = 0, d_end_sum = 0, d_end_n = 0, first_is = -1, first_step = -1, done_cyc = -1, obs_cyc = -1;
  int d_norm_min = 1 << 30, d_norm_max = 0, d_end_min = 1 << 30, d_end_max = 0, n_pend_wait = 0;
  bit pend_is;
  always @(posedge clk) begin
    cyc <= cyc + 1;
    if (!rst && !done) begin
      if (dut.u_ctrl.st == dut.u_ctrl.PEND_WAIT) n_pend_wait++;
      if (first_step < 0 && dut.step_valid[0]) first_step = int'(cyc);
      if (dut.iter_start) begin
        if (last_is >= 0) last_delta = int'(cyc) - last_is; else first_is = int'(cyc);
        last_is = int'(cyc); pend_is = 1;
      end
      if (pend_is && dut.step_valid[0]) begin
        pend_is = 0;
        if (last_delta >= 0) begin
          if (dut.c_init[0]) begin
            d_end_sum += last_delta; d_end_n++;
            if (last_delta < d_end_min) d_end_min = last_delta; if (last_delta > d_end_max) d_end_max = last_delta;
          end else begin
            d_norm_sum += last_delta; d_norm_n++;
            if (last_delta < d_norm_min) d_norm_min = last_delta; if (last_delta > d_norm_max) d_norm_max = last_delta;
          end
        end
      end
    end
  end
  // step-issue gaps inside iterations (must be 0: one step per cycle; every iteration starts with round 0)
  int gap_in_iter = 0; longint last_step = -10;
  always @(posedge clk) if (!rst && dut.step_valid[0]) begin
    if (dut.step_g[0] != '0 && cyc != last_step + 1) gap_in_iter++;
    last_step = cyc;
  end

  string LIST, fn;
  int lf, fd, nshots = 0, nbad = 0, n_leg0 = 0, tot_it = 0, tot_legstarts = 0;
  longint tot_norm = 0, tot_norm_n = 0;
  initial begin
    if (!$value$plusargs("LIST=%s", LIST)) LIST = "shots.txt";
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
      // the engine is NOT reset between shots unless +RESET (memories keep the previous shot's state: the
      // decode-start paths must not depend on it)
      if ($test$plusargs("RESET") || nshots == 0) begin
        rst = 1; start = 0; repeat (4) @(negedge clk);
      end
      for (int h = 0; h < NRND; h++) for (int t = 0; t < NTYPES; t++) begin
        pr_we = 1; pr_wround = PRW'(h); pr_wtype = TW'(t); pr_wdata = MW'(ptab[h][t]); @(negedge clk);
      end
      pr_we = 0;
      for (int h = 0; h < NRND; h++) begin arr_valid = 1; arr_idx = IW'(h); arr_data = syn[h]; @(negedge clk); end
      arr_valid = 0;
      @(negedge clk); rst = 0; @(negedge clk); @(negedge clk);
      last_is = -1; last_delta = -1; d_norm_sum = 0; d_norm_n = 0; d_end_sum = 0; d_end_n = 0; first_is = -1;
      first_step = -1; bad_leg = 0; d_norm_min = 1 << 30; d_norm_max = 0; d_end_min = 1 << 30; d_end_max = 0;
      n_pend_wait = 0; n_draws = 0; n_pre = 0;
      begin
        automatic int c0;
        start = 1; c0 = int'(cyc); @(negedge clk); start = 0;
        while (!done && guard < (e_it + 10) * 40 + 5000) begin @(negedge clk); guard++; end
        done_cyc = int'(cyc);
        while (!dut.cm_run && guard < (e_it + 10) * 40 + 6000) begin @(negedge clk); guard++; end
        while (dut.cm_run && guard < (e_it + 10) * 40 + 6000) begin @(negedge clk); guard++; end
        repeat (2) @(negedge clk);
        obs_cyc = int'(cyc);
        for (int h = 0; h < NRND; h++) begin
          automatic logic [NV-1:0] g = dut.hard_r[dut.cbank][h];
          for (int k = 0; k < NV; k++) if (e_mask[h][k]) begin n_hard++; if (g[k] !== e_hard[h][k]) bad_hard++; end
        end
        if (!done) bad++;
        if (int'(iter_total) != e_it) bad++;
        if (success !== e_succ[0]) bad++;
        if (bad_hard) bad++;
        if (!obs_valid || obs !== e_obs) bad++;
        if (int'(dut.leg) >= nlegs) bad_leg++;
        if (bad_leg) bad++;
        nshots++; if (bad) nbad++; if (e_it <= 80) n_leg0++; tot_it += e_it; tot_legstarts += nlegs - 1;
        tot_norm += d_norm_sum; tot_norm_n += d_norm_n;
        $display("SHOT %s it %0d/%0d succ %0d/%0d hard_bad %0d/%0d obs %h/%h legs %0d cycles start->done %0d done->obs %0d start->first_step %0d norm_iters %0d mean %.3f min %0d max %0d leg_end_iters %0d mean %.3f min %0d max %0d last_iter_to_done %0d pend_wait %0d draws %0d prefill %0d %s",
                 fn, iter_total, e_it, success, e_succ, bad_hard, n_hard, obs, e_obs, nlegs, done_cyc - c0,
                 obs_cyc - done_cyc, first_step - c0, d_norm_n, d_norm_n ? real'(d_norm_sum) / d_norm_n : 0.0,
                 d_norm_n ? d_norm_min : 0, d_norm_max, d_end_n, d_end_n ? real'(d_end_sum) / d_end_n : 0.0,
                 d_end_n ? d_end_min : 0, d_end_max, done_cyc - last_is, n_pend_wait, n_draws, n_pre,
                 bad ? "MISMATCH" : "OK");
        repeat (8) @(negedge clk);                       // drain the speculative steps before the next shot
      end
    end
    $display("HAZARD-CHECK: reads checked %0d, RAW violations %0d, WAR violations %0d, writes scheduled %0d, real writes checked %0d, unscheduled %0d",
             dut.haz_reads, dut.haz_viol, dut.war_viol, dut.sched_cnt, dut.wr_checked, dut.wr_unsched);
    $display("step-issue gaps inside an iteration: %0d", gap_in_iter);
    $display("tb_engine_rb: shots %0d, mismatching %0d, converged in leg 0 %0d, iterations %0d, leg starts %0d, normal iterations %0d mean %.4f cycles",
             nshots, nbad, n_leg0, tot_it, tot_legstarts, tot_norm_n, tot_norm_n ? real'(tot_norm) / tot_norm_n : 0.0);
    $display("%s", (nshots > 0 && nbad == 0 && dut.haz_viol == 0 && dut.war_viol == 0 && dut.wr_unsched == 0 && gap_in_iter == 0) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
