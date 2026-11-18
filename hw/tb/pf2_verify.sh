#!/bin/bash
# Test 2c follow-up: bit-exact replay of round_step_pf2 (VNU_PASSES 1 and 2; 3-shot and 10-leg vectors), tb_ctrl_pf
# (ctrl_pf vs ctrl, STEP_CYCLES 2 and 3) and pf2 mutants. 4 cores. Log: logs/pf2_verify.log
cd "$(dirname "$0")"
export PATH=${HDL_ENV:+$HDL_ENV/bin:}$PATH
L=logs/pf2_verify.log; : > $L
v() { echo "$(date -u '+%F %T') $*" >> $L; }
v start
for p in 1 2; do ( JOBS=2 ./run_tb.sh tb_round_step_pf2 -GVNU_PASSES=$p > logs/pf2_p$p.out 2>&1 ) & done; wait
for p in 1 2; do v "P$p 3-shot: $(grep -E '^tb_round_step_pf2|^PASS|^FAIL|BUILD FAILED|fatal|cur_valid_dup' logs/pf2_p$p.out | tr '\n' ' ')"; done
for p in 1 2; do ( RUNARGS="+VEC=vectors/round_vectors_legs10.txt" NOBUILD=1 ./run_tb.sh tb_round_step_pf2 -GVNU_PASSES=$p > logs/pf2_p${p}_legs10.out 2>&1 ) & done; wait
for p in 1 2; do v "P$p 10-leg: $(grep -E '^tb_round_step_pf2|^PASS|^FAIL|fatal|cur_valid_dup' logs/pf2_p${p}_legs10.out | tr '\n' ' ')"; done
for p in 1 2; do ( RUNARGS="+FLUSH" NOBUILD=1 ./run_tb.sh tb_round_step_pf2 -GVNU_PASSES=$p > logs/pf2_p${p}_flush.out 2>&1 ) & done; wait
for p in 1 2; do v "P$p 3-shot +FLUSH: $(grep -E '^FLUSH|^tb_round_step_pf2|^PASS|^FAIL|fatal|cur_valid_dup' logs/pf2_p${p}_flush.out | tr '\n' ' ')"; done
for p in 2 3; do
  verilator --binary --timing -j 1 -Wno-fatal -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND --top-module tb_ctrl_pf -GSTEP_CYCLES=$p \
    -Mdir obj_tb_ctrl_pf_$p $(ls ../rtl/*_pkg.sv) ../rtl/ctrl.sv ../synth/rtl_2c/ctrl_pf.sv tb_ctrl_pf.sv > logs/build_tb_ctrl_pf_$p.log 2>&1
  ./obj_tb_ctrl_pf_$p/Vtb_ctrl_pf > logs/tb_ctrl_pf_$p.log 2>&1
  v "tb_ctrl_pf P$p: $(grep -E '^tb_ctrl_pf|^PASS|^FAIL' logs/tb_ctrl_pf_$p.log | tr '\n' ' ')"
done
./mutate_par.sh pf2_bfresh pf2_a2 pf2_adv_p2 pf2_flush > /dev/null 2>&1
v "mutants: $(tr '\n' ' ' < logs/mutation_par.log)"
v finished
