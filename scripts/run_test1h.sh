#!/bin/bash
# Idea 1 Test 1h: rb accuracy at p = 0.003. 8 workers, nice -n 10, RAYON_NUM_THREADS=1 (as Test 1g).
#   step 1: rb13 float (+ rb13 int4 as identity check vs Test 1g) on the Test 1b shots, p = 0.003
#   step 2: fresh shots (seed 20261120), float flood reference + 6 rb settings; pick
#   step 3: chosen setting on the Test 1b shots, p = 0.003 and 0.002; criteria (T = 12 us); report
# Usage: ./run_test1h.sh [smoke]    smoke = 2,000 shots per step -> test1h/smoke
cd "$(dirname "$0")"
C=../circuits/bb_ibm
f() { echo "$C/circuit=bicycle_bivariate_144_12_12_memory_Z,distance=12,rounds=12,error_rate=$1,noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim"; }
export RAYON_NUM_THREADS=1
PY="nice -n 10 ${RELAY_PYTHON:-python3}"; QPY="nice -n 10 ${QUEUE_PYTHON:-python3}"
OUT=../results/test1h; N3=168000; N2=600000
if [ "$1" = smoke ]; then OUT=../results/test1h/smoke; N3=2000; N2=2000; fi
mkdir -p $OUT
S2=flood_float,rb13_int4,rb13_int4_g0.0625,rb13_int4_g0.25,rb13_int4_i0.15_0.5,rb13_int4_i0.3_0.7,odd13_int4
$PY test1h.py run "$(f 0.003)" p0.003 $N3 8 500 20261111 $OUT/step1 rb13_float,rb13_int4 || exit 1
$PY test1h.py run "$(f 0.003)" p0.003 $N3 8 500 20261120 $OUT/step2 $S2 || exit 1
$QPY test1h_report.py pick $OUT || exit 1
CH=$(python3 -c "import json; print(json.load(open('$OUT/chosen.json'))['chosen'])")
$PY test1h.py run "$(f 0.003)" p0.003 $N3 8 500 20261111 $OUT/step3 $CH || exit 1
$PY test1h.py run "$(f 0.002)" p0.002 $N2 8 1000 20261111 $OUT/step3 $CH || exit 1
[ "$1" = smoke ] || $QPY test1h_criteria.py $OUT/criteria 2 > $OUT/criteria.log 2>&1
$QPY test1h_report.py report $OUT > $OUT/report.log
echo ALL DONE
