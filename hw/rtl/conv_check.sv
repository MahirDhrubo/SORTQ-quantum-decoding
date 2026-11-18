// conv_check.sv — convergence check over a whole window of W rounds (W12: 864 detectors), pipelined.
//   unsat[i][x] = syn[i][x] XOR (XOR over base edges k with emask[i][k] of hard[i - o_k][type_k][x + s_k])
//   conv        = no detector unsatisfied  (= golden: H * hard == syndrome over all window detectors)
// i = window round (0..W-1); hard[i] are the hard decisions of the errors homed in window round i.
// Offset-1 edges of window round 0 would read home round -1 (outside the window) and are forced off.
// Stage 1 (registered): per-detector parity (36 inputs: syndrome + 35 edges).
// Then an OR tree of fan-in FANIN, one register per level. Latency LAT = 1 + levels (W = 12, FANIN = 6: 1 + 4 = 5).
module conv_check
  import round_wiring_pkg::*;
#(
  parameter int W     = 12,
  parameter int FANIN = 6,
  localparam int ND   = W * NPOS
) (
  input  logic                                 clk,
  input  logic                                 in_valid,
  input  logic [W-1:0][NTYPES-1:0][NPOS-1:0]   hard,
  input  logic [W-1:0][NPOS-1:0]               syn,
  input  logic [W-1:0][NBASE-1:0]              emask,
  output logic                                 out_valid,
  output logic                                 conv,
  output logic [W-1:0][NPOS-1:0]               unsat      // registered after stage 1 (valid LAT - 1 cycles early)
);
  function automatic int lvl_size(int l);
    int s = ND;
    for (int j = 0; j < l; j++) s = (s + FANIN - 1) / FANIN;
    return s;
  endfunction
  function automatic int n_levels();
    int s = ND, n = 0;
    while (s > 1) begin s = (s + FANIN - 1) / FANIN; n++; end
    return n;
  endfunction
  localparam int NLEV = n_levels();
  localparam int LAT  = 1 + NLEV;      // cycles from in_valid to out_valid

  // ---------------------------------------------------------------- stage 1: detector parities
  logic [W-1:0][NPOS-1:0] par_c;
  for (genvar i = 0; i < W; i++) begin : g_r
    for (genvar x = 0; x < NPOS; x++) begin : g_x
      logic [NBASE-1:0] terms;
      for (genvar k = 0; k < NBASE; k++) begin : g_k
        localparam int PA = ((x / 6) + BE_SA[k]) % 12;
        localparam int PB = ((x % 6) + BE_SB[k]) % 6;
        localparam int H  = i - BE_OFF[k];
        if (H >= 0) begin : g_on
          assign terms[k] = emask[i][k] & hard[H][BE_TYPE[k]][PA * 6 + PB];
        end else begin : g_off
          assign terms[k] = 1'b0;
        end
      end
      assign par_c[i][x] = syn[i][x] ^ (^terms);
    end
  end

  logic v1;
  always_ff @(posedge clk) begin unsat <= par_c; v1 <= in_valid; end

  // ---------------------------------------------------------------- OR tree, registered per level

  logic [ND-1:0] lv [NLEV+1];
  logic          vv [NLEV+1];
  assign lv[0] = unsat;
  assign vv[0] = v1;
  for (genvar l = 0; l < NLEV; l++) begin : g_lev
    localparam int NI = lvl_size(l);
    localparam int NO = lvl_size(l + 1);
    logic [NO-1:0] o_c;
    for (genvar j = 0; j < NO; j++) begin : g_o
      localparam int LO = j * FANIN;
      localparam int HI = ((j + 1) * FANIN < NI) ? (j + 1) * FANIN : NI;
      assign o_c[j] = |lv[l][HI-1:LO];
    end
    always_ff @(posedge clk) begin
      lv[l+1] <= '0; lv[l+1][NO-1:0] <= o_c; vv[l+1] <= vv[l];
    end
  end
  assign conv      = ~lv[NLEV][0];
  assign out_valid = vv[NLEV];
endmodule
