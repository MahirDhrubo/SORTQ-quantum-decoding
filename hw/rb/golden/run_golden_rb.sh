#!/bin/bash
# Test 2f step 1: rb13 golden decodes and dumps (nice 10, at most 4 threads). Log: run_golden_rb.log
cd "$(dirname "$0")"
export RAYON_NUM_THREADS=4
L=run_golden_rb.log; : > $L
v() { echo "$(date -u '+%F %T') $*" >> $L; }
N="nice -n 10"
v start
$N ${RELAY_DUMP_PYTHON:-${RELAY_PYTHON:-python3}} golden_rb.py decode rb_dumpbuild.npz >> $L 2>&1 || { v "decode dump build FAILED"; exit 1; }
$N ${RELAY_PYTHON:-python3} golden_rb.py decode rb_relayvenv.npz >> $L 2>&1 || { v "decode relay_venv FAILED"; exit 1; }
$N ${RELAY_DUMP_PYTHON:-${RELAY_PYTHON:-python3}} golden_rb.py compare rb_dumpbuild.npz rb_relayvenv.npz >> $L 2>&1
$N ${RELAY_DUMP_PYTHON:-${RELAY_PYTHON:-python3}} golden_rb.py compare rb_dumpbuild.npz ../../golden/ref_int4.2.8_sweep.npz >> $L 2>&1
v "decodes done"
$N ${RELAY_DUMP_PYTHON:-${RELAY_PYTHON:-python3}} golden_rb.py dump dump_rb >> $L 2>&1 || { v "dump FAILED"; exit 1; }
v "dump done"
$N ${RELAY_DUMP_PYTHON:-${RELAY_PYTHON:-python3}} golden_rb.py dumplegs dump_rb_legs10 2 10 >> $L 2>&1 || { v "dumplegs FAILED"; exit 1; }
v finished
