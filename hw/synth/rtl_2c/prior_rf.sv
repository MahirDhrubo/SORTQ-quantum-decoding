// prior_rf.sv — Test 2c: the prior register file of round_step.sv as a standalone block (same code), for synthesis
// on its own. NRND home rounds x NTYPES priors (N + 1 bits, two's complement), load port, read by round_idx:
// cur = row round_idx, prev = row round_idx - 1 (0 for round 0), broadcast to the 72 positions.
module prior_rf
  import round_wiring_pkg::*;
#(
  parameter int N    = 4,
  parameter int NRND = 13,
  localparam int MW = N + 1, RW = $clog2(NRND), TW = $clog2(NTYPES)
) (
  input  logic                              clk,
  input  logic                              pr_we,
  input  logic [RW-1:0]                     pr_wround,
  input  logic [TW-1:0]                     pr_wtype,
  input  logic [MW-1:0]                     pr_wdata,
  input  logic [RW-1:0]                     round_idx,
  output logic [NTYPES-1:0][NPOS-1:0][MW-1:0] prior_cur,
  output logic [NTYPES-1:0][NPOS-1:0][MW-1:0] prior_prev
);
  logic [NTYPES-1:0][MW-1:0] prf [NRND];
  always_ff @(posedge clk) if (pr_we) prf[pr_wround][pr_wtype] <= pr_wdata;
  logic [NTYPES-1:0][MW-1:0] c, p;
  assign c = prf[round_idx];
  assign p = (round_idx == '0) ? '0 : prf[round_idx - RW'(1)];
  for (genvar t = 0; t < NTYPES; t++) begin : g_t
    for (genvar x = 0; x < NPOS; x++) begin : g_x
      assign prior_cur[t][x] = c[t]; assign prior_prev[t][x] = p[t];
    end
  end
endmodule
