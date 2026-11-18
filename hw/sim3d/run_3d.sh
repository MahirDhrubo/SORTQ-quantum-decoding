#!/bin/bash
# Test 3d (reduced) pipeline: pick shots, p = 0.002 g8 check dump, per-shot inputs + software references, Verilator
# build (4 jobs) and closed-loop simulation of engine_top_pf2_sim. nice -n 10, at most 4 cores. Log: run_3d.log
# Usage: ./run_3d.sh [wait_for_file wait_pattern]   (starts after the pattern appears in the file, e.g. Test 1g)
cd "$(dirname "$0")"
if [ -n "$1" ]; then while ! grep -q "$2" "$1" 2>/dev/null; do sleep 60; done; fi
export PATH=${HDL_ENV:+$HDL_ENV/bin:}$PATH RAYON_NUM_THREADS=1
L=run_3d.log; : > $L
v() { echo "$(date -u '+%F %T') $*" >> $L; }
N="nice -n 10"
v start
$N ${RELAY_PYTHON:-python3} prep_3d.py pick picks.json >> $L 2>&1 || { v "pick FAILED"; exit 1; }
$N ${RELAY_DUMP_PYTHON:-${RELAY_PYTHON:-python3}} prep_3d.py dump2 dump_p0.002.bin >> $L 2>&1 || { v "dump2 FAILED"; exit 1; }
v "dump2 done"
$N ${RELAY_PYTHON:-python3} prep_3d.py write shots picks.json ../golden/dump_legs10_shot0.bin \
   ../golden/dump_p0.003_shot0.bin ../golden/dump_p0.003_shot1.bin ../golden/dump_p0.003_shot2.bin dump_p0.002.bin \
   > prep_write.log 2>&1 || { v "write FAILED"; tail -20 prep_write.log >> $L; exit 1; }
v "inputs written: $(ls shots/shot_*.txt | wc -l) shots"
# order: golden first, then p = 0.003, then p = 0.002
{ ls shots/shot_p0.003_golden_*.txt; ls shots/shot_p0.003_leg*.txt; ls shots/shot_p0.002_leg*.txt; } > shots.txt
$N verilator --binary --timing -j 4 -Wno-fatal -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND -Wno-MULTIDRIVEN --top-module tb_engine_3d \
   -Mdir obj_3d $(ls ../rtl/*_pkg.sv) $(ls ../rtl/*.sv | grep -v _pkg) ../synth/rtl_2c/ctrl_pf.sv engine_top_pf2_sim.sv \
   tb_engine_3d.sv > build_3d.log 2>&1 || { v "BUILD FAILED"; tail -30 build_3d.log >> $L; exit 1; }
v "build done"
$N /usr/bin/time -f "runtime %e s, max RSS %M kB" ./obj_3d/Vtb_engine_3d +LIST=shots.txt > sim_3d.log 2>&1
v "sim done: $(tail -3 sim_3d.log | tr '\n' ' ')"
v finished
