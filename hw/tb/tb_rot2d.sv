// tb_rot2d.sv — exhaustive over all 72 shifts (sa 0..11, sb 0..5), 20 random payload sets each (W = 8 bits),
// plus a unique-ID payload (lane index) for each shift. Reference: out[(a,b)] = in[((a+sa)%12, (b+sb)%6)].
`timescale 1ns/1ps
module tb_rot2d;
  parameter bit PIPE = 1'b1;
  localparam int A = 12, B = 6, W = 8;
  logic clk = 0;
  logic [3:0] sa = '0;
  logic [2:0] sb = '0;
  logic [A*B-1:0][W-1:0] din = '0, dout, want;
  always #5 clk = ~clk;
  rot2d #(.W(W), .A(A), .B(B), .PIPE(PIPE)) dut (.*);

  int ntests = 0, nbad = 0, nlanes_bad = 0;
  initial begin
    @(negedge clk);
    for (int s_a = 0; s_a < A; s_a++)
      for (int s_b = 0; s_b < B; s_b++)
        for (int rep = 0; rep <= 20; rep++) begin
          sa = 4'(s_a); sb = 3'(s_b);
          for (int p = 0; p < A*B; p++) din[p] = (rep == 0) ? W'(p) : W'($urandom);
          for (int a = 0; a < A; a++)
            for (int b = 0; b < B; b++) want[a*B + b] = din[((a + s_a) % A)*B + (b + s_b) % B];
          if (PIPE) begin @(posedge clk); @(posedge clk); end
          #1;
          ntests++;
          begin
            automatic int bad = 0;
            for (int p = 0; p < A*B; p++) if (dout[p] !== want[p]) bad++;
            nlanes_bad += bad;
            if (bad) begin nbad++; if (nbad <= 5) $display("MISMATCH shift (%0d,%0d) rep %0d: %0d lanes", s_a, s_b, rep, bad); end
          end
          @(negedge clk);
        end
    $display("tb_rot2d PIPE=%0d: shifts 72, tests %0d (72 x 21), mismatching tests %0d, mismatching lanes %0d",
             PIPE, ntests, nbad, nlanes_bad);
    $display("%s", (nbad == 0 && ntests == 72 * 21) ? "PASS" : "FAIL");
    $finish;
  end
endmodule
