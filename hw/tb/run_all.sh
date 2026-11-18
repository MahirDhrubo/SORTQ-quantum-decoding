#!/bin/bash
# Final regression of all Test 2a testbenches on the real RTL (../rtl). Summary: logs/regression.txt
cd "$(dirname "$0")"
unset RTL
R=logs/regression.txt; : > $R
t() { local name=$1; shift; local out; out=$(RUNARGS="$RUNARGS" NOBUILD="$NOBUILD" ./run_tb.sh "$@" 2>&1)
      echo "[$name] $(echo "$out" | grep -E '^tb_' | tail -1) => $(echo "$out" | grep -E '^(PASS|FAIL)$' | tail -1)" | tee -a $R; }
t "cnu golden, OUT_REG=1"   tb_cnu
t "cnu golden, OUT_REG=0"   tb_cnu -GOUT_REG=0
t "vnu golden, OUT_REG=1"   tb_vnu
t "vnu golden, OUT_REG=0"   tb_vnu -GOUT_REG=0
t "cnu N=6 random model"    tb_cnu -GN=6 -GVEC=\"vectors/cnu_vectors_N6.txt\"
t "vnu N=6 random model"    tb_vnu -GN=6 -GVEC=\"vectors/vnu_vectors_N6.txt\"
t "gamma_src"               tb_gamma_src
t "rot2d PIPE=1"            tb_rot2d
t "rot2d PIPE=0"            tb_rot2d -GPIPE=0
t "round_wiring K=1"        tb_round_wiring -GK_ROUNDS=1
t "round_wiring K=2"        tb_round_wiring -GK_ROUNDS=2
t "conv_check"              tb_conv_check
t "ctrl"                    tb_ctrl
t "commit"                  tb_commit
for c in "BRAM 1" "LUTRAM 1" "LUTRAM 0" "REG 1" "REG 0"; do set -- $c
t "state_mem $1 RD_LAT=$2"  tb_state_mem -GSTORAGE=\"$1\" -GRD_LAT=$2; done
for v in 1 2; do
t "round_step golden, VNU_PASSES=$v, 3 shots x 2 legs"      tb_round_step -GVNU_PASSES=$v
RUNARGS="+VEC=vectors/round_vectors_legs10.txt" NOBUILD=1 \
t "round_step golden, VNU_PASSES=$v, 580-iteration shot, 10 legs" tb_round_step -GVNU_PASSES=$v; done
for v in 1 2; do
t "round_step_pf golden, VNU_PASSES=$v, 3 shots x 2 legs"   tb_round_step_pf -GVNU_PASSES=$v
RUNARGS="+VEC=vectors/round_vectors_legs10.txt" NOBUILD=1 \
t "round_step_pf golden, VNU_PASSES=$v, 580-iteration shot, 10 legs" tb_round_step_pf -GVNU_PASSES=$v; done
for v in 1 2; do
t "round_step_pf2 golden, VNU_PASSES=$v, 3 shots x 2 legs"  tb_round_step_pf2 -GVNU_PASSES=$v
RUNARGS="+VEC=vectors/round_vectors_legs10.txt" NOBUILD=1 \
t "round_step_pf2 golden, VNU_PASSES=$v, 580-iteration shot, 10 legs" tb_round_step_pf2 -GVNU_PASSES=$v; done
echo "== $(grep -c '=> PASS' $R) PASS, $(grep -c '=> FAIL' $R) FAIL, $(grep -vc '=> PASS\|=> FAIL' $R) other" | tee -a $R
