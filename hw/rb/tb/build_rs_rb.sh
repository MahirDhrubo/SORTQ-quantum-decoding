#!/bin/bash
# Test 2f: Verilator build of tb_round_step_rb (4 jobs, nice 10). Log: logs/build_rs_rb.log
cd "$(dirname "$0")"; mkdir -p logs
export PATH=${HDL_ENV:+$HDL_ENV/bin:}$PATH
OBJ=${1:-obj_rs_rb}; shift
nice -n 10 verilator --binary -j 4 -Wno-fatal -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND --top-module tb_round_step_rb -Mdir $OBJ "$@" \
  ../../rtl/round_wiring_pkg.sv ../rtl/rb_pkg.sv ../../rtl/round_wiring.sv ../../rtl/cnu.sv ../../rtl/vnu_nosat.sv \
  ../rtl/vnu_post_rb.sv ../rtl/cnu_merge_rb.sv ${RTL_RS:-../rtl/round_step_rb.sv} tb_round_step_rb.sv > logs/build_$OBJ.log 2>&1
echo "build exit $?" >> logs/build_$OBJ.log
