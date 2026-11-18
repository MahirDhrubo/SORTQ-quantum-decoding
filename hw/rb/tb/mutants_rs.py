"""Test 2f: round_step_rb / cnu_merge_rb mutants (one realistic bug each). Writes mut/<name>/{round_step_rb,cnu_merge_rb}.sv.
Each replacement must match exactly once."""
import os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
RS = open(os.path.join(HERE, "..", "rtl", "round_step_rb.sv")).read()
CM = open(os.path.join(HERE, "..", "rtl", "cnu_merge_rb.sv")).read()
M = {   # name: (file, old, new, count)
  "cnu_gate_odd_none": ("rs", "(ps ? CNU_GATE_P1[k] : CNU_GATE_P0[k])", "(ps ? 1'b0 : CNU_GATE_P0[k])", 1),
  "cnu_gate_sweep":    ("rs", "(ps ? CNU_GATE_P1[k] : CNU_GATE_P0[k])", "(BE_OFF[k] == 0)", 1),
  "vnu_gate_none":     ("rs", "(prv ? (ps ? VG_PREV_P1[t][j] : VG_PREV_P0[t][j]) : (ps ? VG_CUR_P1[t][j] : VG_CUR_P0[t][j]))", "1'b0", 1),
  "no_m_minus1":       ("rs", "f3[p / PF_PPC] ?", "1'b0 ?", 2),
  "syn_stage":         ("rs", ".syn((g == 0) ? syn3[x] : 1'b0)", ".syn((g == 0) ? syn2[x] : 1'b0)", 1),
  "bias_prior_stage":  ("rs", ".prior(pb2_cur[CP][t])", ".prior(pb[CP].cur[t])", 1),
  "merge_no_group":    ("cm", "((GW'(e / GSZ) == wg_c) && (LW'(e % GSZ) == g_idx[e / GSZ]))", "(LW'(e % GSZ) == g_idx[e / GSZ])", 1),
  "merge_local_parity":("cm", "(g_osign[e] ^ g_par[e / GSZ] ^ par_c)", "g_osign[e]", 1),
}
for name, (f, old, new, cnt) in M.items():
    rs, cm = RS, CM
    if f == "rs": assert rs.count(old) == cnt, (name, rs.count(old)); rs = rs.replace(old, new)
    else: assert cm.count(old) == cnt, (name, cm.count(old)); cm = cm.replace(old, new)
    d = os.path.join(HERE, "mut", name); os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "round_step_rb.sv"), "w").write(rs); open(os.path.join(d, "cnu_merge_rb.sv"), "w").write(cm)
print(" ".join(M))
