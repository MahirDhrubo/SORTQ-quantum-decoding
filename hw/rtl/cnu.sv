// cnu.sv — min-sum check node (alpha = 1), bit-exact with ARITHMETIC.md section 2.
// Inputs in sign-magnitude (N-bit magnitude), per-edge valid mask (boundary rounds switch off whole base edges).
// min1 / min2 / index of min1 by a balanced 2-min tree; sign parity by an XOR tree.
// Output: per edge, magnitude = (edge == min1 index) ? min2 : min1, sign = parity XOR own sign.
// Masked edges: ignored for min and parity, their outputs are 0.
// OUT_REG = 1 adds one register stage on all outputs (latency 1 cycle), OUT_REG = 0 is purely combinational.
module cnu #(
  parameter int N       = 4,          // message magnitude bits (4 now, 6 as option)
  parameter int DEG     = 35,         // max check degree (35 = base edges)
  parameter bit OUT_REG = 1'b1,
  localparam int IW     = (DEG > 1) ? $clog2(DEG) : 1
) (
  input  logic                    clk,
  input  logic                    in_valid,
  input  logic                    syn,
  input  logic [DEG-1:0]          mask,
  input  logic [DEG-1:0]          in_sign,
  input  logic [DEG-1:0][N-1:0]   in_mag,
  output logic                    out_valid,
  output logic [DEG-1:0]          out_sign,
  output logic [DEG-1:0][N-1:0]   out_mag,
  output logic [N-1:0]            min1,
  output logic [N-1:0]            min2,
  output logic [IW-1:0]           min1_idx,
  output logic                    parity
);
  localparam logic [N-1:0] MAXM = {N{1'b1}};   // = saturation value 2^N - 1
  localparam int LEAVES = 1 << IW;            // tree padded to a power of two
  localparam int LEVELS = IW;

  // 2-min tree node
  typedef struct packed { logic [N-1:0] m1; logic [N-1:0] m2; logic [IW-1:0] idx; } node_t;

  function automatic node_t merge(node_t a, node_t b);
    node_t r;
    if (a.m1 <= b.m1) begin r.m1 = a.m1; r.idx = a.idx; r.m2 = (a.m2 < b.m1) ? a.m2 : b.m1; end
    else              begin r.m1 = b.m1; r.idx = b.idx; r.m2 = (b.m2 < a.m1) ? b.m2 : a.m1; end
    return r;
  endfunction

  node_t tree [LEVELS+1][LEAVES];
  logic  par_c;
  logic [N-1:0] m1_c, m2_c;
  logic [IW-1:0] idx_c;
  logic [DEG-1:0] osign_c;
  logic [DEG-1:0][N-1:0] omag_c;

  always_comb begin
    for (int i = 0; i < LEAVES; i++) begin
      // masked or padding leaves carry MAX, which equals the golden "no second minimum" value after saturation
      tree[0][i].m1  = (i < DEG && mask[i]) ? in_mag[i] : MAXM;
      tree[0][i].m2  = MAXM;
      tree[0][i].idx = IW'(i);
    end
    for (int l = 0; l < LEVELS; l++)
      for (int i = 0; i < (LEAVES >> (l + 1)); i++)
        tree[l+1][i] = merge(tree[l][2*i], tree[l][2*i+1]);
    m1_c  = tree[LEVELS][0].m1;
    m2_c  = tree[LEVELS][0].m2;
    idx_c = tree[LEVELS][0].idx;
    par_c = syn ^ ^(in_sign & mask);
    for (int e = 0; e < DEG; e++) begin
      omag_c[e]  = mask[e] ? ((IW'(e) == idx_c) ? m2_c : m1_c) : '0;
      osign_c[e] = mask[e] ? (par_c ^ in_sign[e]) : 1'b0;
    end
  end

  if (OUT_REG) begin : g_reg
    always_ff @(posedge clk) begin
      out_valid <= in_valid;
      out_sign  <= osign_c;  out_mag <= omag_c;
      min1 <= m1_c; min2 <= m2_c; min1_idx <= idx_c; parity <= par_c;
    end
  end else begin : g_comb
    always_comb begin
      out_valid = in_valid;
      out_sign  = osign_c;  out_mag = omag_c;
      min1 = m1_c; min2 = m2_c; min1_idx = idx_c; parity = par_c;
    end
  end
endmodule
