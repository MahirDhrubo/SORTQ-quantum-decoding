// tb_vnu.sv — replay the golden error-node vectors (vectors/vnu_vectors.txt, from golden/check_and_vectors.py).
// Line: init prior g8 mpost mask[6] late[6] c2v_stored[6] | bias marg hard v2c_out[6]
// c2v_stored = what the hardware message memory holds (previous-leg values at a leg start); the VNU must gate the
// stale ones (init & late) to 0. Masked slots carry random junk. All outputs must match bit-exactly.
`timescale 1ns/1ps
module tb_vnu;
  parameter int N = 4;
  parameter int DV = 6;
  parameter bit OUT_REG = 1'b1;
  parameter string VEC = "vectors/vnu_vectors.txt";
  localparam int MB = N + 3;

  logic clk = 0, in_valid = 0, init = 0, out_valid, hard;
  logic [DV-1:0] mask = '0, late = '0, c2v_sign = '0, v2c_sign;
  logic [DV-1:0][N-1:0] c2v_mag = '0, v2c_mag;
  logic signed [N:0] prior = '0;
  logic signed [3:0] g8 = '0;
  logic signed [MB-1:0] mpost = '0, bias, marg;
  int e_bias, e_marg, e_hard, e_v [DV];

  vnu #(.N(N), .DV(DV), .OUT_REG(OUT_REG)) dut (.*);

  always #5 clk = ~clk;

  int fd, r, v, nvec = 0, nbad = 0, ninit = 0, nlate_gated = 0;
  int nb_bias = 0, nb_marg = 0, nb_hard = 0, nb_v2c = 0;
  initial begin
    fd = $fopen(VEC, "r");
    if (fd == 0) begin $display("FAIL: cannot open %s", VEC); $finish; end
    @(negedge clk);
    while (1) begin
      r = $fscanf(fd, "%d", v);
      if (r != 1) break;
      init = v[0];
      r = $fscanf(fd, "%d", v); prior = (N+1)'(v);
      r = $fscanf(fd, "%d", v); g8 = 4'(v);
      r = $fscanf(fd, "%d", v); mpost = MB'(v);
      for (int e = 0; e < DV; e++) begin r = $fscanf(fd, "%d", v); mask[e] = v[0]; end
      for (int e = 0; e < DV; e++) begin r = $fscanf(fd, "%d", v); late[e] = v[0]; end
      for (int e = 0; e < DV; e++) begin
        r = $fscanf(fd, "%d", v); c2v_sign[e] = (v < 0); c2v_mag[e] = N'((v < 0) ? -v : v);
      end
      r = $fscanf(fd, "%d", e_bias); r = $fscanf(fd, "%d", e_marg); r = $fscanf(fd, "%d", e_hard);
      for (int e = 0; e < DV; e++) r = $fscanf(fd, "%d", e_v[e]);
      in_valid = 1;
      if (init) ninit++;
      for (int e = 0; e < DV; e++) if (init && late[e] && mask[e]) nlate_gated++;
      if (OUT_REG) @(posedge clk);
      #1;
      nvec++;
      begin
        automatic int bad = 0;
        if (int'(bias) != e_bias) begin bad++; nb_bias++; end
        if (int'(marg) != e_marg) begin bad++; nb_marg++; end
        if (int'(hard) != e_hard) begin bad++; nb_hard++; end
        for (int e = 0; e < DV; e++) begin
          automatic int got = v2c_sign[e] ? -int'(v2c_mag[e]) : int'(v2c_mag[e]);
          if (got != e_v[e] || (v2c_sign[e] && v2c_mag[e] == 0)) begin bad++; nb_v2c++; end
        end
        if (!out_valid) bad++;
        if (bad) begin nbad++; if (nbad <= 5) $display("MISMATCH vector %0d (%0d fields)", nvec, bad); end
      end
      @(negedge clk);
    end
    $display("tb_vnu N=%0d DV=%0d OUT_REG=%0d: vectors %0d (init %0d, gated stale edges %0d), mismatching vectors %0d [bias %0d, marg %0d, hard %0d, v2c %0d]",
             N, DV, OUT_REG, nvec, ninit, nlate_gated, nbad, nb_bias, nb_marg, nb_hard, nb_v2c);
    $display("%s", (nbad == 0 && nvec > 0) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
