"""Test 2f: engine_top_rb mutants and the write-back depth experiment. Writes mut/<name>/engine_top_rb.sv."""
import os
HERE = os.path.dirname(os.path.abspath(__file__))
E = open(os.path.join(HERE, "..", "rtl", "engine_top_rb.sv")).read()
M = {
  "vwb_dly1":   ("parameter int    V_WB_DLY  = 0,", "parameter int    V_WB_DLY  = 1,"),   # read->write 5 cycles
  "vwb_dly2":   ("parameter int    V_WB_DLY  = 0,", "parameter int    V_WB_DLY  = 2,"),   # read->write 6 cycles
  "m_read_copy": ("assign rc3 = ~sp[3].par;", "assign rc3 = sp[3].par;"),
  "no_prefill": ("assign g_we[1] = pre_w;", "assign g_we[1] = 1'b0;"),
  "c1_bank":    ("assign c1_we[b] = sp[5].v && sp[5].pa && (int'(sp[5].i[0]) != b);",
                 "assign c1_we[b] = sp[5].v && sp[5].pa && (int'(sp[5].i[0]) == b);"),
  "vnp_prev_write": ("assign vnp_we[b] = sp[6].v && is_cur;", "assign vnp_we[b] = wv;"),
  "conv_early": ("localparam int CDLY = 7;", "localparam int CDLY = 6;"),
}
for name, (old, new) in M.items():
    assert E.count(old) == 1, (name, E.count(old))
    d = os.path.join(HERE, "mut", name); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "engine_top_rb.sv"), "w").write(E.replace(old, new))
print(" ".join(M))
