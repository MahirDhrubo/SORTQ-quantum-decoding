#!/bin/bash
# Eval task 2: Test 1g rb13 (int4.2.8) at p = 0.001 on the Test 1b shots: 600,000 shots, seed 20261111, 8 workers x
# batch 1000 (= Test 1b p = 0.001), nice -n 10. The sweep schedule is decoded too, only as a shot-identity check
# against Test 1b's p0.001_int4.2.8_sweep.npz. Then test1e_criteria targets (T = 12 and 8 us) for rb13 at p = 0.001.
cd "$(dirname "$0")"
C=../circuits/bb_ibm
F="$C/circuit=bicycle_bivariate_144_12_12_memory_Z,distance=12,rounds=12,error_rate=0.001,noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim"
export RAYON_NUM_THREADS=1 TEST1G_SCHEDS=sweep,rb13
OUT=../results/test1g/p001; mkdir -p $OUT
nice -n 10 ${RELAY_PYTHON:-python3} test1g_order.py run "$F" p0.001 600000 8 1000 $OUT
nice -n 10 ${QUEUE_PYTHON:-python3} test1g_criteria_p001.py $OUT/criteria 1 > $OUT/criteria.log 2>&1
echo ALL DONE
