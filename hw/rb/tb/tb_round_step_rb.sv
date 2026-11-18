// tb_round_step_rb.sv — Test 2f: golden replay of round_step_rb, one round step issued every cycle (back to back), each
// input in its pipeline stage (S0 control, S2 v2c, S3 g8 / M(t-1), S4 stored c2v), so up to 7 steps are in flight.
// Vectors from gen_vectors_rb.py (rb13 dumps, hardware memory view with junk before the first write and junk M(-1)).
// Checks every step: all 2,520 c2v (sign and magnitude) at S5; bias at S5 and marginal, hard decision and every v2c at
// S6 of every error updated in the layer (cmp masks). Priors from prior_table.txt through the load port.
// Plusargs: +VEC=<file> +PRIOR=<file>
`timescale 1ns/1ps
module tb_round_step_rb;
  import round_wiring_pkg::*;
  localparam int N = 4, MB = N + 3, MW = N + 1, NRND = 13, RW = $clog2(NRND), TW = $clog2(NTYPES), DEPTH = 8;
  logic clk = 0, rst = 1;
  always #5 clk = ~clk;
  logic pr_we = 0; logic [RW-1:0] pr_wround = '0; logic [TW-1:0] pr_wtype = '0; logic [MW-1:0] pr_wdata = '0;
  logic in_valid = 0, init = 0, first = 0, pass = 0; logic [RW-1:0] round_idx = '0;
  logic [NPOS-1:0] syn = '0; logic [NBASE-1:0] cnu_mask = '0;
  logic [NTYPES-1:0][DVMAX-1:0] vmask_cur = '0, vmask_prev = '0;
  logic [NE0-1:0][NPOS-1:0][MW-1:0] v2c_o0_st = '0, c2v_prev_o0_st = '0;
  logic [NE1-1:0][NPOS-1:0][MW-1:0] v2c_o1_st = '0, c2v_cur_late_st = '0;
  logic [NTYPES-1:0][NPOS-1:0][3:0] g8_cur = '0, g8_prev = '0;
  logic [NTYPES-1:0][NPOS-1:0][MB-1:0] mpost_cur = '0, mpost_prev = '0;
  logic c2v_valid, out_valid;
  logic [NPOS-1:0][NBASE-1:0][MW-1:0] c2v_out;
  logic [NE0-1:0][NPOS-1:0][MW-1:0] c2v_o0;
  logic [NE1-1:0][NPOS-1:0][MW-1:0] c2v_o1;
  logic [NTYPES-1:0][NPOS-1:0][MB-1:0] cur_bias, prev_bias, cur_marg, prev_marg;
  logic [NTYPES-1:0][NPOS-1:0] cur_hard, prev_hard;
  logic [NTYPES-1:0][NPOS-1:0][DVMAX-1:0][MW-1:0] cur_v2c, prev_v2c;

  round_step_rb #(.N(N), .NRND(NRND)) dut (.*);

  // ring buffer of vectors (step n in slot n % DEPTH)
  int r_g [DEPTH], r_init [DEPTH], r_first [DEPTH];
  logic [NPOS-1:0] r_syn [DEPTH]; logic [NBASE-1:0] r_cm [DEPTH];
  logic [NE0-1:0][NPOS-1:0][MW-1:0] r_o0 [DEPTH], r_po0 [DEPTH];
  logic [NE1-1:0][NPOS-1:0][MW-1:0] r_o1 [DEPTH], r_late [DEPTH];
  logic [NTYPES-1:0][NPOS-1:0][MW-1:0] r_pc, r_pp;            // unused (priors come from the register file)
  logic [NTYPES-1:0][NPOS-1:0][3:0] r_g8c [DEPTH], r_g8p [DEPTH];
  logic [NTYPES-1:0][NPOS-1:0][MB-1:0] r_mc [DEPTH], r_mp [DEPTH];
  logic [NTYPES-1:0][DVMAX-1:0] r_vc [DEPTH], r_vp [DEPTH];
  logic [NPOS-1:0][NBASE-1:0][MW-1:0] x_c2v [DEPTH];
  logic [NTYPES-1:0][NPOS-1:0][MB-1:0] x_cb [DEPTH], x_cm [DEPTH], x_pb [DEPTH], x_pm [DEPTH];
  logic [NTYPES-1:0][NPOS-1:0] x_ch [DEPTH], x_ph [DEPTH], k_c [DEPTH], k_p [DEPTH];
  logic [NTYPES-1:0][NPOS-1:0][DVMAX-1:0][MW-1:0] x_cv [DEPTH], x_pv [DEPTH];

  string VEC, PRI;
  int vf, pf, nvec = 0, bad_steps = 0, bad_c2v = 0, bad_bias = 0, bad_vnu = 0, init_steps = 0, first_steps = 0;
  int n_upd = 0, n_c2v_edges = 0;
  bit eof = 0;
  int last_n = -1;

  task automatic read_step(input int n);
    int q = n % DEPTH;
    int rv = $fscanf(vf, "%d %d %d %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h %h",
      r_g[q], r_init[q], r_first[q], r_syn[q], r_cm[q], r_o0[q], r_o1[q], r_pc, r_g8c[q], r_mc[q], r_late[q], r_vc[q],
      r_pp, r_g8p[q], r_mp[q], r_po0[q], r_vp[q], x_c2v[q], x_cb[q], x_cm[q], x_ch[q], x_cv[q], x_pb[q], x_pm[q],
      x_ph[q], x_pv[q], k_c[q], k_p[q]);
    if (rv != 28) begin eof = 1; last_n = n; end
  endtask

  int step_bad [DEPTH];
  initial begin
    if (!$value$plusargs("VEC=%s", VEC)) VEC = "vectors/round_vectors_rb.txt";
    if (!$value$plusargs("PRIOR=%s", PRI)) PRI = "vectors/prior_table.txt";
    vf = $fopen(VEC, "r"); pf = $fopen(PRI, "r");
    if (vf == 0 || pf == 0) begin $display("FAIL: cannot open %s / %s", VEC, PRI); $finish; end
    repeat (3) @(negedge clk);
    rst = 0;
    for (int h = 0; h < NRND; h++) for (int t = 0; t < NTYPES; t++) begin
      int x; void'($fscanf(pf, "%d", x));
      pr_we = 1; pr_wround = RW'(h); pr_wtype = TW'(t); pr_wdata = MW'(x); @(negedge clk);
    end
    pr_we = 0; @(negedge clk);
    for (int k = 0; ; k++) begin
      // ---- checks (outputs registered at the posedge before this negedge)
      if (k >= 5 && (last_n < 0 || k - 5 < last_n)) begin
        automatic int s = k - 5, q = (k - 5) % DEPTH, nb = 0, nc = 0;
        if (!c2v_valid) begin $display("FAIL: c2v_valid low for step %0d", s); $finish; end
        for (int x = 0; x < NPOS; x++) for (int e = 0; e < NBASE; e++) if (c2v_out[x][e] !== x_c2v[q][x][e]) nc++;
        n_c2v_edges += NPOS * NBASE;
        for (int t = 0; t < NTYPES; t++) for (int p = 0; p < NPOS; p++) begin
          if (k_c[q][t][p] && cur_bias[t][p] !== x_cb[q][t][p]) nb++;
          if (k_p[q][t][p] && prev_bias[t][p] !== x_pb[q][t][p]) nb++;
        end
        bad_c2v += nc; bad_bias += nb; step_bad[q] = nc + nb;
        if ((nc || nb) && bad_steps < 8) $display("step %0d (g %0d init %0d): c2v mismatches %0d, bias mismatches %0d", s, r_g[q], r_init[q], nc, nb);
      end
      if (k >= 6 && (last_n < 0 || k - 6 < last_n)) begin
        automatic int s = k - 6, q = (k - 6) % DEPTH, nv = 0;
        if (!out_valid) begin $display("FAIL: out_valid low for step %0d", s); $finish; end
        for (int t = 0; t < NTYPES; t++) for (int p = 0; p < NPOS; p++) begin
          if (k_c[q][t][p]) begin
            n_upd++;
            if (cur_marg[t][p] !== x_cm[q][t][p] || cur_hard[t][p] !== x_ch[q][t][p] || cur_v2c[t][p] !== x_cv[q][t][p]) nv++;
          end
          if (k_p[q][t][p]) begin
            n_upd++;
            if (prev_marg[t][p] !== x_pm[q][t][p] || prev_hard[t][p] !== x_ph[q][t][p] || prev_v2c[t][p] !== x_pv[q][t][p]) nv++;
          end
        end
        bad_vnu += nv;
        if (nv && bad_steps < 8) $display("step %0d (g %0d init %0d first %0d): VNU mismatches %0d", s, r_g[q], r_init[q], r_first[q], nv);
        if (nv || step_bad[q]) bad_steps++;
        nvec++; init_steps += r_init[q]; first_steps += r_first[q];
      end
      if (last_n >= 0 && k - 6 >= last_n) break;
      // ---- drive: S0 of step k, S2 of k - 2, S3 of k - 3, S4 of k - 4
      if (!eof) read_step(k);
      if (!eof) begin
        automatic int q = k % DEPTH;
        in_valid = 1; round_idx = RW'(r_g[q]); init = r_init[q][0]; first = r_first[q][0]; pass = r_g[q][0];
        syn = r_syn[q]; cnu_mask = r_cm[q]; vmask_cur = r_vc[q]; vmask_prev = r_vp[q];
      end else begin
        in_valid = 0; init = 0; first = 0;
      end
      if (k >= 2 && (last_n < 0 || k - 2 < last_n)) begin
        v2c_o0_st = r_o0[(k - 2) % DEPTH]; v2c_o1_st = r_o1[(k - 2) % DEPTH];
      end
      if (k >= 3 && (last_n < 0 || k - 3 < last_n)) begin
        automatic int q = (k - 3) % DEPTH;
        g8_cur = r_g8c[q]; g8_prev = r_g8p[q]; mpost_cur = r_mc[q]; mpost_prev = r_mp[q];
      end
      if (k >= 4 && (last_n < 0 || k - 4 < last_n)) begin
        c2v_cur_late_st = r_late[(k - 4) % DEPTH]; c2v_prev_o0_st = r_po0[(k - 4) % DEPTH];
      end
      @(negedge clk);
    end
    $display("tb_round_step_rb: steps %0d (init %0d, first %0d), c2v edges %0d, error updates %0d", nvec, init_steps,
             first_steps, n_c2v_edges, n_upd);
    $display("mismatches: steps %0d, c2v %0d, bias %0d, VNU %0d", bad_steps, bad_c2v, bad_bias, bad_vnu);
    $display("%s", (nvec > 0 && bad_steps == 0) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
