#!/bin/bash
# wait for the round-step mutants, then final closed-loop regression (final RTL), then the engine mutants
cd "$(dirname "$0")"
until grep -q finished ../tb/logs/mutation_rs.log 2>/dev/null; do sleep 30; done
./run_rb.sh
./mut_eng.sh
