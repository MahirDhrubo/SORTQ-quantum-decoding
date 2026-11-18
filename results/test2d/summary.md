# Test 2d: resource model from the measured Test 2c numbers

## Setup
- **Inputs (all measured earlier, post-route, xcvu19p, 4,085,760 LUT):**
  - `hw/synth/results.json` (Test 2c runs plus 6 calibration runs added for 2d, below);
  - Test 1f per-k iteration traces and criteria;
  - Test 1e W12_C8 criteria.
- **Model script:** `scripts/test2d_model.py` → `model.json`, `pareto.csv`. No number in the tables is typed by hand.
- **X decoder of the 12-round circuit** (H from `dem_tools.xdecoder_problem`, measured):
  - 936 checks: 792 of degree 35, 72 of degree 25, 72 of degree 16;
  - 8,784 errors: degree 2: 864, degree 3: 5,328, degree 4: 864, degree 5: 864, degree 6: 864;
  - 30,672 edges.
- **Added for 2d** (same harness and flow as 2c, 2.5 ns, post-route):
  - cnu at degrees 16 and 25; vnu at degrees 2, 3, 4 and 5. 2c had only CNU degree 35 and VNU degree 6.
  - Test 1f decoding at p = 0.001 (k1..k4, flood; 600,000 Test 1b shots, 8 workers at nice 10). k1 and flood reproduce the Test 1b int4.2.8 traces on all 600,000 shots (0 differ). Without this run there would be no p = 0.001 targets for k > 1.
- **IBM reference** (as given in the task): about 2.1M LUT (51.6%) for the 12 + 1-round X decoder, fully parallel, flooding. Its time per iteration is taken as 24 ns, the value used in Test 1e.
- **Word widths:** all our blocks are int4.2.8 (4-bit message magnitude, 7-bit marginal / bias, 4-bit g8).

## Results

### 1. Calibration: the fully parallel X decoder built from our blocks

Measured block sizes (post-route LUT / FF per instance):

| Block | Degree | Count | LUT each | FF each | LUT total |
|---|---|---|---|---|---|
| cnu | 35 | 792 | 810 | 191 | 641,520 |
| cnu | 25 | 72 | 551 | 140 | 39,672 |
| cnu | 16 | 72 | 353 | 94 | 25,416 |
| vnu | 2 | 864 | 167 | 26 | 144,288 |
| vnu | 3 | 5,328 | 195 | 31 | 1,038,960 |
| vnu | 4 | 864 | 279 | 36 | 241,056 |
| vnu | 5 | 864 | 321 | 41 | 277,344 |
| vnu | 6 | 864 | 364 | 46 | 314,496 |

| Total | LUT | vs IBM 2.1M |
|---|---|---|
| CNUs (936) | 706,608 | — |
| VNUs (8,784) | 2,016,144 | — |
| **CNU + VNU (standalone blocks)** | **2,722,752 (66.6% of device)** | **1.30×** |
| Scaled by the in-context factors (derived; see below) | ≈2.47M | ≈1.18× |
| + one gamma lane per error (71.0 LUT each, measured in engine_top_pf2) | 3,346,575 | 1.59× |

Not in the LUT totals: FFs, which are 168,120 (CNU) + 293,904 (VNU), plus 61,488 for M(t−1) per error (7 bits each).

- **In-context factors** (measured inside round_step_pf2): a CNU of degree 35 is 671 LUT there, against 810 standalone (0.83×). A VNU averages 211.5 LUT there (vnu_nosat), against 226 for standalone vnu weighted to the same degree mix (0.93×). The standalone harness keeps every input live, so less logic is optimized away.
- **Where the difference to IBM comes from** (our side only; I don't have IBM's per-block breakdown):
  - **VNUs are 74% of our total.** A linear fit of VNU LUT against degree (measured points, degrees 2–6) gives about 57 LUT fixed per VNU plus about 52 LUT per edge. The fixed part is mostly the memory term: bias = round(((8 − g8)·prior + g8·M(t−1)) / 8), with two small products, the rounding and the saturator. That is about 0.50M LUT over 8,784 VNUs (derived from the fit, not synthesized separately).
  - **Generic inputs:** our VNU and CNU take per-edge masks and init / late gating as inputs, because the engine reuses them across rounds. A fixed-graph decoder can hard-wire these. Not measured separately.
  - **Gamma:** our engine draws g8 with one 16-bit LFSR lane per error position (71 LUT). A fully parallel copy of that is +624k LUT. IBM's gamma source is not known to me. The base comparison leaves gamma out.
  - IBM's word widths and saturation choices were not checked against ours.

