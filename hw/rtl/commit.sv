// commit.sv — commit unit for the sliding window (W, C).
// After a window [t, t + W) is decoded, the errors homed in [t, t + C) are committed, one round per beat:
//   logical frame:   obs ^= XOR over committed errors e of OBS_ROM[type_e][pos_e]   (12 logicals)
//   syndrome carry:  committed errors of the last committed round (home t + C - 1) with offset-1 edges flip checks
//                    of round t + C, which is the first round of the next window:
//                      syn_corr[x] = XOR over offset-1 base edges k of hard[type_k][x + s_k]
//                    (rounds < t + C are not in the next window; the next window XORs syn_corr into round t + C).
// `clear` resets the frame (start of a shot). Pipeline: obs 2 cycles (per-type partial XOR, then combine +
// accumulate); syn_corr 1 cycle (valid when the beat had `last` = 1 and `carry_en` = 1, i.e. round t + C <= R).
module commit
  import round_wiring_pkg::*;
  import engine_tables_pkg::*;
(
  input  logic                          clk,
  input  logic                          clear,
  input  logic                          in_valid,
  input  logic [NTYPES-1:0][NPOS-1:0]   hard,          // hard decisions of one committed home round
  input  logic [NTYPES-1:0]             types_present,
  input  logic                          last,
  input  logic                          carry_en,
  output logic [NOBS-1:0]               obs,
  output logic                          obs_valid,     // obs includes all beats up to 2 cycles ago
  output logic                          syn_corr_valid,
  output logic [NPOS-1:0]               syn_corr
);
  logic [NTYPES-1:0][NPOS-1:0] h_m;
  always_comb for (int t = 0; t < NTYPES; t++) h_m[t] = types_present[t] ? hard[t] : '0;

  // stage 1: per type and logical, XOR over 72 positions
  logic [NTYPES-1:0][NOBS-1:0] part_c, part_q;
  logic v1;
  always_comb
    for (int t = 0; t < NTYPES; t++)
      for (int b = 0; b < NOBS; b++) begin
        logic acc;
        acc = 1'b0;
        for (int p = 0; p < NPOS; p++) acc ^= h_m[t][p] & OBS_ROM[t][p][b];
        part_c[t][b] = acc;
      end

  // syndrome carry (offset-1 edges)
  logic [NPOS-1:0] sc_c;
  for (genvar x = 0; x < NPOS; x++) begin : g_x
    logic [NBASE-1:0] terms;
    for (genvar k = 0; k < NBASE; k++) begin : g_k
      localparam int PA = ((x / 6) + BE_SA[k]) % 12;
      localparam int PB = ((x % 6) + BE_SB[k]) % 6;
      if (BE_OFF[k] == 1) begin : g_on
        assign terms[k] = h_m[BE_TYPE[k]][PA * 6 + PB];
      end else begin : g_off
        assign terms[k] = 1'b0;
      end
    end
    assign sc_c[x] = ^terms;
  end

  always_ff @(posedge clk) begin
    part_q <= part_c; v1 <= in_valid && !clear;
    syn_corr_valid <= in_valid && last && carry_en && !clear;
    if (in_valid && last && carry_en) syn_corr <= sc_c;
    if (clear) begin
      obs <= '0; obs_valid <= 1'b0;
    end else begin
      obs_valid <= 1'b1;
      if (v1) for (int b = 0; b < NOBS; b++) begin
        logic acc;
        acc = obs[b];
        for (int t = 0; t < NTYPES; t++) acc ^= part_q[t][b];
        obs[b] <= acc;
      end
    end
  end
endmodule
