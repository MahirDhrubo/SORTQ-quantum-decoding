#!/bin/bash
# sortq build --order rb check: elaborate the unchanged red-black RTL (hw/rtl blocks + hw/rb/rtl) with one build's
# generated packages (round_wiring_pkg.sv, round_wiring.sv, engine_tables_pkg.sv, rb_pkg.sv). Verilator lint, top
# engine_top_rb, one window over the whole circuit: W = C = NRND = number of detector rounds (as engine_top_rb was
# built and measured). File list as hw/rb/sim/run_rb.sh.
# Usage: ./sortq_lint_rb.sh <build dir> <NRND>       prints "LINT_RB <build> NRND=<n> OK|FAIL (<errors>)"
B=$1; N=$2
export PATH=${HDL_ENV:+$HDL_ENV/bin:}$PATH
HERE="$(cd "$(dirname "$0")" && pwd)"; RTL=$HERE/../hw/rtl; RB=$HERE/../hw/rb/rtl
out=$(verilator --lint-only --timing -Wno-fatal -Wno-WIDTHTRUNC -Wno-WIDTHEXPAND -Wno-MULTIDRIVEN --top-module engine_top_rb \
      -GW=$N -GC=$N -GNRND=$N \
      $B/round_wiring_pkg.sv $B/engine_tables_pkg.sv $B/rb_pkg.sv $B/round_wiring.sv \
      $RTL/cnu.sv $RTL/vnu_nosat.sv $RTL/gamma_src.sv $RTL/state_mem.sv $RTL/conv_check.sv $RTL/commit.sv \
      $RB/vnu_post_rb.sv $RB/cnu_merge_rb.sv $RB/round_step_rb.sv $RB/ctrl_rb.sv $RB/engine_top_rb.sv 2>&1)
n=$(echo "$out" | grep -c "%Error")
echo "$out" > $B/lint_rb.log
[ "$n" = 0 ] && echo "LINT_RB $(basename $B) NRND=$N OK ($(echo "$out" | grep -c "%Warning") warnings)" || echo "LINT_RB $(basename $B) NRND=$N FAIL ($n errors, see lint_rb.log)"
