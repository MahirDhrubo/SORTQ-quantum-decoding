#!/bin/bash
# Test 2f closed loop: pick shots, per-shot inputs + rb13 software references, Verilator build (4 jobs), simulation.
# nice 10, at most 4 cores. Log: run_rb.log
cd "$(dirname "$0")"
export PATH=${HDL_ENV:+$HDL_ENV/bin:}$PATH RAYON_NUM_THREADS=1
L=run_rb.log; : > $L
v() { echo "$(date -u '+%F %T') $*" >> $L; }
N="nice -n 10"
v start
if [ ! -f shots/index.json ]; then
  $N ${RELAY_PYTHON:-python3} prep_rb.py pick picks_rb.json >> $L 2>&1 || { v "pick FAILED"; exit 1; }
  G=../golden; G2=../../golden
  $N ${RELAY_PYTHON:-python3} prep_rb.py write shots picks_rb.json $G/dump_rb_legs10b_shot0.bin $G/dump_rb_legs10_shot0.bin \
     $G/dump_rb_shot0.bin $G/dump_rb_shot1.bin $G/dump_rb_shot2.bin $G/dump_rbx_shot0.bin $G/dump_rbx_shot1.bin \
     $G2/dump_legs10_shot0.bin $G2/dump_p0.003_shot0.bin ../../sim3d/dump_p0.002.bin \
     > prep_write.log 2>&1 || { v "write FAILED"; tail -20 prep_write.log >> $L; exit 1; }
  v "inputs written: $(ls shots/shot_*.txt | wc -l) shots"
fi
{ ls shots/shot_p0.003_golden_*.txt; ls shots/shot_p0.003_leg*.txt; ls shots/shot_p0.002_leg*.txt; } > shots.txt
$N verilator --binary -j 4 -Wno-fatal -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND -Wno-MULTIDRIVEN +define+RB_G8LOAD \
   --top-module tb_engine_rb -Mdir obj_rb ../../rtl/round_wiring_pkg.sv ../../rtl/engine_tables_pkg.sv ../rtl/rb_pkg.sv \
   ../../rtl/round_wiring.sv ../../rtl/cnu.sv ../../rtl/vnu_nosat.sv ../../rtl/gamma_src.sv ../../rtl/state_mem.sv \
   ../../rtl/conv_check.sv ../../rtl/commit.sv ../rtl/vnu_post_rb.sv ../rtl/cnu_merge_rb.sv ../rtl/round_step_rb.sv \
   ../rtl/ctrl_rb.sv ../rtl/engine_top_rb.sv tb_engine_rb.sv > build_rb.log 2>&1 || { v "BUILD FAILED"; tail -30 build_rb.log >> $L; exit 1; }
v "build done"
$N /usr/bin/time -f "runtime %e s, max RSS %M kB" ./obj_rb/Vtb_engine_rb +LIST=${LIST:-shots.txt} > sim_rb.log 2>&1
v "sim done: $(tail -4 sim_rb.log | tr '\n' ' ')"
v finished