### 2. SORTQ engine costs, k rounds per layer

- **Model (as specified):** LUT(k) = engine LUT at k = 1 + (k − 1) × round_step LUT. Shared blocks and state memory are unchanged.
- **Inputs:** k = 1 is measured (post-route, at the confirmed clock); k > 1 is estimated.
- **Second column:** also adds (k − 1) × the 720 gamma lanes, in case one init step must draw for k rounds.
- **Lower bound:** a k-round layer updates 720k + 504 errors, not 1,224k. Each extra round over-counts 504 VNUs × 211.5 LUT ≈ 106.6k LUT, so the model is an upper bound.

| Engine (measured k = 1) | Shared LUT | round_step LUT | k = 1 | k = 2 | k = 3 | k = 4 | k = 4 with extra lanes | k = 4 lower bound |
|---|---|---|---|---|---|---|---|---|
| engine_top_pf2, VNU_PASSES 1 | 149,096 | 301,131 | **450,227 (11.0%)** | 751,358 (18.4%) | 1,052,489 (25.8%) | 1,353,620 (33.1%) | 1,507,019 | ≈1,033,801 |
| engine_top_pf2, VNU_PASSES 2 | 162,870 | 212,871 | **375,741 (9.2%)** | 588,612 (14.4%) | 801,483 (19.6%) | 1,014,354 (24.8%) | 1,163,265 | — |
| engine_top_pf, VNU_PASSES 1 (as asked) | 152,827 | 291,965 | **444,792 (10.9%)** | 736,757 (18.0%) | 1,028,722 (25.2%) | 1,320,687 (32.3%) | 1,474,896 | — |

- **FF:** 127,677 → 255,663 (pf2 P1, k = 1 → 4); 119,816 → 225,155 (pf2 P2).
- **LUTRAM:** 19,096 at every k.

### 3. Memory variants (analytic)

**Measured basis.** In engine_top_pf2 every LUTRAM field costs 0.5717 LUTRAM per bit per slot (12 slots). This is the same for all six fields, e.g. v2c_o0: 4,528 LUTRAM for 7,920 bits per slot. The total today is 33,408 bits per slot (19,096 LUTRAM).

| Variant | Bits per slot | LUTRAM | Added logic (estimate) | Expected effect on the critical path |
|---|---|---|---|---|
| (a) compressed c2v_o1 per check: min1, min2, min1 index (6 bits), 13 signs = 27 bits per check | 4,680 → 1,944 (**−2,736**, −8.2% of all state) | **−1,564** | 936 edge decoders (6-bit index = constant compare, 4-bit 2:1 mux) ≈ 4.7k LUT; the CNU already outputs min1 / min2 / index | +~2 logic levels on the memory → VNU (late c2v) path, which is not critical today. Net LUT about +3.1k. |
| (b) v2c not stored, recomputed as sat(M − c2v) at the CNU input | −12,600 (v2c_o0 + c2v_o1), +3,528 (compressed old c2v of all 35 edges: 49 bits per check), +4,896 (marginals stored unsaturated, 9 instead of 7 bits) = **−4,176** (−12.5%) | **−2,387** | 1,584 recompute paths (22 offset-0 edges × 72): c2v decode + 9-bit subtract + saturate + sign-magnitude ≈ 20 LUT each ≈ 31.7k LUT | Adds about 4–6 levels in front of the CNU on the memory → CNU path. That path was the critical path of the BRAM engine (17 levels at 9.73 ns) and sits next to the current VNU → CNU limit. Expect a lower clock, unless the read is moved one cycle earlier (possible because the round order is static). |
| (c) per-error prior RAM instead of the 10 × 13 file | +6,120 per row (720 cur + 504 prev × 5 bits), 13 rows = 79,560 bits | **+3,499** | −536 LUT, −650 FF (register file); the stage A / A2 / B copies (−3,600 FF) are no longer needed | Each error gets its own prior wire from a prefetched memory read, like the other fields; no broadcast. No effect expected; that path was removed in pf / pf2 anyway. |

