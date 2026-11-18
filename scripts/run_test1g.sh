#!/bin/bash
# Idea 1 Test 1g: red-black round order (sweep, rb13, rb2), int4.2.8, Test 1b shots (seed 20261111, Test 1b batch x
# workers). 8 workers, nice -n 10. Usage: ./run_test1g.sh [smoke]   smoke = 4,000 shots of p = 0.003 -> test1g/smoke
cd "$(dirname "$0")"
C=../circuits/bb_ibm
f() { echo "$C/circuit=bicycle_bivariate_144_12_12_memory_Z,distance=12,rounds=12,error_rate=$1,noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim"; }
export RAYON_NUM_THREADS=1
PY="nice -n 10 ${RELAY_PYTHON:-python3}"; OUT=../results/test1g
mkdir -p $OUT
$PY test1g_order.py hcheck "$(f 0.003)" $OUT/hcheck.json > $OUT/hcheck.log
if [ "$1" = smoke ]; then
  $PY test1g_order.py run "$(f 0.003)" p0.003 4000 8 500 $OUT/smoke
  $PY test1g_order.py report $OUT/smoke ../results/test1b > $OUT/smoke/report.log
  echo SMOKE DONE; exit
fi
$PY test1g_order.py run "$(f 0.003)" p0.003 168000 8 500 $OUT
$PY test1g_order.py run "$(f 0.002)" p0.002 600000 8 1000 $OUT
$PY test1g_order.py report $OUT ../results/test1b > $OUT/report.log
nice -n 10 ${QUEUE_PYTHON:-python3} test1g_criteria.py $OUT/criteria 8 > $OUT/criteria.log 2>&1
echo ALL DONE
