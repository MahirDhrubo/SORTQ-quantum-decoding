# Test 1h: accuracy of the red-black order (rb13 int4.2.8) at p = 0.003

## Setup
- **Decoder:** as Test 1g. relay_bp RelayDecoderF32; alpha = 1, S = 1, pre_iter 80, 300 legs × 60 (cap 18,080); gamma generator seed 0. 12-round gross-code X decoder.
  - In int4.2.8, γ is rounded to the 1/8 grid: g8 = ⌊8γ + ½⌋. That is relay's `QuantFormat::round`, for both gamma0 and the drawn γ.
  - The round order is set through the layer ids: the id of a round-r check is r's position in the order.
- **Shots:**
  - Steps 1 and 3 use the Test 1b shots (seed 20261111, 8 × 500 per batch at p = 0.003 and 8 × 1000 at p = 0.002).
  - Step 2 uses fresh shots: seed 20261120, 168,000 at p = 0.003, same batch size.
  - Every setting within a step decodes the same shots, so all comparisons are paired.
- **Identity check (measured):** Step 1 also decoded rb13 int4.2.8. Against the Test 1g rb13 trace, it differs on 0 shots in iterations, success, logical failure and decoding CRC. So these are the Test 1b / 1g shots.
- **Settings (step 2):**

  | Name | Messages | Order | gamma0 (g8 in leg 0) | Interval | g8 set |
  |---|---|---|---|---|---|
  | baseline | int4.2.8 | rb13: 0, 2, …, 12, 1, …, 11 | 0.125 (1) | (−0.226, 0.622) | −2 … 5 |
  | g0 = 0.0625 | int4.2.8 | rb13 | 0.0625 (**1**: 8 × 0.0625 = 0.5 rounds up) | original | −2 … 5 |
  | g0 = 0.25 | int4.2.8 | rb13 | 0.25 (2) | original | −2 … 5 |
  | interval (−0.15, 0.5) | int4.2.8 | rb13 | 0.125 (1) | (−0.15, 0.5) | −1 … 4 |
  | interval (−0.3, 0.7) | int4.2.8 | rb13 | 0.125 (1) | (−0.3, 0.7) | −2 … **6** |
  | odd-first | int4.2.8 | 1, 3, …, 11, 0, 2, …, 12 | 0.125 (1) | original | −2 … 5 |

- **Choice rule:** fewest failures in step 2; ties go to fewer mean iterations. It was applied automatically by `test1h_report.py pick`.
- **McNemar:** exact two-sided binomial test on the discordant shots (only A vs only B), as in Tests 1b–1g.
- **Run:** server, 8 workers, nice 10, tmux sortq_queue window t1h (`scripts/run_test1h.sh`). A 2,000-shot smoke run of the whole chain came first.
  - Wall time: step 1 10.6 min, step 2 42.6 min, step 3 8.4 + 9.3 min, criteria 14 s.

## Results

### Step 1: rb13 with float messages (Test 1b shots, p = 0.003, 168,000; measured)
| Design | Failures | LER | Mean iterations | p99.9 | Not converged |
|---|---|---|---|---|---|
| float flood (Test 1b) | 111 | 6.61e-4 | 32.85 | 2015 | 17 |
| float sweep (Test 1b) | 124 | 7.38e-4 | 24.15 | 1599 | 6 |
| **rb13 float** | **124** | 7.38e-4 | **23.57** | 1496 | 9 |
| rb13 int4.2.8 (Test 1g) | 138 | 8.21e-4 | 24.11 | 1538 | 10 |
| int4.2.8 flood (Test 1b) | 106 | 6.31e-4 | 32.51 | 1979 | 18 |

| Pair (A vs B) | Both | Only A | Only B | McNemar p |
|---|---|---|---|---|
| rb13 float vs float flood | 50 | 74 | 61 | 0.30 |
| rb13 float vs float sweep | 52 | 72 | 72 | 1.0 |
| rb13 int4.2.8 vs rb13 float | 63 | 75 | 61 | 0.26 |
| rb13 int4.2.8 vs float flood | 59 | 79 | 52 | **0.023** |

