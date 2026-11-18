// Review fixes, part B.1: the 720 gamma lanes of engine_top_rb in LFSR mode (unchanged gamma_src.sv, the engine's
// per-lane seeds), reset once, then one draw per cycle (next = 1). After every draw the g8 of all lanes is written as
// one line of 720 hex digits (4-bit two's complement, lane = t * 72 + p). Compared with lfsr_model.table() by
// lfsr_check.py.   Plusargs: +NDRAWS=<n> (default 10000), +OUT=<file> (default lfsr_rtl.txt)
`timescale 1ns/1ps
module tb_gamma_lfsr;
  localparam int NT = 10, NP = 72, NL = NT * NP;
  logic clk = 0, rst = 1, next = 0;
  logic signed [3:0] g8 [NL];
  for (genvar t = 0; t < NT; t++) begin : g_t
    for (genvar p = 0; p < NP; p++) begin : g_p
      /* verilator lint_off PINCONNECTEMPTY */
      gamma_src #(.LFSR_MODE(1'b1), .SEED(16'(((t * NP + p) + 1) * 16'h9E37))) u_g (
        .clk, .rst, .start(1'b0), .next(next), .load(1'b0), .load_g8('0), .g8(g8[t * NP + p]), .state());
      /* verilator lint_on PINCONNECTEMPTY */
    end
  end
  always #1 clk = ~clk;
  int nd, fd; string fn;
  initial begin
    if (!$value$plusargs("NDRAWS=%d", nd)) nd = 10000;
    if (!$value$plusargs("OUT=%s", fn)) fn = "lfsr_rtl.txt";
    fd = $fopen(fn, "w");
    @(posedge clk); @(posedge clk); @(negedge clk); rst = 0; next = 1;   // change inputs away from the clock edge
    for (int d = 0; d < nd; d++) begin
      @(posedge clk); #0.5;
      for (int l = 0; l < NL; l++) $fwrite(fd, "%1h", g8[l]);
      $fwrite(fd, "\n");
    end
    $fclose(fd);
    $display("tb_gamma_lfsr: %0d draws x %0d lanes written to %s", nd, NL, fn);
    $finish;
  end
endmodule
