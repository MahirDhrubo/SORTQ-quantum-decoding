// rot2d.sv — two-stage cyclic rotator over Z_A x Z_B (A = 12, B = 6), W-bit payload per position.
// Position index p = a * B + b. Read rotation by shift (sa, sb):  out[(a, b)] = in[((a + sa) mod A, (b + sb) mod B)]
// i.e. lane x reads the error at x + s (the Test 1c convention "the rotator reads the error at x + s").
// Stage 1 rotates inside each of the A groups of B (by sb), stage 2 rotates the groups (by sa).
// Each stage is a barrel of log2 steps (shift by 1, 2, 4, ... with wrap-around); PIPE = 1 registers between and
// after the stages (latency 2), PIPE = 0 is combinational. For design-space configurations with fewer than
// A * B lanes this block is the shared shuffle; with 72 lanes and hard-wired shifts it is not needed.
module rot2d #(
  parameter int W    = 8,
  parameter int A    = 12,
  parameter int B    = 6,
  parameter bit PIPE = 1'b1,
  localparam int AW  = $clog2(A),
  localparam int BW  = $clog2(B)
) (
  input  logic                    clk,
  input  logic [AW-1:0]           sa,       // 0 .. A-1
  input  logic [BW-1:0]           sb,       // 0 .. B-1
  input  logic [A*B-1:0][W-1:0]   din,
  output logic [A*B-1:0][W-1:0]   dout
);
  logic [A*B-1:0][W-1:0] s1_c, s1_q, s2_c;
  logic [AW-1:0] sa_q;

  // stage 1: within each group, rotate by sb (barrel: bit k rotates by 2^k mod B)
  always_comb begin
    logic [A*B-1:0][W-1:0] t, g;
    t = din;
    for (int k = 0; k < BW; k++) begin
      for (int a = 0; a < A; a++)
        for (int b = 0; b < B; b++) g[a*B + b] = t[a*B + ((b + (1 << k)) % B)];
      if (sb[k]) t = g;
    end
    s1_c = t;
  end

  if (PIPE) begin : g_p1
    always_ff @(posedge clk) begin s1_q <= s1_c; sa_q <= sa; end
  end else begin : g_c1
    always_comb begin s1_q = s1_c; sa_q = sa; end
  end

  // stage 2: rotate the groups by sa
  always_comb begin
    logic [A*B-1:0][W-1:0] t, g;
    t = s1_q;
    for (int k = 0; k < AW; k++) begin
      for (int a = 0; a < A; a++)
        for (int b = 0; b < B; b++) g[a*B + b] = t[((a + (1 << k)) % A)*B + b];
      if (sa_q[k]) t = g;
    end
    s2_c = t;
  end

  if (PIPE) begin : g_p2
    always_ff @(posedge clk) dout <= s2_c;
  end else begin : g_c2
    assign dout = s2_c;
  end
endmodule
