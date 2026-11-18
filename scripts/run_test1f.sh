#!/bin/bash
# Idea 1 Test 1f: k rounds per layer (k1..k4, flood), int4.2.8, Test 1b shots (seed 20261111, same batch x workers
# as Test 1b so the sampled shots are identical). 8 workers, nice -n 10 (Vivado keeps priority).
# Usage: ./run_test1f.sh [smoke]   smoke = first 4,000 shots of p = 0.003 into ../results/test1f/smoke
cd "$(dirname "$0")"
C=../circuits/bb_ibm
f() { echo "$C/circuit=bicycle_bivariate_144_12_12_memory_Z,distance=12,rounds=12,error_rate=$1,noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim"; }
export RAYON_NUM_THREADS=1
PY="nice -n 10 ${RELAY_PYTHON:-python3}"; OUT=../results/test1f
if [ "$1" = p001 ]; then   # added for Test 2d: p = 0.001 (Test 1b shots: 600,000, batch 1000 x 8 workers)
  $PY test1f_layers.py run "$(f 0.001)" p0.001 600000 8 1000 $OUT
  $PY test1f_layers.py report $OUT ../results/test1b > $OUT/report.log
  nice -n 10 ${QUEUE_PYTHON:-python3} test1f_criteria.py $OUT/criteria 8 > $OUT/criteria.log 2>&1
  echo P001 DONE; exit
fi
if [ "$1" = smoke ]; then
  $PY test1f_layers.py run "$(f 0.003)" p0.003 4000 8 500 $OUT/smoke
  $PY test1f_layers.py report $OUT/smoke ../results/test1b > $OUT/smoke/report.log
  echo SMOKE DONE; exit
fi
$PY test1f_layers.py run "$(f 0.003)" p0.003 168000 8 500 $OUT
$PY test1f_layers.py run "$(f 0.002)" p0.002 600000 8 1000 $OUT
$PY test1f_layers.py report $OUT ../results/test1b > $OUT/report.log
nice -n 10 ${QUEUE_PYTHON:-python3} test1f_criteria.py $OUT/criteria 8 > $OUT/criteria.log 2>&1
echo ALL DONE
