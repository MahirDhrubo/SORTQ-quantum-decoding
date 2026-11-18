#!/bin/bash
# Build and install the patched Relay-BP decoder (relay_bp) into the active Python environment.
#   upstream: https://github.com/trmue/relay, commit cdfdc996ce55582c4c431f8d8392bcce57175e36
#   patch:    relay_bp_sortq.patch (this folder) adds
#               - check_layers: layered (round-by-round / red-black) schedules, order = layer ids
#               - quant:        bit-exact integer arithmetic (int4.2.8, int6.4.8; see hw/ARITHMETIC.md)
#               - RELAY_DUMP / RELAY_DUMP_LEGS: write-only golden dumps for the RTL test benches
#             With quant / check_layers unset and no dump file, decoding is unchanged.
# Needs: git, a Rust toolchain (cargo), and pip (maturin is fetched as the build backend).
# Usage: setup/relay_bp/build_relay_bp.sh [build dir]        (default: build/relay)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
D="${1:-$HERE/../../build/relay}"
COMMIT=cdfdc996ce55582c4c431f8d8392bcce57175e36
if [ ! -d "$D/.git" ]; then git clone https://github.com/trmue/relay "$D"; fi
cd "$D"
git checkout -q "$COMMIT"
git apply --check "$HERE/relay_bp_sortq.patch" && git apply "$HERE/relay_bp_sortq.patch"
python -m pip install .
python -c "import relay_bp; print('relay_bp installed from', relay_bp.__file__)"
