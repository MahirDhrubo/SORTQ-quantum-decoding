// tb_round_step_pf2.sv — round_step_pf2 (Test 2c follow-up: two-level prior tree prefetched two steps ahead,
// cur_valid copies, vnu_nosat) with the same golden replay as tb_round_step.sv. The round of step n + 2 is given
// (nxt_valid / nxt_round_idx) in the start cycle of step n, and the rounds of steps 0 and 1 before step 0;
// +FLUSH: at every step with round 0 (iteration start) the two prefetches that should carry its rounds carry round
// 12 instead (wrong priors), then pf_flush + two correct loads are given before the step: a stale prior left in
// the pipeline would change that step's results.
// (from tb_round_step_pf.sv) the steps run back to back (period VNU_PASSES + 1), so a prior that moves
// into the stage-B copies one cycle too early or too late changes a result at every round boundary where the
// priors differ (rounds 0, 11, 12 of the table).
//
// (from tb_round_step.sv) one full round step (prior register file + init mux + wiring + 72 CNUs + VNUs) replayed against
// the golden dumps (vectors from gen_vectors_round.py): every round step of the dumped shots.
// The prior register file is loaded once through the load port from prior_table.txt (the per-error priors in the
// vector lines are not driven; the generator checked that every error equals its table entry).
// Each step: one in_valid pulse, inputs held until out_valid. Checks
//   - all 2,520 c2v outputs (sign and magnitude; masked edges must be 0),
//   - for every error updated in the layer (both groups): bias, marginal, hard decision, all 6 v2c slots,
//     cur group sampled at cur_valid, prev group at prev_valid,
//   - latency start -> out_valid = VNU_PASSES + 1 cycles, and in_ready low until then (step period).
// Parameter VNU_PASSES (1 / 2); run-time plusargs +VEC=<vector file> +PTAB=<prior table> (defaults below).
`timescale 1ns/1ps
module tb_round_step_pf2 #(
  parameter int VNU_PASSES = 1
);
  string VEC = "vectors/round_vectors.txt", PTAB = "vectors/prior_table.txt";
  import round_wiring_pkg::*;
  localparam int N = 4, MB = N + 3, MW = N + 1, NRND = 13, RW = $clog2(NRND), TW = $clog2(NTYPES);
  logic clk = 0, rst = 1, in_valid = 0, in_ready, init = 0, cur_valid, prev_valid, out_valid;
  logic pr_we = 0, nxt_valid = 0, pf_flush = 0; logic [RW-1:0] pr_wround = '0, nxt_round_idx = '0; logic [TW-1:0] pr_wtype = '0;
  logic [MW-1:0] pr_wdata = '0;
  logic [NPOS-1:0] syn;
  logic [NBASE-1:0] cnu_mask;
  logic [NE0-1:0][NPOS-1:0][MW-1:0] v2c_o0_st, c2v_prev_o0_st;
  logic [NE1-1:0][NPOS-1:0][MW-1:0] v2c_o1_st, c2v_cur_late_st;
  logic [NTYPES-1:0][NPOS-1:0][MW-1:0] prior_cur_v, prior_prev_v;     // read from the vectors, not driven
  logic [NTYPES-1:0][NPOS-1:0][3:0] g8_cur, g8_prev;
  logic [NTYPES-1:0][NPOS-1:0][MB-1:0] mpost_cur, mpost_prev, cur_bias, cur_marg, prev_bias, prev_marg;
  logic [NTYPES-1:0][DVMAX-1:0] vmask_cur, vmask_prev;
  logic [NPOS-1:0][NBASE-1:0][MW-1:0] c2v_out, e_c2v;
  logic [NTYPES-1:0][NPOS-1:0] cur_hard, prev_hard;
  logic [NTYPES-1:0][NPOS-1:0][DVMAX-1:0][MW-1:0] cur_v2c, prev_v2c;
  // expected
  logic [NTYPES-1:0][NPOS-1:0][MB-1:0] e_cb, e_cm, e_pb, e_pm;
  logic [NTYPES-1:0][NPOS-1:0] e_ch, e_ph, cmp_c, cmp_p;
  logic [NTYPES-1:0][NPOS-1:0][DVMAX-1:0][MW-1:0] e_cv, e_pv;
  // captured outputs
  logic [NTYPES-1:0][NPOS-1:0][MB-1:0] k_cb, k_cm, k_pb, k_pm;
  logic [NTYPES-1:0][NPOS-1:0] k_ch, k_ph;
  logic [NTYPES-1:0][NPOS-1:0][DVMAX-1:0][MW-1:0] k_cv, k_pv;
  always #5 clk = ~clk;
  logic [NPOS-1:0] cur_valid_dup;   // checked against cur_valid inside the DUT (simulation-only $fatal)
  round_step_pf2 #(.N(N), .VNU_PASSES(VNU_PASSES), .NRND(NRND)) dut (.*);
  int gs[$];   // rounds of all steps (pre-scan of the vector file)
  bit flush_mode; int n_flush = 0;
  function automatic int pf_round(int k);   // round sent as the prefetch for step k
    if (k >= gs.size()) return 0;
    if (flush_mode && gs[k] == 0) return 12; // deliberately wrong: must be dropped by pf_flush
    if (flush_mode && k >= 1 && gs[k - 1] == 0) return 12;
    return gs[k];
  endfunction

  int fd, g, ini, n = 0, n_init = 0, n_init_leg = 0, nbad = 0, bad_c2v = 0, bad_vnu = 0, n_err_cmp = 0;
  int bad_lat = 0, bad_ready = 0, lat, got_c, got_p, n_prior = 0;
  initial begin
    void'($value$plusargs("VEC=%s", VEC)); void'($value$plusargs("PTAB=%s", PTAB));
    flush_mode = $test$plusargs("FLUSH");
    // ---- load the prior register file through the load port
    fd = $fopen(PTAB, "r");
    if (fd == 0) begin $display("FAIL: no prior table %s", PTAB); $finish; end
    repeat (2) @(negedge clk);
    for (int h = 0; h < NRND; h++) for (int t = 0; t < NTYPES; t++) begin
      int v;
      if ($fscanf(fd, "%d", v) != 1) begin $display("FAIL: short prior table"); $finish; end
      pr_we = 1; pr_wround = RW'(h); pr_wtype = TW'(t); pr_wdata = MW'(v); n_prior++;
      @(negedge clk);
    end
    pr_we = 0; $fclose(fd);
    rst = 0; @(negedge clk);
    // ---- pre-scan: round of every step (first field of each vector line)
    fd = $fopen(VEC, "r");
    if (fd == 0) begin $display("FAIL: no vectors %s", VEC); $finish; end
    begin
      string line; int gv;
      while ($fgets(line, fd)) if ($sscanf(line, "%d", gv) == 1) gs.push_back(gv);
    end
    $fclose(fd);
    // prefetch for steps 0 and 1 (idle): A -> A2 -> B for step 0, step 1 waits in A2
    nxt_valid = 1; nxt_round_idx = RW'(gs[0]); @(negedge clk); nxt_valid = 0; repeat (3) @(negedge clk);
    if (gs.size() > 1) begin nxt_valid = 1; nxt_round_idx = RW'(gs[1]); @(negedge clk); nxt_valid = 0; end
    repeat (3) @(negedge clk);
    // ---- round steps
    fd = $fopen(VEC, "r");
    if (fd == 0) begin $display("FAIL: no vectors %s", VEC); $finish; end
    while ($fscanf(fd, "%d %d %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h",
                   g, ini, syn, cnu_mask, v2c_o0_st, v2c_o1_st, prior_cur_v, g8_cur, mpost_cur, c2v_cur_late_st,
                   vmask_cur, prior_prev_v, g8_prev, mpost_prev, c2v_prev_o0_st, vmask_prev, e_c2v,
                   e_cb, e_cm, e_ch, e_cv, e_pb, e_pm, e_ph, e_pv, cmp_c, cmp_p) == 27) begin
      init = ini[0];
      if (g != gs[n]) begin $display("FAIL: pre-scan mismatch at step %0d", n); $finish; end
      if (flush_mode && n > 0 && gs[n] == 0) begin       // drop the wrong prefetches, load steps n and n + 1
        pf_flush = 1; nxt_valid = 1; nxt_round_idx = RW'(gs[n]); @(negedge clk); pf_flush = 0; nxt_valid = 0;
        repeat (3) @(negedge clk);
        if (n + 1 < gs.size()) begin nxt_valid = 1; nxt_round_idx = RW'(gs[n + 1]); @(negedge clk); nxt_valid = 0; end
        repeat (3) @(negedge clk);
        n_flush++;
      end
      if (init) begin n_init++; if (g == 0) n_init_leg++; end
      if (!in_ready) bad_ready++;
      in_valid = 1;
      nxt_valid = (n + 2 < gs.size()); nxt_round_idx = RW'(pf_round(n + 2));  // round two steps ahead
      @(posedge clk); #1 in_valid = 0; nxt_valid = 0;
      lat = 0; got_c = 0; got_p = 0;
      while (!out_valid && lat < 10) begin
        if (in_ready) bad_ready++;                       // must stay busy until the step's last results
        @(posedge clk); #1 lat++;
        if (cur_valid) begin got_c++; k_cb = cur_bias; k_cm = cur_marg; k_ch = cur_hard; k_cv = cur_v2c; end
        if (prev_valid) begin got_p++; k_pb = prev_bias; k_pm = prev_marg; k_ph = prev_hard; k_pv = prev_v2c; end
      end
      if (lat + 1 != VNU_PASSES + 1 || got_c != 1 || got_p != 1) bad_lat++;
      begin
        automatic int bad = 0;
        if (c2v_out !== e_c2v) begin
          bad++; bad_c2v++;
          if (bad_c2v <= 3) for (int x = 0; x < NPOS; x++) for (int k = 0; k < NBASE; k++)
            if (c2v_out[x][k] !== e_c2v[x][k]) $display("  step %0d g=%0d c2v x=%0d k=%0d got %h exp %h", n, g, x, k, c2v_out[x][k], e_c2v[x][k]);
        end
        for (int t = 0; t < NTYPES; t++) for (int p = 0; p < NPOS; p++) begin
          if (cmp_c[t][p]) begin
            n_err_cmp++;
            if (k_cb[t][p] !== e_cb[t][p] || k_cm[t][p] !== e_cm[t][p] || k_ch[t][p] !== e_ch[t][p]
                || k_cv[t][p] !== e_cv[t][p]) begin bad++; bad_vnu++; end
          end
          if (cmp_p[t][p]) begin
            n_err_cmp++;
            if (k_pb[t][p] !== e_pb[t][p] || k_pm[t][p] !== e_pm[t][p] || k_ph[t][p] !== e_ph[t][p]
                || k_pv[t][p] !== e_pv[t][p]) begin bad++; bad_vnu++; end
          end
        end
        if (bad) begin nbad++; if (nbad <= 5) $display("MISMATCH step %0d (g = %0d, init %0d): %0d", n, g, init, bad); end
      end
      n++;
      @(negedge clk);
    end
    if (flush_mode) $display("FLUSH mode: %0d flushes (wrong prefetches dropped before each)", n_flush);
    $display("tb_round_step_pf2 VNU_PASSES=%0d %s: priors loaded %0d, round steps %0d (init %0d, leg starts %0d), error updates compared %0d, mismatching steps %0d [c2v %0d, vnu %0d], latency start->out_valid %0d cycles (errors %0d), in_ready errors %0d",
             VNU_PASSES, VEC, n_prior, n, n_init, n_init_leg, n_err_cmp, nbad, bad_c2v, bad_vnu, VNU_PASSES + 1, bad_lat, bad_ready);
    $display("%s", (n > 0 && nbad == 0 && bad_lat == 0 && bad_ready == 0) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
