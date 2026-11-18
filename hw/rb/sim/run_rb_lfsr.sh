#!/bin/bash
# Review fixes, part B.1 + B.3 (no RTL change). nice 10, at most 4 cores. Log: run_rb_lfsr.log
#   B.1: tb_gamma_lfsr (720 gamma_src lanes, engine seeds, LFSR mode) 10,000 draws vs lfsr_model (lfsr_check.py)
#   B.3: closed loop of engine_top_rb in LFSR mode (built without RB_G8LOAD) on 6 golden + 200 random shots vs the
#        software LFSR model (prep_rb_lfsr.py). The testbench is tb_engine_rb.sv with LEGMAX raised to 301 (LFSR draws
#        can need more legs than the 10 of the LOAD-mode tests); nothing else changed.
cd "$(dirname "$0")"
export PATH=${HDL_ENV:+$HDL_ENV/bin:}$PATH RAYON_NUM_THREADS=1
L=run_rb_lfsr.log; : > $L
v() { echo "$(date -u '+%F %T') $*" >> $L; }
N="nice -n 10"
v start
# ---- B.1
$N verilator --binary -j 4 -Wno-fatal --top-module tb_gamma_lfsr -Mdir obj_lfsr ../../rtl/gamma_src.sv tb_gamma_lfsr.sv \
   > build_lfsr.log 2>&1 || { v "B.1 BUILD FAILED"; tail -20 build_lfsr.log >> $L; exit 1; }
$N ./obj_lfsr/Vtb_gamma_lfsr +NDRAWS=10000 +OUT=lfsr_rtl.txt >> $L 2>&1
$N ${RELAY_PYTHON:-python3} lfsr_check.py lfsr_rtl.txt lfsr_check.json > lfsr_check.log 2>&1; v "B.1 check rc=$? $(grep -E 'values_compared|mismatches' lfsr_check.log | tr -d '\n ')"
# ---- B.3
$N ${RELAY_PYTHON:-python3} prep_rb_lfsr.py shots_lfsr > prep_lfsr.log 2>&1 || { v "B.3 prep FAILED"; tail -20 prep_lfsr.log >> $L; exit 1; }
v "B.3 inputs: $(wc -l < shots_lfsr.txt) shots"
sed 's/LEGMAX = 10;/LEGMAX = 301;/' tb_engine_rb.sv > tb_engine_rb_lfsr.sv
grep -q "LEGMAX = 301" tb_engine_rb_lfsr.sv || { v "tb copy FAILED"; exit 1; }
$N verilator --binary -j 4 -Wno-fatal -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND -Wno-MULTIDRIVEN \
   --top-module tb_engine_rb -Mdir obj_rb_lfsr ../../rtl/round_wiring_pkg.sv ../../rtl/engine_tables_pkg.sv ../rtl/rb_pkg.sv \
   ../../rtl/round_wiring.sv ../../rtl/cnu.sv ../../rtl/vnu_nosat.sv ../../rtl/gamma_src.sv ../../rtl/state_mem.sv \
   ../../rtl/conv_check.sv ../../rtl/commit.sv ../rtl/vnu_post_rb.sv ../rtl/cnu_merge_rb.sv ../rtl/round_step_rb.sv \
   ../rtl/ctrl_rb.sv ../rtl/engine_top_rb.sv tb_engine_rb_lfsr.sv > build_rb_lfsr.log 2>&1 || { v "B.3 BUILD FAILED"; tail -30 build_rb_lfsr.log >> $L; exit 1; }
v "B.3 build done"
$N /usr/bin/time -f "runtime %e s, max RSS %M kB" ./obj_rb_lfsr/Vtb_engine_rb +LIST=shots_lfsr.txt > sim_rb_lfsr.log 2>&1
v "B.3 sim done: $(tail -3 sim_rb_lfsr.log | tr '\n' ' ')"
v finished
