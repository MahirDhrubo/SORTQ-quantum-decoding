#!/bin/bash
# Idea 1 Test 1b: formats {float, int4.2.8, int6.4.8} x schedules {sweep, flood}, paired shots (seed 20261111).
cd "$(dirname "$0")"
C=../circuits/bb_ibm
f() { echo "$C/circuit=bicycle_bivariate_144_12_12_memory_Z,distance=12,rounds=12,error_rate=$1,noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim"; }
export RAYON_NUM_THREADS=1
PY=${RELAY_PYTHON:-python3}; OUT=../results/test1b
$PY test1b_quant.py run "$(f 0.003)" p0.003 168000 8 500 $OUT
$PY test1b_quant.py run "$(f 0.002)" p0.002 600000 8 1000 $OUT
$PY test1b_quant.py run "$(f 0.001)" p0.001 600000 8 1000 $OUT
echo ALL DONE
