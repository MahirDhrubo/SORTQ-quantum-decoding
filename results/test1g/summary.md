# Test 1g: red-black round order

## Setup
- **Decoder:** same as Test 1b / 1f int4.2.8: alpha = 1, S = 1, gamma0 = 0.125, gamma interval (−0.226, 0.622), pre_iter 80, 300 legs × 60 (cap 18,080).
- **Circuit and shots:** 12-round circuit, X decoder. The shots are the Test 1b shots (seed 20261111, same batch × workers): p = 0.003: 168,000; p = 0.002: 600,000. All schedules decode the same shots.
- **Schedules:** only the layer order changes. relay_bp processes the layers in increasing id order (`run_layered_iteration`), so the order is set by the layer id of each check row (r = its round):

  | Schedule | Layer id | Order |
  |---|---|---|
  | (1) sweep | r | 13 layers, rounds 0, 1, …, 12 (= Test 1b) |
  | (2) rb13 | position of r in the order | 13 layers, one round each: 0, 2, 4, 6, 8, 10, 12, 1, 3, 5, 7, 9, 11 |
  | (3) rb2 | r mod 2 | 2 layers: {even rounds}, {odd rounds} |

- **H check (12-round H, measured):** 8,784 error columns.
  - 0 touch two even rounds, and 0 touch two odd rounds.
  - 2,736 columns touch one round; 6,048 touch two consecutive rounds (home h and h + 1).
  - So the checks of one parity never share an error, and processing the even (or odd) rounds one after another gives the same result as processing them together. (2) and (3) should give identical results.
- **Real-time targets:** test1e_criteria.py, unchanged model, run on the three traces: T = 12 and 8 µs, K = 18,080, overhead 200 ns, 10^7 jobs.
- **Compute:** server, 8 workers at nice 10. p = 0.003 took 23 min and p = 0.002 took 24 min.
- **Files:** scripts `scripts/test1g_order.py`, `scripts/test1g_criteria.py`, `scripts/run_test1g.sh`. Traces `p{p}_{sweep,rb13,rb2}.npz` (Test 1b format plus a per-shot CRC of the decoding), `report.json`, `hcheck.json`, `criteria/criteria.json`.

## Results (all measured)

### Are (2) and (3) identical?

**Yes, on every shot.** Compared shot by shot (decoding by CRC-32 of the full 8,784-bit decoding):

| p | Shots | Decoding differs | Iterations differ | Success differs | Logical failure differs |
|---|---|---|---|---|---|
| 0.003 | 168,000 | 0 | 0 | 0 | 0 |
| 0.002 | 600,000 | 0 | 0 | 0 | 0 |

The sweep equals the Test 1b int4.2.8 sweep trace on every shot: 0 of 168,000 / 600,000 differ in iterations, success or logical failure.

### Logical error rate

| p | (1) sweep | (2) rb13 | (3) rb2 |
|---|---|---|---|
| 0.003 (168,000) | 128 (7.62e-4) | 138 (8.21e-4) | 138 (8.21e-4) |
| 0.002 (600,000) | 19 (3.17e-5) | 22 (3.67e-5) | 22 (3.67e-5) |

Not converged (all hit the 18,080 cap):

| p | (1) | (2) | (3) |
|---|---|---|---|
| 0.003 | 9 | 10 | 10 |
| 0.002 | 3 | 2 | 2 |

### Paired comparison with (1)

| p | Schedule | Both fail | Only (1) fails | Only this one fails | McNemar p |
|---|---|---|---|---|---|
| 0.003 | rb13 / rb2 | 57 | 71 | 81 | 0.47 |
| 0.002 | rb13 / rb2 | 5 | 14 | 17 | 0.72 |

### Iterations per shot

| p | Schedule | Mean | vs sweep | p50 | p90 | p99 | p99.9 | Max |
|---|---|---|---|---|---|---|---|---|
| 0.003 | sweep | 23.53 | — | 11 | 27 | 217 | 1,264 | 18,080 |
| 0.003 | rb13 = rb2 | 24.11 | +2.5% | 11 | 25 | 219 | 1,538 | 18,080 |
| 0.002 | sweep | 10.25 | — | 8 | 17 | 39 | 216 | 18,080 |
| 0.002 | rb13 = rb2 | 9.85 | −3.9% | 7 | 15 | 37 | 216 | 18,080 |

### Largest t_iter (ns per iteration, test1e_criteria model)

| p | Schedule | T = 12 µs: a / b / c / d | T = 8 µs: a / b / c / d |
|---|---|---|---|
| 0.003 | sweep | 277 / 13 / 63 / 327 | 184 / 11 / 60 / 258 |
| 0.003 | rb13 = rb2 | 282 / 11 / 62 / 308 | 187 / 9 / 59 / 240 |
| 0.002 | sweep | 626 / 56 / 162 / 631 | 417 / 43 / 133 / 569 |
| 0.002 | rb13 = rb2 | 524 / 49 / 134 / 628 | 349 / 37 / 111 / 568 |

- **What binds:** (a) is bound by the queue max in every row; (b)–(d) by the p99.9 latency.
- **rb13 and rb2 rows are equal** because the traces are identical shot by shot.

## What this means
- **Red-black is exactly a 2-layer schedule here.** Because no error touches two rounds of the same parity, the 13-step order 0, 2, …, 12, 1, …, 11 and the 2-layer {even}, {odd} schedule are bit-identical. Measured: 0 differences on 768,000 shots, including the full decoding.
- **Accuracy:** the logical error rate does not change measurably: +8% and +16% more failures, McNemar p = 0.47 and 0.72.
- **Iterations:**
  - In the mean, red-black is about the same as the sweep: +2.5% at p = 0.003, −3.9% at p = 0.002. p50 and p90 are equal or lower.
  - The far tail is longer at p = 0.003: p99.9 is 1,538 vs 1,264.
  - This is unlike the grouped schedules of Test 1f (k = 2: +16% / +10.5%; flood: +38% / +30%). With only 2 layers, red-black converges almost as fast as the 13-layer sweep.
- **Speed targets per iteration** are within about 0–20% of the sweep, lower in most rows, because of the longer tail: for example (c) at p = 0.002 is 134 vs 162 ns at T = 12 µs.
  - For hardware that processes one layer per step, the 2-layer schedule needs only 2 steps per iteration instead of 13.
  - Each step then covers 7 (even) or 6 (odd) rounds, so it needs about 6–7× the round-step hardware for one step per layer. That would be about the same parallelism as k = 7, but with sweep-like convergence instead of k = 7's slowdown.
  - The trade is not measured here (software only).

## Not tested
- **p = 0.001**, and the windowed W12_C8 / W8_C4 settings (full 12-round decode only).
- **Hardware:** no RTL or synthesis for a red-black engine.
- **Other orders:** odd rounds first, or other colorings.
- **Statistical power:** at p = 0.002 there are only 19–22 failures per schedule.
