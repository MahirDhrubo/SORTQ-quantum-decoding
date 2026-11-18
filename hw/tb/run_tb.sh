#!/bin/bash
# Build and run one testbench with Verilator (from the HDL environment). Usage: ./run_tb.sh <tb_name> [-G<param>=<v> ...]
# Logs: logs/<tb_name><suffix>.log ; build dir obj_<tb_name><suffix>. At most 4 build jobs.
# RUNARGS="+X=..": run-time plusargs (reuse the build; added to the log name only). NOBUILD=1: skip the build if the
# binary exists. OBJTAG=x: separate build dir obj_<tb><suffix>_x (parallel builds). JOBS=n: build jobs (default 4).
set -e
cd "$(dirname "$0")"
export PATH=${HDL_ENV:+$HDL_ENV/bin:}$PATH
TB=$1; shift
SUF=$(echo "$*" | tr -c 'A-Za-z0-9=_' '_' | tr '=' '-' | sed 's/_*$//')
SUF=${SUF:+_$SUF}
RTL=${RTL:-../rtl}
LSUF=$(echo "$RUNARGS" | tr -c 'A-Za-z0-9=_' '_' | tr '=' '-' | sed 's/_*$//')
LSUF=$SUF${LSUF:+_$LSUF}${OBJTAG:+_$OBJTAG}
OBJ=obj_$TB$SUF${OBJTAG:+_$OBJTAG}
mkdir -p logs
SRCS="$(ls $RTL/*_pkg.sv) $(ls $RTL/*.sv | grep -v _pkg.sv)"
{
  echo "== $TB $* $RUNARGS ($(date '+%F %T'))"; verilator --version
  [ -n "$NOBUILD" ] && [ -x $OBJ/V$TB ] || verilator --binary --timing -j ${JOBS:-4} -Wno-fatal -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND --top-module $TB \
    -Mdir $OBJ "$@" $SRCS $TB.sv > logs/build_$TB$LSUF.log 2>&1 || { echo BUILD FAILED; tail -30 logs/build_$TB$LSUF.log; exit 1; }
  /usr/bin/time -f "runtime %e s, max RSS %M kB" ./$OBJ/V$TB $RUNARGS
} 2>&1 | tee logs/$TB$LSUF.log
