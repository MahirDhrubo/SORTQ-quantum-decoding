#!/bin/bash
# Run several mutants in parallel, one build job each (OBJTAG = mutant name keeps the build dirs apart).
# Usage: ./mutate_par.sh name1 name2 ...   (at most 4 names = 4 cores) -> logs/mutation_par.log
cd "$(dirname "$0")"
[ $# -le 4 ] || { echo "at most 4 mutants (4 cores)"; exit 1; }
for m in "$@"; do JOBS=1 ONLY=$m ./mutate.sh > logs/mut_$m.out 2>&1 & done
wait
cat $(for m in "$@"; do echo logs/mut_$m.out; done) | grep -E 'caught|NOT|no verdict' | tee logs/mutation_par.log