- **(b) is not bit-exact with the stored 7-bit marginal.** In Test 1b (int4.2.8), 43–54% of marginal updates saturate. Recomputing v2c needs the unsaturated total: |total| ≤ 63 + 6 × 15 = 153, which fits in 9 bits signed. It also needs the c2v used in that error's last update, which is why (b) adds the compressed c2v of all 35 edges.
- **(c) is not needed for this circuit:** its per-error priors take only 19 distinct values, all covered by the 10 × 13 file. (c) is the cost of supporting arbitrary non-uniform noise.

### 4. Pareto table (`pareto.csv`)

- **ns per iteration (13-round decode):** layers × (VNU_PASSES + 1) × period, with the overlapped convergence check. Layers are 13 / 7 / 5 / 4 for k = 1 / 2 / 3 / 4. W12_C8 (k = 1 only): 12 steps.
- **Criteria met:** a / b / c / d at T = 12 µs. Each design uses its own schedule's Test 1f trace (k1..k4; flood for IBM; int4.2.8). W12_C8 uses the Test 1e targets from the Test 1d windows (F32, T = 8 µs; p = 0.002 and 0.003 only).
- **Clocks:** measured for k = 1; **for k > 1 the k = 1 clock is assumed**. IBM: 24 ns as used in Test 1e.

| Design | k | Passes | LUT (% dev) | Clock | ns / iter 13 rounds | 13 rounds, p = 0.001 / 0.002 / 0.003 | ns / iter W12_C8 | W12_C8, p = 0.002 / 0.003 |
|---|---|---|---|---|---|---|---|---|
| IBM fully parallel (flood) | — | — | 2,100,000 (51.6%) | as published | 24.0 | abcd / abcd / acd | — | n/a |
| SORTQ pf2 | 1 | 1 | 450,227 (11.0%) | 146.2 MHz measured | 177.8 | abcd / ad / ad | 164.2 | ad / none |
| SORTQ pf2 | 2 | 1 | 751,358 (18.4%) | 146.2 MHz assumed | 95.8 | abcd / acd / ad | n/a | n/a |
| SORTQ pf2 | 3 | 1 | 1,052,489 (25.8%) | 146.2 MHz assumed | 68.4 | abcd / acd / ad | n/a | n/a |
| SORTQ pf2 | 4 | 1 | 1,353,620 (33.1%) | 146.2 MHz assumed | 54.7 | abcd / acd / **acd** | n/a | n/a |
| SORTQ pf2 | 1 | 2 | 375,741 (9.2%) | 130.7 MHz measured | 298.4 | abcd / ad / d | 275.4 | d / none |
| SORTQ pf2 | 2 | 2 | 588,612 (14.4%) | 130.7 MHz assumed | 160.7 | abcd / ad / ad | n/a | n/a |
| SORTQ pf2 | 3 | 2 | 801,483 (19.6%) | 130.7 MHz assumed | 114.8 | abcd / ad / ad | n/a | n/a |
| SORTQ pf2 | 4 | 2 | 1,014,354 (24.8%) | 130.7 MHz assumed | 91.8 | abcd / acd / ad | n/a | n/a |
| SORTQ pf (as asked) | 1 | 1 | 444,792 (10.9%) | 135.9 MHz measured | 191.4 | abcd / ad / ad | 176.6 | ad / none |
| SORTQ pf | 2 | 1 | 736,757 (18.0%) | 135.9 MHz assumed | 103.0 | abcd / acd / ad | n/a | n/a |
| SORTQ pf | 3 | 1 | 1,028,722 (25.2%) | 135.9 MHz assumed | 73.6 | abcd / acd / ad | n/a | n/a |
| SORTQ pf | 4 | 1 | 1,320,687 (32.3%) | 135.9 MHz assumed | 58.9 | abcd / acd / ad | n/a | n/a |

Largest t_iter at T = 12 µs (ns per iteration), from the Test 1f traces:

| Schedule | p = 0.001 (a / b / c / d) | p = 0.002 | p = 0.003 |
|---|---|---|---|
| k1 | 1487 / 493 / 1163 / 2125 | 626 / 56 / 162 / 631 | 277 / 13 / 63 / 327 |
| k2 | 1403 / 475 / 1165 / 2007 | 581 / 48 / 131 / 588 | 261 / 11 / 61 / 293 |
| k3 | 1337 / 432 / 1079 / 1918 | 373 / 35 / 104 / 571 | 234 / 9 / 58 / 266 |
| k4 | 1299 / 415 / 878 / 1856 | 356 / 35 / 102 / 567 | 202 / 9 / 58 / 260 |
| flood | 1230 / 382 / 870 / 1761 | 345 / 31 / 93 / 552 | 235 / 9 / 58 / 257 |

