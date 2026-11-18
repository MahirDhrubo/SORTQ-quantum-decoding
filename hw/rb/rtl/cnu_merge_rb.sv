// cnu_merge_rb.sv — Test 2f: second stage of the two-stage check node. Stage 1 is NG instances of the unchanged cnu.sv
// (one per group of at most GSZ base edges, OUT_REG = 1), each giving min1, min2, the index of min1 (in its group),
// its parity (syndrome only in group 0) and its per-edge out_sign (= group parity XOR own sign, 0 when masked).
// Stage 2 (this block) merges the groups with the same 2-min merge as cnu.sv and forms the outputs of ARITHMETIC.md
// section 2:   magnitude_e = (e == global min1 edge) ? min2 : min1,   sign_e = parity XOR own sign_e,
// masked edges 0. Global min1 edge = (winning group, its min1 index); ties go to the lower group, as in cnu.sv's tree
// (and any tie choice is bit-exact: a repeated minimum makes min2 = min1).
// OUT_REG = 1: one register stage on the outputs.
module cnu_merge_rb #(
  parameter int N       = 4,
  parameter int DEG     = 35,
  parameter int NG      = 5,
  parameter int GSZ     = 8,
  parameter bit OUT_REG = 1'b1,
  localparam int LW     = (GSZ > 1) ? $clog2(GSZ) : 1,
  localparam int GW     = (NG > 1) ? $clog2(NG) : 1
) (
  input  logic                    clk,
  input  logic                    in_valid,
  input  logic [DEG-1:0]          mask,          // stage-1 mask, registered with the stage-1 outputs
  input  logic [DEG-1:0]          g_osign,       // group cnu out_sign, edge order (edge e is in group e / GSZ)
  input  logic [NG-1:0][N-1:0]    g_min1,
  input  logic [NG-1:0][N-1:0]    g_min2,
  input  logic [NG-1:0][LW-1:0]   g_idx,
  input  logic [NG-1:0]           g_par,
  output logic                    out_valid,
  output logic [DEG-1:0]          out_sign,
  output logic [DEG-1:0][N-1:0]   out_mag
);
  localparam logic [N-1:0] MAXM = {N{1'b1}};
  localparam int LV = GW;                      // tree levels over the padded groups
  localparam int LEAVES = 1 << LV;
  typedef struct packed { logic [N-1:0] m1; logic [N-1:0] m2; logic [GW-1:0] g; } node_t;
  function automatic node_t merge(node_t a, node_t b);       // same rule as cnu.sv
    node_t r;
    if (a.m1 <= b.m1) begin r.m1 = a.m1; r.g = a.g; r.m2 = (a.m2 < b.m1) ? a.m2 : b.m1; end
    else              begin r.m1 = b.m1; r.g = b.g; r.m2 = (b.m2 < a.m1) ? b.m2 : a.m1; end
    return r;
  endfunction

  node_t tree [LV+1][LEAVES];
  logic [N-1:0] m1_c, m2_c; logic [GW-1:0] wg_c; logic par_c;
  logic [DEG-1:0] osign_c; logic [DEG-1:0][N-1:0] omag_c;
  always_comb begin
    for (int i = 0; i < LEAVES; i++) begin
      tree[0][i].m1 = (i < NG) ? g_min1[i] : MAXM;
      tree[0][i].m2 = (i < NG) ? g_min2[i] : MAXM;
      tree[0][i].g  = GW'(i);
    end
    for (int l = 0; l < LV; l++)
      for (int i = 0; i < (LEAVES >> (l + 1)); i++)
        tree[l+1][i] = merge(tree[l][2*i], tree[l][2*i+1]);
    m1_c = tree[LV][0].m1; m2_c = tree[LV][0].m2; wg_c = tree[LV][0].g;
    par_c = ^g_par;
    for (int e = 0; e < DEG; e++) begin
      omag_c[e]  = mask[e] ? (((GW'(e / GSZ) == wg_c) && (LW'(e % GSZ) == g_idx[e / GSZ])) ? m2_c : m1_c) : '0;
      osign_c[e] = mask[e] ? (g_osign[e] ^ g_par[e / GSZ] ^ par_c) : 1'b0;
    end
  end

  if (OUT_REG) begin : g_reg
    always_ff @(posedge clk) begin out_valid <= in_valid; out_sign <= osign_c; out_mag <= omag_c; end
  end else begin : g_comb
    always_comb begin out_valid = in_valid; out_sign = osign_c; out_mag = omag_c; end
  end
endmodule