- With float messages the red-black order fails exactly as often as the float sweep (124 vs 124, p = 1.0). It is not significantly worse than float flood (p = 0.30), and it uses the fewest iterations (23.57).
- The order is not the problem. The step from rb13 float to rb13 int4.2.8 (+14 failures) is also not significant on its own (p = 0.26). Only the two steps together reach p = 0.023 against float flood.

### Step 2: tuning on fresh shots (seed 20261120, p = 0.003, 168,000; measured)
| Setting | Failures | Ratio vs float flood | Both / only setting / only flood | McNemar p | Mean iterations | p99.9 | Not converged |
|---|---|---|---|---|---|---|---|
| float flood (reference) | 113 | 1 | — | — | 32.93 | 1962 | 20 |
| baseline rb13 int4.2.8 | 118 | 1.04 | 48 / 70 / 65 | 0.73 | 23.60 | 1476 | 13 |
| g0 = 0.0625 | 118 | 1.04 | 48 / 70 / 65 | 0.73 | 23.60 | 1476 | 13 |
| g0 = 0.25 | **163** | **1.44** | 54 / 109 / 59 | **1.4e-4** | 21.05 | 1481 | 11 |
| **interval (−0.15, 0.5)** | **109** | **0.96** | 49 / 60 / 64 | 0.79 | 26.40 (+12%) | 1873 | 30 |
| interval (−0.3, 0.7) | 116 | 1.03 | 48 / 68 / 65 | 0.86 | 22.95 | 1453 | 4 |
| odd-first | 121 | 1.07 | 51 / 70 / 62 | 0.54 | 23.62 | 1434 | 14 |

- **g0 = 0.0625 is the baseline:** it differs on 0 shots in iterations, success, failure and decoding, as the grid rounding predicts (g8 = 1 either way).
- **On fresh shots the baseline is not worse than float flood:** 118 vs 113, p = 0.73. On the Test 1b shots it was 138 vs 111.
- **Chosen: interval (−0.15, 0.5)**, with 109 failures, the fewest.
  - Its lead over the baseline (109 vs 118) and over interval (−0.3, 0.7) (116) is within noise; none of these differ significantly from float flood.
  - It costs +12% mean iterations, a longer tail (p99.9 1873 vs 1476) and more non-converged shots (30 vs 13).
- **g0 = 0.25 is clearly worse:** +44% failures against float flood, p = 1.4e-4.

### Step 3: chosen setting on the Test 1b shots (measured)
| p | Shots | Interval (−0.15, 0.5) | rb13 baseline (Test 1g) | float flood | int4.2.8 sweep |
|---|---|---|---|---|---|
| 0.003 | 168,000 | **128** (7.62e-4), mean 26.67 it, p99.9 1974, 27 not converged | 138, mean 24.11 | 111, mean 32.85 | 128 |
| 0.002 | 600,000 | **25** (4.17e-5), mean 10.35 it, p99.9 231, 16 not converged | 22, mean 9.85 | 26, mean 13.14 | 19 |

| p | Pair (A vs B) | Both | Only A | Only B | McNemar p |
|---|---|---|---|---|---|
| 0.003 | chosen vs float flood | 62 | 66 | 49 | 0.14 |
| 0.003 | chosen vs rb13 baseline | 75 | 53 | 63 | 0.40 |
| 0.003 | chosen vs int4.2.8 sweep | 59 | 69 | 69 | 1.0 |
| 0.002 | chosen vs float flood | 12 | 13 | 14 | 1.0 |
| 0.002 | chosen vs rb13 baseline | 11 | 14 | 11 | 0.69 |
| 0.002 | chosen vs int4.2.8 sweep | 9 | 16 | 10 | 0.33 |

- **At p = 0.003:** 128 vs 111 for float flood, p = 0.14, so no longer significant (baseline: p = 0.023). It matches the int4.2.8 sweep exactly (128 vs 128).
  - The improvement over the baseline (128 vs 138) is not significant (p = 0.40).
- **At p = 0.002:** 25 vs 26 for float flood (p = 1.0).

### Real-time targets (test1e_criteria, T = 12 µs, step-3 traces; computed from measured traces)
Largest ns per 13-round iteration, criteria a / b / c / d:

