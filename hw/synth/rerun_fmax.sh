#!/bin/bash
# Test 2c: confirmation runs at the estimated fmax (period = 2.5 - WNS, rounded up to 0.01 ns) -> runs/<run>_fmax
cd "$(dirname "$0")"
for r in "$@"; do
  w=$(grep "^wns" runs/$r/result.txt | cut -d" " -f2)
  p=$(python3 -c "import math; print(f\"{math.ceil((2.5 - ($w)) * 100 - 1e-9) / 100:.2f}\")")
  echo "$(date -u "+%F %T") fmax rerun $r: wns $w -> period $p" >> logs/queue.log
  PERIOD=$p TAG=fmax ./queue_2c.sh $r
done
