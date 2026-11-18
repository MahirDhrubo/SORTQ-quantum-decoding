// tb_gamma_src.sv — gamma_src in both modes.
//  LOAD: 10,000 random loads (values -8..7), g8 must follow load_g8; start/next must not change it.
//  LFSR: rst -> start: g8 = G0 = 1. Then 65,535 `next` draws = one full period of the leap-16 LFSR, so every
//        non-zero 16-bit state appears exactly once and the low 12 bits take each value 16 times (0: 15 times).
//        Exact expected counts per g8 bin: 16 * width (minus 1 for the bin holding 0):
//        -2: 2991, -1..4: 9664 each, 5: 4560. Also: the state returns to SEED after exactly 65,535 draws, not earlier.
`timescale 1ns/1ps
module tb_gamma_src;
  logic clk = 0, rst = 1, start = 0, next = 0, load = 0;
  logic signed [3:0] load_g8 = '0, g8_l, g8_f;
  logic [15:0] st_l, st_f;
  always #5 clk = ~clk;

  gamma_src #(.LFSR_MODE(1'b0)) u_load (.clk, .rst, .start, .next, .load, .load_g8, .g8(g8_l), .state(st_l));
  gamma_src #(.LFSR_MODE(1'b1), .SEED(16'hACE1)) u_lfsr (.clk, .rst, .start, .next, .load(1'b0), .load_g8(4'sd0),
                                                       .g8(g8_f), .state(st_f));
  int nbad_load = 0, nbad_lfsr = 0, hist [8], early = 0, period_ok;
  int exp_cnt [8] = '{2991, 9664, 9664, 9664, 9664, 9664, 9664, 4560};
  initial begin
    for (int b = 0; b < 8; b++) hist[b] = 0;
    @(negedge clk); @(negedge clk); rst = 0;
    // LOAD mode
    for (int i = 0; i < 10000; i++) begin
      load_g8 = 4'($urandom_range(0, 15)); load = ($urandom_range(0, 3) != 0);
      start = ($urandom_range(0, 7) == 0); next = ($urandom_range(0, 7) == 0);
      begin
        automatic logic signed [3:0] prev_g8 = g8_l;
        automatic logic signed [3:0] want = load ? load_g8 : prev_g8;
        @(posedge clk); #1;
        if (g8_l !== want) nbad_load++;
      end
      @(negedge clk);
    end
    load = 0; start = 0; next = 0;
    // LFSR mode
    rst = 1; @(negedge clk); rst = 0; start = 1; @(negedge clk); start = 0;
    if (g8_f !== 4'sd1) begin nbad_lfsr++; $display("start: g8 = %0d (expected 1)", g8_f); end
    for (int i = 1; i <= 65535; i++) begin
      next = 1; @(posedge clk); #1;
      if (g8_f < -2 || g8_f > 5) nbad_lfsr++; else hist[int'(g8_f) + 2]++;
      if (i < 65535 && st_f == 16'hACE1) early++;
      if (i == 65535) period_ok = (st_f == 16'hACE1);
      @(negedge clk);
    end
    next = 0;
    for (int b = 0; b < 8; b++) begin
      $display("g8 = %0d: %0d draws (expected %0d), %.3f%%", b - 2, hist[b], exp_cnt[b], 100.0 * hist[b] / 65535.0);
      if (hist[b] != exp_cnt[b]) nbad_lfsr++;
    end
    $display("tb_gamma_src: LOAD mismatches %0d / 10000; LFSR: out-of-set %0d, period 65535 %s, early returns %0d",
             nbad_load, nbad_lfsr, period_ok ? "yes" : "NO", early);
    $display("%s", (nbad_load == 0 && nbad_lfsr == 0 && period_ok && early == 0) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
