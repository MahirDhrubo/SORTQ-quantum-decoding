#!/bin/bash
# Test 2f: engine mutants + write-back depth experiment, closed loop on shots_mut.txt (golden + 50 random shots).
# Builds one after another (3 jobs, nice 10). Log: mutation_eng.log
cd "$(dirname "$0")"; export PATH=${HDL_ENV:+$HDL_ENV/bin:}$PATH
L=mutation_eng.log; : > $L
{ ls shots/shot_p0.003_golden_*.txt; ls shots/shot_p0.003_leg0_*.txt | head -20; ls shots/shot_p0.003_legs1to3_*.txt | head -5;
  ls shots/shot_p0.002_leg0_*.txt | head -20; ls shots/shot_p0.002_legs1to3_*.txt | head -5; } > shots_mut.txt
for m in ${MUTS:-$(python3 mutants_eng.py)}; do
  d=mut/$m
  nice -n 10 verilator --binary -j 3 -Wno-fatal -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND -Wno-MULTIDRIVEN +define+RB_G8LOAD \
   --top-module tb_engine_rb -Mdir $d/obj ../../rtl/round_wiring_pkg.sv ../../rtl/engine_tables_pkg.sv ../rtl/rb_pkg.sv \
   ../../rtl/round_wiring.sv ../../rtl/cnu.sv ../../rtl/vnu_nosat.sv ../../rtl/gamma_src.sv ../../rtl/state_mem.sv \
   ../../rtl/conv_check.sv ../../rtl/commit.sv ../rtl/vnu_post_rb.sv ../rtl/cnu_merge_rb.sv ../rtl/round_step_rb.sv \
   ../rtl/ctrl_rb.sv $d/engine_top_rb.sv tb_engine_rb.sv > $d/build.log 2>&1 || { echo "$m BUILD FAILED" >> $L; continue; }
  nice -n 10 $d/obj/Vtb_engine_rb +LIST=shots_mut.txt > $d/sim.log 2>&1
  echo "$m: $(grep -c MISMATCH $d/sim.log) mismatching shots of $(grep -c '^SHOT' $d/sim.log); $(grep HAZARD-CHECK $d/sim.log); $(grep -E '^(PASS|FAIL)' $d/sim.log); first hazard: $(grep -m1 -E '^HAZARD' $d/sim.log | grep -v CHECK)" >> $L
  rm -rf $d/obj
done
echo finished >> $L
