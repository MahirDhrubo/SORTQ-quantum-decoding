#!/bin/bash
# Test 2f: round_step_rb mutants, built one after another (3 jobs, nice 10), each replayed on the rb vectors.
# Log: logs/mutation_rs.log
cd "$(dirname "$0")"; export PATH=${HDL_ENV:+$HDL_ENV/bin:}$PATH
L=logs/mutation_rs.log; : > $L
for m in $(python3 mutants_rs.py); do
  d=mut/$m
  nice -n 10 verilator --binary -j 3 -Wno-fatal -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND --top-module tb_round_step_rb -Mdir $d/obj \
    ../../rtl/round_wiring_pkg.sv ../rtl/rb_pkg.sv ../../rtl/round_wiring.sv ../../rtl/cnu.sv ../../rtl/vnu_nosat.sv \
    ../rtl/vnu_post_rb.sv $d/cnu_merge_rb.sv $d/round_step_rb.sv tb_round_step_rb.sv > $d/build.log 2>&1 || { echo "$m BUILD FAILED" >> $L; continue; }
  for v in rbx rb3; do
    nice -n 10 $d/obj/Vtb_round_step_rb +VEC=vectors/rv_$v.txt +PRIOR=vectors/prior_table.txt > $d/replay_$v.log 2>&1
    echo "$m $v: $(grep -E '^mismatches' $d/replay_$v.log) $(grep -E '^(PASS|FAIL)' $d/replay_$v.log)" >> $L
  done
  rm -rf $d/obj
done
echo finished >> $L
