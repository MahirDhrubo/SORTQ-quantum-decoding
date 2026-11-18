// tb_conv_check.sv — conv_check (W = 12) against a software parity check on the 36-round matrix
// (vectors/conv_vectors.txt from gen_vectors_step3.py): windows t = 0, 8, 24, 32; random hard decisions, syndromes
// consistent (conv = 1) or with 1-3 flipped detectors (conv = 0); edge masks from H.
// Checks conv and the full 864-bit unsatisfied-detector vector; measures the latency in cycles.
`timescale 1ns/1ps
module tb_conv_check;
  import round_wiring_pkg::*;
  localparam int W = 12;
  logic clk = 0, in_valid = 0, out_valid, conv;
  logic [W-1:0][NTYPES-1:0][NPOS-1:0] hard;
  logic [W-1:0][NPOS-1:0] syn, unsat;
  logic [W-1:0][NBASE-1:0] emask;
  logic [W*NTYPES*NPOS-1:0] h_f;
  logic [W*NPOS-1:0] s_f, u_f;
  logic [W*NBASE-1:0] m_f;
  always #5 clk = ~clk;
  conv_check #(.W(W)) dut (.*);

  int fd, t, ec, n = 0, nbad_c = 0, nbad_u = 0, ncv = 0, lat, lat_seen = -1;
  initial begin
    fd = $fopen("vectors/conv_vectors.txt", "r");
    if (fd == 0) begin $display("FAIL: no vectors"); $finish; end
    @(negedge clk);
    while ($fscanf(fd, "%d %h %h %h %d %h", t, h_f, s_f, m_f, ec, u_f) == 6) begin
      hard = h_f; syn = s_f; emask = m_f; in_valid = 1;
      lat = 0;
      @(posedge clk); #1; in_valid = 0;
      lat = 1;
      if (unsat !== u_f) nbad_u++;
      while (!out_valid) begin @(posedge clk); #1; lat++; end
      if (lat_seen < 0) lat_seen = lat; else if (lat != lat_seen) nbad_c++;
      if (conv !== ec[0]) nbad_c++;
      if (ec) ncv++;
      n++;
      @(negedge clk);
    end
    $display("tb_conv_check W=%0d: vectors %0d (converged %0d), conv mismatches %0d, unsat-vector mismatches %0d, latency %0d cycles",
             W, n, ncv, nbad_c, nbad_u, lat_seen);
    $display("%s", (n == 400 && nbad_c == 0 && nbad_u == 0) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
