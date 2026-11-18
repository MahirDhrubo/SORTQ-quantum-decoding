#!/bin/bash
# Test 2e check: elaborate the existing RTL (hw/rtl + ctrl_pf + engine_top_pf2) with each sortq build's generated
# packages (round_wiring_pkg.sv, round_wiring.sv, engine_tables_pkg.sv) — Verilator lint, top engine_top_pf2.
# Usage: ./sortq_lint.sh <build dir> <W> <C>     prints "LINT <build> OK|FAIL (<errors>)"
B=$1; W=$2; C=$3
export PATH=${HDL_ENV:+$HDL_ENV/bin:}$PATH
HERE="$(cd "$(dirname "$0")" && pwd)"; RTL=$HERE/../hw/rtl
T=$(mktemp -d)
for f in $RTL/*.sv; do case $(basename $f) in round_wiring.sv|round_wiring_pkg.sv|engine_tables_pkg.sv) ;; *) cp $f $T/ ;; esac; done
cp $B/round_wiring.sv $B/round_wiring_pkg.sv $B/engine_tables_pkg.sv $T/
cp $HERE/../hw/synth/rtl_2c/ctrl_pf.sv $HERE/../hw/synth/rtl_2c/engine_top_pf2.sv $T/
out=$(verilator --lint-only --timing -Wno-fatal -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND -Wno-MULTIDRIVEN --top-module engine_top_pf2 \
      -GW=$W -GC=$C $(ls $T/*_pkg.sv) $(ls $T/*.sv | grep -v _pkg) 2>&1)
n=$(echo "$out" | grep -c "%Error")
echo "$out" > $B/lint.log
[ "$n" = 0 ] && echo "LINT $(basename $B) W=$W C=$C OK" || echo "LINT $(basename $B) FAIL ($n errors, see lint.log)"
rm -rf $T