| p | Interval (−0.15, 0.5) | rb13 baseline (Test 1g) | engine_top_rb at 61.88 ns meets: chosen | baseline |
|---|---|---|---|---|
| 0.003 | 230 / 8 / **57** / 266 | 282 / 11 / 62 / 308 | (a), (d) | (a), **(c)**, (d) |
| 0.002 | 364 / 24 / 78 / 527 | 524 / 49 / 134 / 628 | (a), (c), (d) | (a), (c), (d) |

- The longer iteration tail lowers every target by 13–42%.
- At p = 0.003, the chosen setting loses criterion (c) (p99.9 latency under 1 ms): it needs 57 ns, and the engine runs 61.88 ns. The baseline meets (c), with 62 ns needed.

### Hardware changes for the chosen setting (interval (−0.15, 0.5))
| Item | Change |
|---|---|
| gamma_src g8 grid thresholds (LFSR mode) | `GMIN` −2 → **−1**, `NBINS` 8 → **6**, `CUM` {187, 791, 1395, 1999, 2603, 3207, 3811, 4096} → **{551, 1339, 2127, 2914, 3702, 4096}** (probabilities 13.5%, 19.2% × 4, 9.6%; cumulative, rounded to 1/4096). Parameters set at the instantiation in engine_top_rb (it now passes only LFSR_MODE and SEED). |
| gamma0 constant | unchanged: g8 = 1 (`G0` = 1, the `4'sd1` leg-0 constant in engine_top_rb) |
| order tables (rb_pkg: gating, hazard distance) | unchanged (rb13 order) |
| G memory field (g8 + 2, 3 bits) | unchanged: g8 + 2 ∈ {1 … 6} fits |
| gamma_src LOAD mode (closed-loop simulation) | none (it loads the software g8) |

- **Datapath:** unchanged. The bias (8 − g8)·L0 + g8·M(t−1) gets 8 − g8 ∈ [4, 9], inside the current [3, 10]. g8 still fits the 4-bit signed lane output, so no widths change. This is a parameter change only.
- **For reference, the other settings:**
  - Interval (−0.3, 0.7) would need g8 = 6, so the G field grows to 4 bits.
  - g0 = 0.25 changes G0 and the leg-0 constant to 2.
  - Odd-first needs regenerated gating tables (rb_pkg); the spacing between steps that share an error stays 6.

## What this means
- **The red-black order itself does not hurt accuracy.** In float it fails exactly as often as the float sweep, with fewer iterations.
- **The p = 0.003 gap for rb13 int4.2.8 (138 vs 111, p = 0.023) mostly belongs to the Test 1b shot set.** On 168,000 fresh shots the same decoder is 118 vs 113 (p = 0.73). Two smaller, individually non-significant steps (int4.2.8 quantization, then the shot set) produced the significant result. 
- **No tuned setting is significantly better than the baseline.**
  - Interval (−0.15, 0.5) has the fewest failures in both runs (109 fresh, 128 on the Test 1b shots, vs 118 / 138). It brings the Test 1b comparison to float flood down to p = 0.14.
  - Neither improvement is significant (p = 0.40 against the baseline on the same shots).
  - It costs +11–12% mean iterations and a heavier tail. That cuts the real-time targets enough to lose criterion (c) at p = 0.003 for engine_top_rb.
- **gamma0 = 0.25 is clearly harmful** (+44% failures).
- **Recommendation:** keep the original settings for the hardware and the paper. Report rb13 int4.2.8 with the fresh-shot result (118 vs 113, p = 0.73) next to the Test 1b one, plus the float diagnostic. If accuracy at p = 0.003 matters more than criterion (c), the narrower interval is a parameter-only change.

## Not tested
- **Several fresh-shot sets:** only one fresh set (seed 20261120) was run. How much the failure count moves between shot sets at 168,000 shots was not measured beyond the two sets here (baseline 138 vs 118).
- **Other intervals, gamma0 values off the 1/8 grid** (for example gamma0 = 0.0625 with a finer grid), and S ≠ 1: not run.
- **Odd-first or narrower-interval decoding in RTL simulation:** not run; the hardware table above is derived, not simulated.
- **p = 0.001 and T = 8 µs targets** for the chosen setting: not run.

Files: `scripts/test1h.py`, `test1h_report.py`, `test1h_criteria.py`, `run_test1h.sh`; results in `results/test1h/` (`step1/`, `step2/`, `step3/`, `chosen.json`, `criteria/`, `report.json`, `run.log`).
