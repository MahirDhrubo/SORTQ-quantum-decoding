#!/bin/bash
# Test 2c follow-up: bit-exact replay of round_step_pf (VNU_PASSES 1 and 2; 3-shot and 10-leg vectors) + pf mutants.
# 4 cores: two builds of 2 jobs, then the two 10-leg runs, then 3 mutants of 1 job. Log: logs/pf_verify.log
cd "$(dirname "$0")"
L=logs/pf_verify.log; : > $L
v() { echo "$(date -u '+%F %T') $*" >> $L; }
v start
for p in 1 2; do ( JOBS=2 ./run_tb.sh tb_round_step_pf -GVNU_PASSES=$p > logs/pf_p$p.out 2>&1 ) & done; wait
for p in 1 2; do v "P$p 3-shot: $(grep -E '^tb_round_step_pf|^PASS|^FAIL|BUILD FAILED' logs/pf_p$p.out | tr '\n' ' ')"; done
for p in 1 2; do ( RUNARGS="+VEC=vectors/round_vectors_legs10.txt" NOBUILD=1 ./run_tb.sh tb_round_step_pf -GVNU_PASSES=$p > logs/pf_p${p}_legs10.out 2>&1 ) & done; wait
for p in 1 2; do v "P$p 10-leg: $(grep -E '^tb_round_step_pf|^PASS|^FAIL' logs/pf_p${p}_legs10.out | tr '\n' ' ')"; done
./mutate_par.sh pf_adv_p2 pf_prev_rd pf_sm > /dev/null 2>&1
v "mutants: $(tr '\n' ' ' < logs/mutation_par.log)"
v finished
