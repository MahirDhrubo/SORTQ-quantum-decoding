// tb_cnu.sv — replay the golden check-node vectors (vectors/cnu_vectors.txt, from golden/check_and_vectors.py).
// Line: syn mask[35] in_sign[35] in_mag[35] out_sign[35] out_mag[35]   (invalid slots hold random junk inputs)
// Every output (sign and magnitude of all valid edges, and 0 on masked edges) must match bit-exactly.
// Also checks min1/min2/parity against values recomputed here from the vector.
`timescale 1ns/1ps
module tb_cnu;
  parameter int N = 4;
  parameter int DEG = 35;
  parameter bit OUT_REG = 1'b1;
  parameter string VEC = "vectors/cnu_vectors.txt";
  localparam int IW = $clog2(DEG);

  logic clk = 0, in_valid = 0, syn = 0, out_valid, parity;
  logic [DEG-1:0] mask = '0, in_sign = '0, out_sign, exp_sign;
  logic [DEG-1:0][N-1:0] in_mag = '0, out_mag, exp_mag;
  logic [N-1:0] min1, min2;
  logic [IW-1:0] min1_idx;

  cnu #(.N(N), .DEG(DEG), .OUT_REG(OUT_REG)) dut (.*);

  always #5 clk = ~clk;

  int fd, r, v, nvec = 0, nbad = 0, nedge = 0, nbad_edge = 0, nbad_min = 0;
  int m1, m2, cnt_m1;
  initial begin
    fd = $fopen(VEC, "r");
    if (fd == 0) begin $display("FAIL: cannot open %s", VEC); $finish; end
    @(negedge clk);
    while (1) begin
      r = $fscanf(fd, "%d", v);
      if (r != 1) break;
      syn = v[0];
      for (int e = 0; e < DEG; e++) begin r = $fscanf(fd, "%d", v); mask[e] = v[0]; end
      for (int e = 0; e < DEG; e++) begin r = $fscanf(fd, "%d", v); in_sign[e] = v[0]; end
      for (int e = 0; e < DEG; e++) begin r = $fscanf(fd, "%d", v); in_mag[e] = N'(v); end
      for (int e = 0; e < DEG; e++) begin r = $fscanf(fd, "%d", v); exp_sign[e] = v[0]; end
      for (int e = 0; e < DEG; e++) begin r = $fscanf(fd, "%d", v); exp_mag[e] = N'(v); end
      in_valid = 1;
      // reference min1 / min2 over valid edges (MAX if absent)
      m1 = (1 << N) - 1; m2 = (1 << N) - 1; cnt_m1 = 0;
      for (int e = 0; e < DEG; e++) if (mask[e]) begin
        if (int'(in_mag[e]) < m1) begin m2 = m1; m1 = int'(in_mag[e]); end
        else if (int'(in_mag[e]) < m2) m2 = int'(in_mag[e]);
      end
      if (OUT_REG) @(posedge clk);
      #1;
      nvec++;
      begin
        automatic int bad = 0;
        for (int e = 0; e < DEG; e++) begin
          if (mask[e]) nedge++;
          if (out_sign[e] !== exp_sign[e] || out_mag[e] !== exp_mag[e]) begin bad++; nbad_edge++; end
        end
        if (int'(min1) != m1 || int'(min2) != m2 || !out_valid) nbad_min++;
        if (bad) begin
          nbad++;
          if (nbad <= 5) $display("MISMATCH vector %0d: %0d edges", nvec, bad);
        end
      end
      @(negedge clk);
    end
    $display("tb_cnu N=%0d DEG=%0d OUT_REG=%0d: vectors %0d, valid edges %0d, mismatching vectors %0d, mismatching edges %0d, min1/min2 mismatches %0d",
             N, DEG, OUT_REG, nvec, nedge, nbad, nbad_edge, nbad_min);
    $display("%s", (nbad == 0 && nbad_min == 0 && nvec > 0) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
