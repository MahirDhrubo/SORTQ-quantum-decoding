// gamma_src.sv — per-error-node memory strength g8 (Mem-BP), one value per relay leg.
//   LFSR_MODE = 0 (LOAD): g8 <= load_g8 when `load` (testbench / bit-exact replay).
//   LFSR_MODE = 1 (LFSR): `start` (decode start, leg 0) sets g8 = G0 (= round(8 * gamma0) = 1);
//                          `next` (new leg) draws a new g8 from a 16-bit Galois LFSR (x^16+x^14+x^13+x^11+1),
//                          advanced 16 steps per draw (full period 65,535 draws), mapped by thresholds on its
//                          low RB = 12 bits onto the golden g8 set {-2..5} with the golden probabilities
//                          (ARITHMETIC.md section 6): counts per 4096 = 187, 604 x 6, 285.
// The LFSR draws are NOT the golden draws (golden = Rust StdRng); only the set and the distribution match.
module gamma_src #(
  parameter bit          LFSR_MODE = 1'b1,
  parameter int          GW        = 4,
  parameter logic [15:0] SEED      = 16'hACE1,       // must be non-zero; give every node its own seed
  parameter int          G0        = 1,
  parameter int          GMIN      = -2,             // g8 of the first bin
  parameter int          NBINS     = 8,
  parameter int          RB        = 12,
  // cumulative upper bounds (exclusive) of the bins, over 2^RB
  parameter int          CUM [NBINS] = '{187, 791, 1395, 1999, 2603, 3207, 3811, 4096}
) (
  input  logic                  clk,
  input  logic                  rst,       // synchronous; reloads SEED and G0
  input  logic                  start,
  input  logic                  next,
  input  logic                  load,
  input  logic signed [GW-1:0]  load_g8,
  output logic signed [GW-1:0]  g8,
  output logic [15:0]           state      // exposed for the testbench (period / distribution checks)
);
  localparam logic [15:0] TAPS = 16'hB400;

  function automatic logic [15:0] leap16(input logic [15:0] s);
    logic [15:0] x = s;
    for (int i = 0; i < 16; i++) x = x[0] ? ((x >> 1) ^ TAPS) : (x >> 1);
    return x;
  endfunction

  function automatic logic signed [GW-1:0] map(input logic [RB-1:0] u);
    logic signed [GW-1:0] r = GW'(GMIN + NBINS - 1);
    for (int b = NBINS - 1; b >= 0; b--) if (int'(u) < CUM[b]) r = GW'(GMIN + b);
    return r;
  endfunction

  logic [15:0] nxt;
  assign nxt = leap16(state);

  always_ff @(posedge clk) begin
    if (rst) begin
      state <= SEED; g8 <= GW'(G0);
    end else if (!LFSR_MODE) begin
      if (load) g8 <= load_g8;
    end else if (start) begin
      g8 <= GW'(G0);
    end else if (next) begin
      state <= nxt; g8 <= map(nxt[RB-1:0]);
    end
  end
endmodule