**p = 0.001, Test 1f traces (measured, 600,000 shots):**

| | k1 | k2 | k3 | k4 | flood |
|---|---|---|---|---|---|
| Logical failures | 2 | 0 | 1 | 1 | 1 |
| Mean iterations | 5.52 | 5.84 | 6.13 | 6.31 | 6.67 |
| p99.9 iterations | 41 | 45 | 44 | 45 | 54 |
| Not converged | 0 | 0 | 0 | 0 | 0 |

## What this means
- **Calibration.** Built from our measured blocks, a fully parallel X decoder is 1.30× IBM's LUT count (1.18× with the in-context factors), without gamma. Our blocks are therefore not unusually small, and the SORTQ saving comes from the schedule, not from cheap blocks.
  - The VNU dominates (74%), and its memory term is roughly a quarter of it (fit estimate).
- **SORTQ at k = 1 is 4.7× smaller than IBM** (450k vs 2.1M LUT) at 7.4× the time per iteration (177.8 vs 24 ns).
  - It meets every criterion at p = 0.001, and (a) and (d) at p = 0.002 and 0.003.
  - It misses (b) (p99.9 < 100 µs) at p = 0.002 and 0.003, which IBM meets at p = 0.002 (IBM also misses (b) at p = 0.003).
- **Larger k buys time per iteration roughly in proportion to its area** (estimates; the k = 1 clock is assumed). k = 2 roughly halves the time (95.8 ns) for +67% LUT; k = 4 reaches 54.7 ns at 1.35M LUT (64% of IBM). That is the first SORTQ point to meet (c) at p = 0.003.
  - (b) at p ≥ 0.002 needs at most 35–56 ns (p = 0.002) or 9–13 ns (p = 0.003). No SORTQ point here reaches it; only IBM meets (b), and only at p = 0.002.
- **VNU_PASSES 2** is the smallest design at every k, but slower per iteration. P2 at k = 4 (1.01M LUT, 91.8 ns) is close to P1 at k = 2 (0.75M LUT, 95.8 ns), so P1 dominates for k > 1.
- **Memory variants:**
  - (a) saves 1.6k LUTRAM for about 4.7k LUT of decoders: about neutral.
  - (b) saves 2.4k LUTRAM for about 32k LUT and a likely clock loss: not worth it in LUTRAM.
  - (c) costs 3.5k LUTRAM for arbitrary per-error priors: cheap.
  - State memory is only 2% of the device, so none of the three changes the Pareto picture. They would matter in a BRAM design, where the fields are width-limited (464 BRAM36).

## Not tested
- **k > 1 engines:** no RTL or synthesis. LUT is the k × round_step model, an upper bound. The clock is assumed equal to k = 1; a k-round step has k× the wiring, so the real clock is probably lower.
- **W12_C8 for k > 1 and for IBM:** no per-k window traces. W12_C8 at p = 0.001: no Test 1d trace.
- **IBM:** only the total (2.1M, 51.6%) and the 24 ns per iteration were used; no per-block comparison. The base calibration includes no gamma source; IBM's is unknown.
- **Memory variants:** analytic only; the LUT numbers of the added logic are estimates, not synthesized. Variant (b) bit-exactness with the 9-bit marginal is argued from value ranges, not simulated.
- **VNU memory-term cost:** derived from a fit over degrees, not measured with the term removed.
- **Power** and BRAM variants of the k > 1 engines.

## Update (2026-11-14): re-synthesized engine with the Test 3d fixes
- Re-run with `REF_RUN=engine_top_pf2fix_p1_lutram_fmax` → `results/test2d/refix/` (model.json, pareto.csv).
- **Changed:** SORTQ pf2 P1:
  - LUT 450,227 → 448,213 at k = 1 (k = 2–4: −2.3k to −2.8k);
  - clock 146.2 → 138.1 MHz;
  - ns per 13-round iteration 177.8 → 188.2 at k = 1 (k = 2 / 3 / 4: 101.4 / 72.4 / 57.9); W12_C8 164.2 → 173.8.
- **Unchanged:** the criteria met in every row, and all other rows. Details in `hw/synth/summary_2c.md`, section "2c re-synthesis (3d fixes)".
