"""Test 2f: synthesis harness h_<run>.sv for engine_top_rb (same harness as Test 2c gen_harness.py: every input from a
flip-flop of one shift chain, every output into an XOR-chain register; resources reported for `dut` only).
Usage: python gen_harness_rb.py OUTDIR"""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "synth"))
from gen_harness import harness, TOP
TOPRB = TOP[:11] + [("lane_draw", "o", ""), ("lane_leg", "o", "[8:0]"), ("lane_home", "o", "[3:0]")] + TOP[11:]
RUNS = {
    "engine_top_rb": ("engine_top_rb", '.N(4), .STORAGE("LUTRAM"), .W(13), .C(13), .NRND(13)', "N = 4", TOPRB),
}
out = sys.argv[1]; os.makedirs(out, exist_ok=True)
for run, (mod, params, lp, ports) in RUNS.items():
    s = harness(run, mod, params, lp, ports).replace("PK_PLACEHOLDER", "")
    s = s.replace("import engine_tables_pkg::*;", "import engine_tables_pkg::*;\n  import rb_pkg::*;")
    open(os.path.join(out, f"h_{run}.sv"), "w").write(s.replace("hw/synth/gen_harness.py", "hw/rb/synth/gen_harness_rb.py"))
print(f"{len(RUNS)} harnesses -> {out}")
