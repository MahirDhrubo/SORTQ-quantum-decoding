// vnu.sv — error (variable) node with memory (Mem-BP bias), bit-exact with ARITHMETIC.md section 3 + 5.
//   bias  = sat_marg( round( ((2^GD - g8) * prior + g8 * mpost) / 2^GD ) )      round = floor(x + 1/2)
//   total = bias + sum of effective c2v ;  marg = sat_marg(total) ;  hard = (marg <= 0)
//   v2c_e = sat_msg(total - c2v_eff_e)
// Leg start (init = 1, first iteration of a relay leg): c2v of edges flagged `late` (edge to round home + 1 while the
// error is updated in its home layer) are taken as 0 — the stored value belongs to the previous leg.
// Inputs/outputs of messages in sign-magnitude (N-bit magnitude); a "-0" input counts as 0.
// Masked edges (mask = 0) are ignored and output 0. OUT_REG = 1: one register stage on the outputs.
module vnu #(
  parameter int N       = 4,          // message magnitude bits
  parameter int DV      = 6,          // max error degree
  parameter int GW      = 4,          // g8 width (signed)
  parameter int GD      = 3,          // log2 of the gamma grid denominator (8)
  parameter bit OUT_REG = 1'b1,
  localparam int MB     = N + 3       // marginal / bias width (two's complement)
) (
  input  logic                         clk,
  input  logic                         in_valid,
  input  logic                         init,
  input  logic [DV-1:0]                mask,
  input  logic [DV-1:0]                late,
  input  logic signed [N:0]            prior,     // sign + N bits
  input  logic signed [GW-1:0]         g8,
  input  logic signed [MB-1:0]         mpost,     // marginal at the end of the previous iteration
  input  logic [DV-1:0]                c2v_sign,
  input  logic [DV-1:0][N-1:0]         c2v_mag,
  output logic                         out_valid,
  output logic signed [MB-1:0]         bias,
  output logic signed [MB-1:0]         marg,
  output logic                         hard,
  output logic [DV-1:0]                v2c_sign,
  output logic [DV-1:0][N-1:0]         v2c_mag
);
  localparam int PW = MB + GW + 3;                        // product / numerator width (generous)
  localparam int TW = MB + $clog2(DV + 1) + 2;            // total width (generous)
  localparam int MSGMAX  = (1 << N) - 1;
  localparam int MARGMAX = (1 << (MB - 1)) - 1;
  localparam int MARGMIN = -(1 << (MB - 1));

  /* verilator lint_off UNUSEDSIGNAL */  // high bits of rnd are only range headroom
  logic signed [PW-1:0] num, rnd;
  /* verilator lint_on UNUSEDSIGNAL */
  logic signed [TW-1:0] bias_w, total, ext [DV];
  logic signed [TW-1:0] c2v_eff [DV];
  logic signed [MB-1:0] bias_c, marg_c;
  logic                 hard_c;
  logic [DV-1:0]        vs_c;
  logic [DV-1:0][N-1:0] vm_c;

  /* verilator lint_off UNUSEDSIGNAL */
  function automatic logic signed [TW-1:0] sat(input logic signed [TW-1:0] x, input int lo, input int hi);
    if (x > TW'(hi))      return TW'(hi);
    else if (x < TW'(lo)) return TW'(lo);
    else                  return x;
  endfunction
  /* verilator lint_on UNUSEDSIGNAL */

  always_comb begin
    num    = (PW'(signed'(1 << GD)) - PW'(g8)) * PW'(prior) + PW'(g8) * PW'(mpost);
    rnd    = (num + PW'(1 << (GD - 1))) >>> GD;
    bias_w = sat(TW'(rnd), MARGMIN, MARGMAX);
    total  = bias_w;
    for (int e = 0; e < DV; e++) begin
      c2v_eff[e] = (mask[e] && !(init && late[e]))
                   ? (c2v_sign[e] ? -signed'(TW'({1'b0, c2v_mag[e]})) : signed'(TW'({1'b0, c2v_mag[e]}))) : '0;
      total = total + c2v_eff[e];
    end
    bias_c = MB'(bias_w);
    marg_c = MB'(sat(total, MARGMIN, MARGMAX));
    hard_c = (marg_c <= 0);
    for (int e = 0; e < DV; e++) begin
      ext[e]  = sat(total - c2v_eff[e], -MSGMAX, MSGMAX);
      vs_c[e] = mask[e] && (ext[e] < 0);
      vm_c[e] = mask[e] ? N'((ext[e] < 0) ? -ext[e] : ext[e]) : '0;
    end
  end

  if (OUT_REG) begin : g_reg
    always_ff @(posedge clk) begin
      out_valid <= in_valid; bias <= bias_c; marg <= marg_c; hard <= hard_c; v2c_sign <= vs_c; v2c_mag <= vm_c;
    end
  end else begin : g_comb
    always_comb begin
      out_valid = in_valid; bias = bias_c; marg = marg_c; hard = hard_c; v2c_sign = vs_c; v2c_mag = vm_c;
    end
  end
endmodule
