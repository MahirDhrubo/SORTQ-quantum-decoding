#!/bin/bash
# Review fixes: lane A (window decoding, 8 threads) and lane B (LFSR accuracy, 3 single-thread streams; then the LFSR
# RTL checks, at most 4 cores). nice 10. Usage: ./run_review_fixes.sh A|B
cd "$(dirname "$0")"
OUT=../results/review_fixes; mkdir -p $OUT/windows $OUT/lfsr
N="nice -n 10"
if [ "$1" = A ]; then
  export RAYON_NUM_THREADS=8
  $N ${RELAY_PYTHON:-python3} review_windows.py run p0.003 30000 5000 1000 >> $OUT/windows/run.log 2>&1
  $N ${RELAY_PYTHON:-python3} review_windows.py run p0.002 500000 25000 2000 4 >> $OUT/windows/run.log 2>&1
  $N ${RELAY_PYTHON:-python3} review_windows.py merge p0.003 >> $OUT/windows/run.log 2>&1
  $N ${RELAY_PYTHON:-python3} review_windows.py merge p0.002 >> $OUT/windows/run.log 2>&1
  echo "LANE A DONE" >> $OUT/windows/run.log
fi
if [ "$1" = B ]; then
  export RAYON_NUM_THREADS=1
  $N ${RELAY_PYTHON:-python3} review_lfsr_acc.py p0.003_seed20261111 ../results/test1g/p0.003_rb13.npz $OUT/lfsr/p0.003_rb13_lfsr.npz > $OUT/lfsr/p0.003.log 2>&1 &
  $N ${RELAY_PYTHON:-python3} review_lfsr_acc.py p0.003_seed20261120 ../results/test1h/step2/p0.003_rb13_int4.npz $OUT/lfsr/p0.003_fresh_rb13_lfsr.npz > $OUT/lfsr/p0.003_fresh.log 2>&1 &
  $N ${RELAY_PYTHON:-python3} review_lfsr_acc.py p0.002_seed20261111 ../results/test1g/p0.002_rb13.npz $OUT/lfsr/p0.002_rb13_lfsr.npz > $OUT/lfsr/p0.002.log 2>&1 &
  wait
  ../hw/rb/sim/run_rb_lfsr.sh
  echo "LANE B DONE" >> $OUT/lfsr/p0.002.log
fi
