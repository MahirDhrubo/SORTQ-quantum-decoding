// tb_round_wiring.sv — connectivity of the generated round_wiring against the parity-check matrix H.
// Expected edges (vectors/round_wiring_expected.txt, written by gen/labels.py from H of round 5, independent of the
// generator): "x k o idx p" = check x, base edge k <-> error-side bus o (0/1), edge index idx, position p.
// Forward: every error-side slot carries a unique ID {ck, o, idx, p}; cnu_in[ck][x][k] must equal the expected ID.
// Backward: every CNU output carries {ck, x, k}; c2v_o<o>[ck][idx][p] must equal it.
// Also: every one of the 72 x 35 CNU inputs and every error-side slot is driven by exactly one edge (counts).
`timescale 1ns/1ps
module tb_round_wiring;
  import round_wiring_pkg::*;
  parameter int K_ROUNDS = 1;
  parameter string EXP = "vectors/round_wiring_expected.txt";
  localparam int W = 14;
  logic [K_ROUNDS-1:0][NE0-1:0][NPOS-1:0][W-1:0]   v2c_o0, c2v_o0;
  logic [K_ROUNDS-1:0][NE1-1:0][NPOS-1:0][W-1:0]   v2c_o1, c2v_o1;
  logic [K_ROUNDS-1:0][NPOS-1:0][NBASE-1:0][W-1:0] cnu_in, cnu_out;
  round_wiring #(.W(W), .K_ROUNDS(K_ROUNDS)) dut (.*);

  int fd, r, x, k, o, idx, p, n = 0, nbad_f = 0, nbad_b = 0;
  int seen_in [NPOS][NBASE];
  int seen_e0 [NE0][NPOS];
  int seen_e1 [NE1][NPOS];
  int ncover_bad = 0;
  initial begin
    for (int ck = 0; ck < K_ROUNDS; ck++) begin
      for (int i = 0; i < NE0; i++) for (int q = 0; q < NPOS; q++) v2c_o0[ck][i][q] = W'({ck[0], 1'b0, 5'(i), 7'(q)});
      for (int i = 0; i < NE1; i++) for (int q = 0; q < NPOS; q++) v2c_o1[ck][i][q] = W'({ck[0], 1'b1, 5'(i), 7'(q)});
      for (int q = 0; q < NPOS; q++) for (int b = 0; b < NBASE; b++) cnu_out[ck][q][b] = W'({ck[0], 7'(q), 6'(b)});
    end
    foreach (seen_in[i, j]) seen_in[i][j] = 0;
    foreach (seen_e0[i, j]) seen_e0[i][j] = 0;
    foreach (seen_e1[i, j]) seen_e1[i][j] = 0;
    #1;
    fd = $fopen(EXP, "r");
    if (fd == 0) begin $display("FAIL: cannot open %s", EXP); $finish; end
    while ($fscanf(fd, "%d %d %d %d %d", x, k, o, idx, p) == 5) begin
      n++;
      seen_in[x][k]++;
      if (o == 0) seen_e0[idx][p]++; else seen_e1[idx][p]++;
      for (int ck = 0; ck < K_ROUNDS; ck++) begin
        if (cnu_in[ck][x][k] !== W'({ck[0], o[0], 5'(idx), 7'(p)})) nbad_f++;
        if ((o == 0 ? c2v_o0[ck][idx][p] : c2v_o1[ck][idx][p]) !== W'({ck[0], 7'(x), 6'(k)})) nbad_b++;
      end
    end
    foreach (seen_in[i, j]) if (seen_in[i][j] != 1) ncover_bad++;
    foreach (seen_e0[i, j]) if (seen_e0[i][j] != 1) ncover_bad++;
    foreach (seen_e1[i, j]) if (seen_e1[i][j] != 1) ncover_bad++;
    $display("tb_round_wiring K_ROUNDS=%0d: expected edges %0d (x %0d rounds), forward mismatches %0d, backward mismatches %0d, coverage errors %0d",
             K_ROUNDS, n, K_ROUNDS, nbad_f, nbad_b, ncover_bad);
    $display("%s", (n == NPOS * NBASE && nbad_f == 0 && nbad_b == 0 && ncover_bad == 0) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
