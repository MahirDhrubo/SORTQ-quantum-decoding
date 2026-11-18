# Test 1f: k check rounds per layer (accuracy and iterations)

## Setup
- **Decoder:** same as Test 1b int4.2.8 (`relay_bp.RelayDecoderF32`, quant int4.2.8). Settings: alpha = 1, S = 1, gamma0 = 0.125, gamma interval (−0.226, 0.622), pre_iter 80, 300 legs × 60 (cap 18,080).
- **Circuit:** 12-round gross-code circuit, X decoder.
- **Shots:** sampler seed 20261111, with the same batch × workers as Test 1b, so the shots are the Test 1b shots. Every schedule decodes the same shots.
  - p = 0.003: 168,000 shots.
  - p = 0.002: 600,000 shots.
- **Schedules** (`check_layers` = round // k; consecutive rounds grouped, last group smaller):

  | Schedule | Layers |
  |---|---|
  | k = 1 | 13 |
  | k = 2 | 7 |
  | k = 3 | 5 |
  | k = 4 | 4 |
  | flood | 1 |

  One iteration = one pass over all layers.
- **Reproduction check (measured):** k = 1 and flood equal the Test 1b int4.2.8 sweep and flood traces on every shot. 0 of 168,000 / 600,000 shots differ in iterations, success or logical failure.
- **Real-time targets:** test1e_criteria.py, unchanged model, run on the per-k traces:
  - seed 20261112, 10^7 jobs, K = 18,080, overhead 200 ns;
  - T = 12 and 8 µs, the same as the 12-round Test 1b trace in Test 1e;
  - criteria: (a) utilization < 0.7 and queue max < 1,000; (b) p99.9 < 100 µs; (c) p99.9 < 1 ms; (d) p99.9 < 10 ms.
- **Compute:** server, 8 workers at nice 10. p = 0.003 took 33 min and p = 0.002 took 39 min; the criteria run took 47 s.
- **Files:** scripts `scripts/test1f_layers.py`, `scripts/test1f_criteria.py`, `scripts/run_test1f.sh`. Traces `p{p}_{k1,k2,k3,k4,flood}.npz` (Test 1b format), plus `report.json` and `criteria/criteria.json`.

## Results (all measured)

### Logical error rate

| p | k = 1 | k = 2 | k = 3 | k = 4 | flood |
|---|---|---|---|---|---|
| 0.003 (168,000 shots) | 128 (7.62e-4) | 123 (7.32e-4) | 130 (7.74e-4) | 122 (7.26e-4) | 106 (6.31e-4) |
| 0.002 (600,000 shots) | 19 (3.17e-5) | 23 (3.83e-5) | 21 (3.50e-5) | 23 (3.83e-5) | 29 (4.83e-5) |

Not converged (all of them hit the 18,080 cap):

| p | k = 1 | k = 2 | k = 3 | k = 4 | flood |
|---|---|---|---|---|---|
| 0.003 | 9 | 13 | 20 | 17 | 18 |
| 0.002 | 3 | 5 | 6 | 6 | 8 |

### Paired comparison with k = 1 (same shots)

| p | Schedule | Both fail | Only k = 1 fails | Only this one fails | McNemar p |
|---|---|---|---|---|---|
| 0.003 | k = 2 | 56 | 72 | 67 | 0.73 |
| 0.003 | k = 3 | 67 | 61 | 63 | 0.93 |
| 0.003 | k = 4 | 59 | 69 | 63 | 0.66 |
| 0.003 | flood | 54 | 74 | 52 | 0.061 |
| 0.002 | k = 2 | 9 | 10 | 14 | 0.54 |
| 0.002 | k = 3 | 8 | 11 | 13 | 0.84 |
| 0.002 | k = 4 | 7 | 12 | 16 | 0.57 |
| 0.002 | flood | 8 | 11 | 21 | 0.11 |

### Iterations per shot

| p | Schedule | Mean | vs k = 1 | p50 | p90 | p99 | p99.9 | Max |
|---|---|---|---|---|---|---|---|---|
| 0.003 | k = 1 | 23.53 | — | 11 | 27 | 217 | 1,264 | 18,080 |
| 0.003 | k = 2 | 27.28 | +16.0% | 13 | 29 | 239 | 1,677 | 18,080 |
| 0.003 | k = 3 | 29.77 | +26.5% | 13 | 31 | 274 | 1,837 | 18,080 |
| 0.003 | k = 4 | 30.28 | +28.7% | 14 | 32 | 279 | 1,639 | 18,080 |
| 0.003 | flood | 32.51 | +38.2% | 15 | 34 | 296 | 1,979 | 18,080 |
| 0.002 | k = 1 | 10.25 | — | 8 | 17 | 39 | 216 | 18,080 |
| 0.002 | k = 2 | 11.33 | +10.5% | 8 | 18 | 43 | 246 | 18,080 |
| 0.002 | k = 3 | 12.15 | +18.5% | 9 | 19 | 46 | 244 | 18,080 |
| 0.002 | k = 4 | 12.49 | +21.8% | 9 | 19 | 48 | 271 | 18,080 |
| 0.002 | flood | 13.35 | +30.2% | 10 | 20 | 55 | 280 | 18,080 |

(The p99.9 values are the numpy interpolated percentile.)

### Largest t_iter per k (ns per iteration, test1e_criteria model)

p = 0.003:

| Schedule | T = 12 µs: a / b / c / d | T = 8 µs: a / b / c / d |
|---|---|---|
| k = 1 | 277 / 13 / 63 / 327 | 184 / 11 / 60 / 258 |
| k = 2 | 261 / 11 / 61 / 293 | 173 / 9 / 58 / 225 |
| k = 3 | 234 / 9 / 58 / 266 | 156 / 8 / 56 / 203 |
| k = 4 | 202 / 9 / 58 / 260 | 134 / 8 / 56 / 200 |
| flood | 235 / 9 / 58 / 257 | 156 / 8 / 56 / 191 |

p = 0.002:

| Schedule | T = 12 µs: a / b / c / d | T = 8 µs: a / b / c / d |
|---|---|---|
| k = 1 | 626 / 56 / 162 / 631 | 417 / 43 / 133 / 569 |
| k = 2 | 581 / 48 / 131 / 588 | 386 / 37 / 105 / 547 |
| k = 3 | 373 / 35 / 104 / 571 | 248 / 27 / 88 / 492 |
| k = 4 | 356 / 35 / 102 / 567 | 237 / 27 / 87 / 489 |
| flood | 345 / 31 / 93 / 552 | 230 / 24 / 81 / 429 |

- **What binds:**
  - (a) is bound by the queue max in every row. The queue max depends on a few very long decodes, so (a) jumps between neighbouring k (for example 626 → 581 → 373 at p = 0.002, T = 12 µs).
  - (b), (c) and (d) are bound by the p99.9 latency.
- **Time per layer** (computed from the measured targets: t_iter ÷ number of layers, criterion (c), T = 12 µs):

  | p | k = 1 | k = 2 | k = 3 | k = 4 | flood |
  |---|---|---|---|---|---|
  | 0.003 | 4.8 ns | 8.7 ns | 11.6 ns | 14.5 ns | 58 ns |
  | 0.002 | 12.5 ns | 18.7 ns | 20.8 ns | 25.5 ns | 93 ns |

## What this means
- **Accuracy:** at these shot counts, grouping k = 2, 3 or 4 rounds per layer does not change the logical error rate measurably. Every paired comparison with k = 1 has McNemar p ≥ 0.54.
  - Flood is the closest to a difference, in opposite directions at the two p: fewer failures at p = 0.003 (p = 0.061) and more at p = 0.002 (p = 0.11).
  - There are only 19–29 failures per schedule at p = 0.002, so differences below about 1.5× can't be resolved there.
- **Iterations:** convergence gets slower with larger k. Mean iterations grow by 16% / 27% / 29% / 38% (k = 2, 3, 4, flood) at p = 0.003, and by 10% / 19% / 22% / 30% at p = 0.002. The tails (p99, p99.9) grow by similar amounts.
- **Speed targets:**
  - The required time per iteration falls only a little with k: about 0–20% lower for criteria (b)–(d), more for (a). The number of layers per iteration falls much faster: 13 → 7 → 5 → 4.
  - So the time allowed per layer grows. For example at p = 0.003, criterion (c), T = 12 µs: 4.8 ns per layer for k = 1, 8.7 ns for k = 2, 14.5 ns for k = 4.
  - A k-round layer needs about k times the round-step hardware (k × 72 CNUs and the matching VNUs), if each layer is done in one step. Whether that trade pays off depends on the Test 2c clock and area numbers, which this software test does not measure.
- **Reference check:** the k = 1 targets (int4.2.8) are close to the Test 1e targets from the 1b float trace. At p = 0.003, T = 12 µs, (b)/(c)/(d) are 13 / 63 / 327 ns here vs 13 / 65 / 328 ns in 1e. (a) differs more (277 vs 255), because the queue max is sensitive.

## Not tested
- **p = 0.001** (not in the task) and the windowed W12_C8 / W8_C4 settings. All results here are for the full 12-round decode (one job = 13 rounds), not the 1d windows.
- **Hardware for k > 1:** no RTL or synthesis. The time per layer above is a budget derived from the traces, not a measured hardware number.
- **Other groupings:** only consecutive groups starting at round 0. Other groupings (for example a smaller first group, or interleaved rounds) were not run.
- **Statistical power:** at p = 0.002 the failure counts are small; see the McNemar p-values above.

## Addendum (2026-11-14, run for Test 2d): p = 0.001
- **Setup:** same script and settings, 600,000 shots (the Test 1b p = 0.001 shots: batch 1,000 × 8 workers), `run_test1f.sh p001`.
- **Reproduction check:** k = 1 and flood again equal the Test 1b int4.2.8 sweep and flood traces on all 600,000 shots (0 differ).

| | k = 1 | k = 2 | k = 3 | k = 4 | flood |
|---|---|---|---|---|---|
| Logical failures | 2 (3.3e-6) | 0 | 1 | 1 | 1 |
| Not converged | 0 | 0 | 0 | 0 | 0 |
| Mean iterations | 5.52 | 5.84 (+5.8%) | 6.13 (+11.1%) | 6.31 (+14.3%) | 6.67 (+20.8%) |
| p99 iterations | 21 | 22 | 23 | 23 | 24 |
| p99.9 iterations | 41 | 45 | 44 | 45 | 54 |
| Largest t_iter (ns), T = 12 µs, a / b / c / d | 1487 / 493 / 1163 / 2125 | 1403 / 475 / 1165 / 2007 | 1337 / 432 / 1079 / 1918 | 1299 / 415 / 878 / 1856 | 1230 / 382 / 870 / 1761 |

- **Accuracy:** with 0–2 failures, the paired comparison is uninformative (all McNemar p ≥ 0.5).
- **Iterations:** the slowdown with k is the same pattern as at p = 0.002 and 0.003, but smaller.
