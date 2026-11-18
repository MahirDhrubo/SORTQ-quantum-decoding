#!/bin/bash
# Test 2f step 1 (extra leg coverage) + round-step vectors. nice 10. Log: run_golden_rb2.log
cd "$(dirname "$0")"
export RAYON_NUM_THREADS=4
L=run_golden_rb2.log; : > $L
v() { echo "$(date -u '+%F %T') $*" >> $L; }
N="nice -n 10"
v start
$N ${RELAY_DUMP_PYTHON:-${RELAY_PYTHON:-python3}} golden_rb.py dumpshots dump_rbx 2 5,141 >> $L 2>&1 || { v "dumpshots FAILED"; exit 1; }
$N ${RELAY_DUMP_PYTHON:-${RELAY_PYTHON:-python3}} golden_rb.py dumpshots dump_rb_legs10b 10 1855 >> $L 2>&1 || { v "dumpshots legs10 FAILED"; exit 1; }
v "dumps done"
cd ../tb; mkdir -p vectors
$N ${RELAY_DUMP_PYTHON:-${RELAY_PYTHON:-python3}} gen_vectors_rb.py ../golden/dump_rb 3 vectors/rv_rb3.txt 96,106,53 >> ../golden/$L 2>&1 || { v "vec3 FAILED"; exit 1; } &
$N ${RELAY_DUMP_PYTHON:-${RELAY_PYTHON:-python3}} gen_vectors_rb.py ../golden/dump_rb_legs10 1 vectors/rv_rb53.txt 53 >> ../golden/$L.53 2>&1 &
$N ${RELAY_DUMP_PYTHON:-${RELAY_PYTHON:-python3}} gen_vectors_rb.py ../golden/dump_rbx 2 vectors/rv_rbx.txt 5,141 >> ../golden/$L.x 2>&1 &
$N ${RELAY_DUMP_PYTHON:-${RELAY_PYTHON:-python3}} gen_vectors_rb.py ../golden/dump_rb_legs10b 1 vectors/rv_rb1855.txt 1855 >> ../golden/$L.1855 2>&1 &
wait
cd ../golden; v "vectors done"; cat $L.53 $L.x $L.1855 >> $L
v finished
