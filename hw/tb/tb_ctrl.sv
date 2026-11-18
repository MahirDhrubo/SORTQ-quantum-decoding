// tb_ctrl.sv — ctrl (W = 12, R = 36) with small leg sizes (PRE_IT = 3, LEG_IT = 2, NLEGS = 2, STEP_CYCLES = 2).
//  A: masks. For windows t = 0, 8, 24, 32 the step sequence of one iteration must be g = t .. min(t+11, 36) and
//     cnu_mask / vnu_mask_cur / vnu_mask_prev / prev_active of every step must equal the masks derived from H
//     (vectors/ctrl_expected.txt); all NDUP copies must be identical.
//  B: sequencing, never converging (t = 8): 3 + 2 * 2 = 7 iterations, then done with success = 0; init = 1 exactly
//     in iterations 1, 4, 6 (first of each leg); gamma_start 1 pulse, gamma_next 2 pulses, iter_start 7 pulses.
//  C: converging at iteration 5: done, success = 1, iter_total = 5.
`timescale 1ns/1ps
module tb_ctrl;
  import round_wiring_pkg::*;
  localparam int NDUP = 2, RW = 8;
  logic clk = 0, rst = 1, start = 0, conv_valid = 0, conv = 0;
  logic [RW-1:0] win_t = '0, last_r = 8'd36;
  logic busy, done, success, gamma_start, gamma_next, iter_start, conv_req;
  logic [15:0] iter_total; logic [8:0] leg;
  logic [NDUP-1:0] step_valid, init, prev_active;
  logic [NDUP-1:0][RW-1:0] step_g;
  logic [NDUP-1:0][NBASE-1:0] cnu_mask;
  logic [NDUP-1:0][NTYPES-1:0][DVMAX-1:0] vnu_mask_cur, vnu_mask_prev;
  always #5 clk = ~clk;
  ctrl #(.W(12), .STEP_CYCLES(2), .PRE_IT(3), .LEG_IT(2), .NLEGS(2), .NDUP(NDUP), .RW(RW)) dut (.*);

  // expected masks
  int e_t [64], e_g [64], e_pa [64], ne = 0;
  logic [NBASE-1:0] e_cm [64];
  logic [NTYPES*DVMAX-1:0] e_vc [64], e_vp [64];
  int nbad_mask = 0, nbad_dup = 0, nsteps_a = 0, nbad_seq = 0;
  int conv_at = 0, iters = 0, n_gs = 0, n_gn = 0, n_is = 0, steps_in_iter = 0;
  int init_iters [$];

  // conv responder: answer conv_req after 3 cycles; converge at iteration conv_at (0 = never)
  always @(posedge clk) begin
    if (gamma_start) n_gs++;
    if (gamma_next) n_gn++;
    if (iter_start) n_is++;
    if (step_valid[0]) begin
      if (init[0] && steps_in_iter == 0) init_iters.push_back(iters + 1);
      if (init != {NDUP{init[0]}}) nbad_dup++;
      steps_in_iter++;
    end
    if (conv_req) begin
      iters++; steps_in_iter = 0;
      fork begin
        automatic int c = iters;
        repeat (3) @(posedge clk);
        #1 conv_valid = 1; conv = (conv_at != 0 && c == conv_at);
        @(posedge clk); #1 conv_valid = 0; conv = 0;
      end join_none
    end
  end

  task automatic run_window(input int t, input int c_at, output int nst);
    conv_at = c_at; iters = 0; n_gs = 0; n_gn = 0; n_is = 0; steps_in_iter = 0; init_iters.delete();
    nst = 0;
    @(negedge clk); win_t = RW'(t); start = 1; @(negedge clk); start = 0;
    while (!done || busy) begin
      @(posedge clk); #2;
      if (step_valid[0] && t >= 0 && c_at == 1) begin
        // part A: compare with the expected masks of this window, in order
        automatic int idx = -1;
        automatic int k = 0;
        for (int q = 0; q < ne; q++) if (e_t[q] == t) begin if (k == nst) idx = q; k++; end
        if (idx < 0 || int'(step_g[0]) != e_g[idx]) nbad_seq++;
        else begin
          if (cnu_mask[0] !== e_cm[idx] || vnu_mask_cur[0] !== e_vc[idx] || vnu_mask_prev[0] !== e_vp[idx]
              || int'(prev_active[0]) != e_pa[idx]) begin
            nbad_mask++;
            if (nbad_mask <= 5) $display("MASK MISMATCH t=%0d g=%0d: cnu %h/%h", t, step_g[0], cnu_mask[0], e_cm[idx]);
          end
        end
        for (int d = 1; d < NDUP; d++)
          if (cnu_mask[d] !== cnu_mask[0] || vnu_mask_cur[d] !== vnu_mask_cur[0] || step_g[d] !== step_g[0]) nbad_dup++;
        nst++; nsteps_a++;
      end
    end
  endtask

  int fd, a, b, pa, nst;
  logic [NBASE-1:0] cm; logic [NTYPES*DVMAX-1:0] vc, vp;
  int okB, okC;
  initial begin
    fd = $fopen("vectors/ctrl_expected.txt", "r");
    while ($fscanf(fd, "%d %d %h %h %h %d", a, b, cm, vc, vp, pa) == 6) begin
      e_t[ne] = a; e_g[ne] = b; e_cm[ne] = cm; e_vc[ne] = vc; e_vp[ne] = vp; e_pa[ne] = pa; ne++;
    end
    repeat (2) @(negedge clk); rst = 0;
    // A
    run_window(0, 1, nst);  if (nst != 12) nbad_seq++;
    run_window(8, 1, nst);  if (nst != 12) nbad_seq++;
    run_window(24, 1, nst); if (nst != 12) nbad_seq++;
    run_window(32, 1, nst); if (nst != 5) nbad_seq++;
    // B
    run_window(8, 0, nst);
    okB = (iters == 7) && (iter_total == 7) && !success && done && (n_gs == 1) && (n_gn == 2) && (n_is == 7)
          && (init_iters.size() == 3) && (init_iters[0] == 1) && (init_iters[1] == 4) && (init_iters[2] == 6);
    $display("B: iterations %0d, iter_total %0d, success %0d, gamma_start %0d, gamma_next %0d, iter_start %0d, init in iterations %p",
             iters, iter_total, success, n_gs, n_gn, n_is, init_iters);
    // C
    run_window(8, 5, nst);
    okC = (iters == 5) && (iter_total == 5) && success && done;
    $display("C: iterations %0d, iter_total %0d, success %0d", iters, iter_total, success);
    $display("tb_ctrl: A: steps checked %0d (expected lines %0d), mask mismatches %0d, sequence errors %0d, duplicate-copy mismatches %0d; B %s; C %s",
             nsteps_a, ne, nbad_mask, nbad_seq, nbad_dup, okB ? "ok" : "FAIL", okC ? "ok" : "FAIL");
    $display("%s", (nsteps_a == ne && nbad_mask == 0 && nbad_seq == 0 && nbad_dup == 0 && okB && okC) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
