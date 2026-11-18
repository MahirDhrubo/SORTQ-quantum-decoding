// tb_ctrl_pf.sv — ctrl_pf (convergence check overlapped with the next iteration, Test 2c timing variant) against
// ctrl (verified in Test 2a), cycle by cycle on the same decodes.
// Each controller gets its own convergence model: conv_valid LATC cycles after its conv_req, with
// conv = (number of this check == CONV_AT) (the decoder's result depends only on the iteration, so both controllers
// see the same result for the same iteration; CONV_AT = 0: never converges).
// Checks per decode:
//   - done, success, iter_total, leg at done identical;
//   - gamma_start / gamma_next pulse counts identical;
//   - step sequence (g, init, cnu_mask, vnu masks, prev_active) of ctrl_pf = ctrl's sequence, plus at most one
//     partial iteration of extra (speculative, discarded) steps at the end, only when the decode converged; the
//     extra steps never have init = 1;
//   - at most one check in flight (no conv_req while a result is outstanding).
// Sweep: windows (win_t, last_r) with 12, 5 and 2 rounds; CONV_AT = 0 .. 16 (every iteration of a decode with
// PRE_IT = 3, LEG_IT = 4, NLEGS = 3, incl. the leg ends); LATC in {3, 7, 12, 40}. Parameter STEP_CYCLES (2 / 3).
// Also reports the decode cycles of both controllers (start -> done).
`timescale 1ns/1ps
module tb_ctrl_pf #(parameter int STEP_CYCLES = 2);
  import round_wiring_pkg::*;
  localparam int W = 12, RW = 8, PRE_IT = 3, LEG_IT = 4, NLEGS = 3;
  logic clk = 0, rst = 1, start = 0;
  logic [RW-1:0] win_t, last_r;
  always #5 clk = ~clk;

  // per-controller signals: index 0 = ctrl, 1 = ctrl_pf
  logic cv [2], cn [2], busy [2], done [2], success [2], gs [2], gn [2], is [2], creq [2];
  logic [15:0] itot [2]; logic [8:0] leg [2];
  logic [0:0] sv [2], ini [2], pa [2];
  logic [0:0][RW-1:0] sg [2];
  logic [0:0][NBASE-1:0] cm [2];
  logic [0:0][NTYPES-1:0][DVMAX-1:0] vc [2], vp [2];

  ctrl #(.W(W), .STEP_CYCLES(STEP_CYCLES), .PRE_IT(PRE_IT), .LEG_IT(LEG_IT), .NLEGS(NLEGS), .NDUP(1), .RW(RW)) u_ref (
    .clk, .rst, .start, .win_t, .last_r, .conv_valid(cv[0]), .conv(cn[0]), .busy(busy[0]), .done(done[0]),
    .success(success[0]), .iter_total(itot[0]), .leg(leg[0]), .gamma_start(gs[0]), .gamma_next(gn[0]),
    .iter_start(is[0]), .conv_req(creq[0]), .step_valid(sv[0]), .init(ini[0]), .step_g(sg[0]), .cnu_mask(cm[0]),
    .vnu_mask_cur(vc[0]), .vnu_mask_prev(vp[0]), .prev_active(pa[0]));
  ctrl_pf #(.W(W), .STEP_CYCLES(STEP_CYCLES), .PRE_IT(PRE_IT), .LEG_IT(LEG_IT), .NLEGS(NLEGS), .NDUP(1), .RW(RW)) u_pf (
    .clk, .rst, .start, .win_t, .last_r, .conv_valid(cv[1]), .conv(cn[1]), .busy(busy[1]), .done(done[1]),
    .success(success[1]), .iter_total(itot[1]), .leg(leg[1]), .gamma_start(gs[1]), .gamma_next(gn[1]),
    .iter_start(is[1]), .conv_req(creq[1]), .step_valid(sv[1]), .init(ini[1]), .step_g(sg[1]), .cnu_mask(cm[1]),
    .vnu_mask_cur(vc[1]), .vnu_mask_prev(vp[1]), .prev_active(pa[1]));

  typedef struct packed {
    logic [RW-1:0] g; logic init; logic [NBASE-1:0] cm; logic [NTYPES-1:0][DVMAX-1:0] vc, vp; logic pa;
  } step_t;
  step_t steps [2][$];
  int latc, conv_at, cnt [2], nchk [2], ngs [2], ngn [2], ncyc [2], overlap_err [2];
  logic run;

  // convergence models + recording
  for (genvar c = 0; c < 2; c++) begin : g_m
    always_ff @(posedge clk) begin
      cv[c] <= 1'b0; cn[c] <= 1'b0;
      if (run) begin
        if (!done[c]) ncyc[c] <= ncyc[c] + 1;
        if (sv[c][0]) steps[c].push_back('{g: sg[c][0], init: ini[c][0], cm: cm[c][0], vc: vc[c][0], vp: vp[c][0],
                                            pa: pa[c][0]});
        if (gs[c]) ngs[c] <= ngs[c] + 1;
        if (gn[c]) ngn[c] <= ngn[c] + 1;
        if (creq[c]) begin
          if (cnt[c] != 0) overlap_err[c] <= overlap_err[c] + 1;
          cnt[c] <= latc;
        end else if (cnt[c] == 1) begin
          cnt[c] <= 0; cv[c] <= 1'b1; cn[c] <= (nchk[c] + 1 == conv_at); nchk[c] <= nchk[c] + 1;
        end else if (cnt[c] > 1) cnt[c] <= cnt[c] - 1;
      end
    end
  end

  int ndec = 0, nbad = 0, nspec = 0, nspec_dec = 0;
  longint cyc_ref = 0, cyc_pf = 0;
  int wins [3][2] = '{'{0, 12}, '{8, 12}, '{11, 12}};
  int lats [4] = '{3, 7, 12, 40};
  initial begin
    repeat (3) @(negedge clk); rst = 0; run = 0;
    foreach (wins[wi]) foreach (lats[li]) for (int ca = 0; ca <= 16; ca++) begin
      win_t = RW'(wins[wi][0]); last_r = RW'(wins[wi][1]); latc = lats[li]; conv_at = ca;
      for (int c = 0; c < 2; c++) begin
        steps[c].delete(); cnt[c] = 0; nchk[c] = 0; ngs[c] = 0; ngn[c] = 0; ncyc[c] = 0; overlap_err[c] = 0;
      end
      run = 1; start = 1; @(negedge clk); start = 0;
      begin
        int guard = 0;
        while (!(done[0] && done[1]) && guard < 100000) begin @(negedge clk); guard++; end
        repeat (60) @(negedge clk);                    // let the discarded steps / late results drain
      end
      run = 0;
      begin
        automatic int bad = 0, nr = steps[0].size(), nf = steps[1].size();
        automatic int nrounds = (wins[wi][0] + W - 1 < wins[wi][1]) ? W : wins[wi][1] - wins[wi][0] + 1;
        if (!done[0] || !done[1]) bad++;
        if (success[0] !== success[1] || itot[0] !== itot[1] || leg[0] !== leg[1]) bad++;
        if (ngs[0] != ngs[1] || ngn[0] != ngn[1]) bad++;
        if (overlap_err[0] || overlap_err[1]) bad++;
        if (nf < nr) bad++;
        else begin
          for (int i = 0; i < nr; i++) if (steps[0][i] !== steps[1][i]) bad++;
          if (nf > nr) begin
            nspec_dec++; nspec += nf - nr;
            if (!success[1] || nf - nr > nrounds) bad++;
            for (int i = nr; i < nf; i++) if (steps[1][i].init) bad++;
          end
        end
        if (bad) begin
          nbad++;
          if (nbad <= 5) $display("MISMATCH win %0d..%0d latc %0d conv_at %0d: ref steps %0d pf steps %0d, success %0d/%0d, iter %0d/%0d, leg %0d/%0d (%0d)",
                                  wins[wi][0], wins[wi][1], latc, ca, nr, nf, success[0], success[1], itot[0], itot[1], leg[0], leg[1], bad);
        end
        cyc_ref += ncyc[0]; cyc_pf += ncyc[1];
        ndec++;
      end
    end
    $display("tb_ctrl_pf STEP_CYCLES=%0d: decodes %0d, mismatching %0d, decodes with discarded speculative steps %0d (steps %0d), decode cycles ref %0d / pf %0d",
             STEP_CYCLES, ndec, nbad, nspec_dec, nspec, cyc_ref, cyc_pf);
    $display("%s", (ndec > 0 && nbad == 0) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
