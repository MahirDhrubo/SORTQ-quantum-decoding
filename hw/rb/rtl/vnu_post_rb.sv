// vnu_post_rb.sv — Test 2f: second half of vnu_nosat.sv (ARITHMETIC.md section 3) with the bias as an input, so the
// bias (prior, g8, M(t-1): all known at iteration start) can be computed one pipeline stage earlier, in parallel with
// the CNU. The expressions below are copied from vnu_nosat.sv unchanged (total, marginal saturation, hard decision,
// extrinsic v2c); vnu_nosat's bias is |bias| < 2^(MB-1) (no saturator, Test 2a), so feeding the MB-bit bias here,
// sign-extended to TW bits, gives exactly vnu_nosat's bias_w.
//   total = bias + sum of effective c2v ;  marg = sat_marg(total) ;  hard = (marg <= 0) ; v2c_e = sat_msg(total - c2v_e)
// gate[e] = 1: c2v of edge e is taken as 0 (leg start, check not yet run in this iteration; = init && late in vnu).
// Masked edges (mask = 0) are ignored and output 0. OUT_REG = 1: one register stage on the outputs.
module vnu_post_rb #(
  parameter int N       = 4,
  parameter int DV      = 6,
  parameter bit OUT_REG = 1'b1,
  localparam int MB     = N + 3
) (
  input  logic                         clk,
  input  logic                         in_valid,
  input  logic [DV-1:0]                mask,
  input  logic [DV-1:0]                gate,
  input  logic signed [MB-1:0]         bias,
  input  logic [DV-1:0]                c2v_sign,
  input  logic [DV-1:0][N-1:0]         c2v_mag,
  output logic                         out_valid,
  output logic signed [MB-1:0]         marg,
  output logic                         hard,
  output logic [DV-1:0]                v2c_sign,
  output logic [DV-1:0][N-1:0]         v2c_mag
);
  localparam int TW = MB + $clog2(DV + 1) + 2;            // as vnu_nosat
  localparam int MSGMAX  = (1 << N) - 1;
  localparam int MARGMAX = (1 << (MB - 1)) - 1;
  localparam int MARGMIN = -(1 << (MB - 1));

  logic signed [TW-1:0] total, ext [DV];
  logic signed [TW-1:0] c2v_eff [DV];
  logic signed [MB-1:0] marg_c;
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
    total = TW'(bias);
    for (int e = 0; e < DV; e++) begin
      c2v_eff[e] = (mask[e] && !gate[e])
                   ? (c2v_sign[e] ? -signed'(TW'({1'b0, c2v_mag[e]})) : signed'(TW'({1'b0, c2v_mag[e]}))) : '0;
      total = total + c2v_eff[e];
    end
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
      out_valid <= in_valid; marg <= marg_c; hard <= hard_c; v2c_sign <= vs_c; v2c_mag <= vm_c;
    end
  end else begin : g_comb
    always_comb begin
      out_valid = in_valid; marg = marg_c; hard = hard_c; v2c_sign = vs_c; v2c_mag = vm_c;
    end
  end
endmodule
