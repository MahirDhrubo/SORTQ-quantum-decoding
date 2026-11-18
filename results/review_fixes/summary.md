# Review fixes: continuous decoding, exact queue model, hardware LFSRs, statistics

No RTL was changed. New scripts and test benches only. Run on the server (nice 10), tmux sortq_queue:
- **Lane A:** windows rvA, `scripts/run_review_fixes.sh`, 2026-11-16 20:31 → 2026-11-17 02:25 CST.
- **Lane B:** window rvB.

Labels:
- **measured:** decoder or RTL simulation output;
- **computed:** a queue model or statistics over measured traces;
- **assumption:** stated where it is made.

## Summary
| Item | Result |
|---|---|
| A.1 Windows W12_C8 vs global, 36 rounds, red-black int4.2.8 | p = 0.003: 73 vs 63 failures (ratio 1.16, 95% CI 0.89–1.51, p = 0.33). p = 0.002: 31 vs 34 (0.91, 0.65–1.28, p = 0.72). **Windowing is not distinguishable from global decoding.** |
| A.2 Queue, T = C = 8 µs, exact cycles | p = 0.003: util 0.376, **p99.9 2.04 ms**, queue max 426. p = 0.002: util 0.149, **p99.9 1.006 ms**, queue max 262. **12-layer windows: dependency distance 5, so no stalls (12 cycles per iteration).** |
| A.3 Table IV, exact cycles | Red-black at p = 0.003: **1003.3 µs** (Test 1b shots), 1024.4 µs (fresh), 1010.3 µs (pooled). This was 986–1007 µs with t_it + 200 ns. **(c) is now missed by 0.3–2.4%.** |
| B.1 LFSR model vs RTL | **0 mismatches** in 7,200,000 g8 draws (720 lanes × 10,000). Period 65,535 on every lane. |
| B.2 Accuracy with LFSR γ | Not different from the PRNG (pooled p = 0.003: 262 vs 256, p = 0.76). Against float flood, pooled p = 0.003: 262 vs 224, **ratio 1.17 (1.02–1.34), p = 0.027.** |
| B.3 Closed-loop RTL in LFSR mode | **206 shots, 0 mismatches** (iterations, decisions, observables, draws per shot). |
| C Statistics table | All Fig. 7 pairs: see C. Pooled red-black vs float flood at p = 0.003: 256 / 224, ratio 1.14 (1.00–1.31), p = 0.057. |

---

## A.1 Sliding-window decoding with the red-black decoder (measured)

### Setup
- **Circuit:** 36-round bb_ibm gross code, X decoder (Test 1d circuit).
- **Windows:** `test1d_window.Windowed` unchanged. (W, C) = (12, 8), so windows start at t = 0, 8, 16, 24, 32 and have 12, 12, 12, 12 and 5 detector layers; the last window commits everything. Global = one window of 37 layers.
- **Decoder per window:** relay_bp `RelayDecoderF32`, int4.2.8, Test 1b Relay-BP settings (α = 1, S = 1, γ0 = 0.125, interval (−0.226, 0.622), 80 + 300 × 60, cap 18,080, gamma seed 0).
- **Red-black order over the window's own layers:** local layer l = round − t; the even l first, then the odd l (layer ids = position in that order). For 12 layers: 0, 2, …, 10, 1, …, 11. For global: 0, 2, …, 36, 1, …, 35.
- **Shots:** the Test 1d chunks.
  - p = 0.003: 6 × 5,000, sampler seeds 1000–1005 (30,000).
  - p = 0.002: 25,000 per chunk, seeds 2000+, chunks in order until 4 h had passed. That gave 10 chunks, seeds 2000–2009, 250,000 shots: the first half of the 500,000 Test 1d shots.
  - Both settings decode the same shots, so the comparison is paired.
- **LER per round:** (1 − (1 − 2·LER)^(1/36)) / 2, with Wilson 95% intervals mapped through the same function.
- **Statistics:** exact McNemar and Bonett–Price CI of the ratio, as in C.

### Logical error rate
| p | Shots | Setting | Failures | LER per round (95% CI) | Windows not converged (shots with one) | Syndrome reproduced |
|---|---|---|---|---|---|---|
| 0.003 | 30,000 | W12_C8 | 73 | 6.78e-5 (5.39–8.52e-5) | 28 (23) | 29,984 |
| 0.003 | 30,000 | global | 63 | 5.85e-5 (4.57–7.48e-5) | 7 (7) | 29,993 |
| 0.002 | 250,000 | W12_C8 | 31 | 3.44e-6 (2.43–4.89e-6) | 68 (64) | 249,989 |
| 0.002 | 250,000 | global | 34 | 3.78e-6 (2.70–5.28e-6) | 9 (9) | 249,991 |

| p | W12_C8 / global failures | Both | Only W12_C8 | Only global | McNemar p | Ratio | 95% CI (Bonett–Price) | 95% CI (bootstrap) |
|---|---|---|---|---|---|---|---|---|
| 0.003 | 73 / 63 | 26 | 47 | 37 | 0.33 | 1.16 | 0.89–1.51 | 0.89–1.52 |
| 0.002 | 31 / 34 | 17 | 14 | 17 | 0.72 | 0.91 | 0.65–1.28 | 0.64–1.29 |

- **Syndrome check:** in every shot whose windows all converged, the committed correction reproduces the syndrome. All syndrome mismatches come from shots with a non-converged window (0 mismatches in fully converged shots).
- **Comparison with Test 1d** (float sweep, same seeds; context only, not a paired comparison here): at p = 0.003, W12_C8 had 65 failures and global 78.
  - With the red-black int4.2.8 decoder, global improves to 63 and W12_C8 goes to 73.
  - Neither direction is significant in either test.

### Iterations and legs per window (measured)
Legs = 1 if n ≤ 80, else 1 + ⌈(n − 80) / 60⌉ (n = window iterations).

| p | Window (t, layers) | Mean it | p99.9 | Max | > 80 it | Mean legs | Max legs | Not converged |
|---|---|---|---|---|---|---|---|---|
| 0.003 | 0 (0, 12) | 57.4 | 4,298 | 18,080 | 14.4% | 1.630 | 301 | 4 |
| 0.003 | 1 (8, 12) | 60.5 | 5,192 | 18,080 | 14.5% | 1.677 | 301 | 7 |
| 0.003 | 2 (16, 12) | 59.6 | 5,289 | 18,080 | 14.7% | 1.661 | 301 | 5 |
| 0.003 | 3 (24, 12) | 67.5 | 4,874 | 18,080 | 17.3% | 1.776 | 301 | 8 |
| 0.003 | 4 (32, 5) | 11.8 | 428 | 18,080 | 0.52% | 1.061 | 301 | 4 |
| 0.003 | global (37) | 57.1 | 4,150 | 18,080 | 8.3% | 1.559 | 301 | 7 |
| 0.002 | 0 (0, 12) | 22.4 | 964 | 18,080 | 6.6% | 1.179 | 301 | 19 |
| 0.002 | 1 (8, 12) | 22.9 | 905 | 18,080 | 6.8% | 1.184 | 301 | 18 |
| 0.002 | 2 (16, 12) | 22.7 | 932 | 18,080 | 6.9% | 1.179 | 301 | 14 |
| 0.002 | 3 (24, 12) | 25.1 | 992 | 18,080 | 8.5% | 1.207 | 301 | 17 |
| 0.002 | 4 (32, 5) | 5.7 | 67 | 15,827 | 0.08% | 1.004 | 264 | 0 |
| 0.002 | global (37) | 17.8 | 537 | 18,080 | 1.3% | 1.058 | 301 | 9 |

- **Bulk windows are flat across the circuit:** 57–67 iterations at p = 0.003, 22–25 at p = 0.002. Window 3 (t = 24) is the highest in both, 10–18% above the other bulk windows.
- **Windows need relay legs much more often than global decoding does:** 14–17% of bulk windows go past 80 iterations at p = 0.003, against 8.3% of global decodes. At p = 0.002 it is 6.6–8.5% against 1.3%.
- **Windows are 4.5–5.6× more costly per shot in iterations:** 257 window-iterations per shot at p = 0.003 vs 57 global, and 99 vs 18 at p = 0.002. A window iteration covers 12 layers and a global one 37 (see Test 1d, review note 1).

## A.2 Queue model at T = C = 8 µs, exact cycles (computed)

### Setup
- **Service time per window** (`scripts/review_queue.py windows`): cycles = 2 + P(L)·n + 13·(leg ends) + 12, at 4.76 ns (210.1 MHz, post-route A_explore).
  - L = the window's detector layers; leg ends = legs − 1.
  - The formula is measured exact for L = 13 (Test 2f, 506 shots).
  - **Assumption:** the constants 2, 13 and 12 are the same for L = 12 and L = 5. They come from the pipeline depth and the 5-cycle convergence check, which do not depend on L.
- **P(L), cycles per iteration:** `gen_rb_pkg.min_period` with 5-cycle spacing (read → write 4 cycles), cyclic.
  - Pairs of steps that share an error are the adjacent layers (r, r + 1), as in the gross-code DEM.
  - P(L) = L when every such pair is at least 5 issue slots apart.

  | Layers L | Order | Smallest distance | P(L) | Stall cycles |
  |---|---|---|---|---|
  | 12 (bulk windows) | 0, 2, …, 10, 1, …, 11 | **5** (e.g. 1 → 2, 9 → 10) | **12** | **0** |
  | 13 (Table IV, for reference) | 0, 2, …, 12, 1, …, 11 | 6 | 13 | 0 |
  | 5 (last window) | 0, 2, 4, 1, 3 | 2 | **11** | **6** (issue slots 0, 1, 2, 6, 7) |

- **Queue:** `test1e_queue` Lindley recursion, unchanged (FIFO, one engine).
  - One window arrives every 8 µs; shots are resampled with seed 20261112 and their 5 windows enter in time order, 10^7 windows in total.
  - No extra overhead; no cap beyond the decoder's own 18,080.

### Results
| p | Mean service per window, windows 0–4 (ns) | Utilization | p99 latency | **p99.9 latency** | Queue max |
|---|---|---|---|---|---|
| 0.003 | 3,382 / 3,563 / 3,511 / 3,968 / 691 | 0.376 | 1.109 ms | **2.042 ms** | 426 |
| 0.002 | 1,359 / 1,385 / 1,373 / 1,512 / 367 | 0.149 | 0.227 ms | **1.006 ms** | 262 |

- **Throughput:** utilization stays below 0.38, so the queue is stable at both p.
- **Latency is set by the cap-length windows.**
  - A window that runs to the cap takes 18,080 × 12 × 4.76 ns ≈ 1.03 ms, which backs up about 130 following windows.
  - At p = 0.002, 68 of the 1.25 M windows (5.4e-5) are such windows. That alone puts p99.9 at about 1 ms.
  - At p = 0.003 there are 28 of 150,000 windows (1.9e-4) plus a heavier relay tail (p99.9 4,300–5,300 iterations), which gives about 2 ms.
- **The 1 ms latency target is missed** at p = 0.003 (2.04 ms) and only just missed at p = 0.002 (1.006 ms) with W12_C8 windows at 8 µs. For comparison, the 12-round benchmark at T = 12 µs gives 1.003 ms and 0.195 ms (A.3).

## A.3 Table IV with exact cycle formulas (computed from measured traces)

### Setup
- **Queue:** as A.2, but one 12-round decode every T = 12 µs, 10^7 jobs, seed 20261112.
- **Red-black (engine_top_rb):** 2 + 13n + 13·(leg ends) + 12 cycles at 4.76 ns. Traces are the rb13 int4.2.8 Test 1g traces; p = 0.001 is the eval run.
- **Sweep (engine_top_pf2fix):** 14 + 1 + 26n + 10·(leg ends) + 10 cycles at 7.24 ns, measured in hw/summary_3d. Traces are int4.2.8 sweep (Test 1b).
- **Fully parallel [25]:** int4.2.8 flooding traces (Test 1b), n × 24 ns.
  - **Assumption:** no start, leg-end or readout overhead, since [25] reports none. This favours [25].
- **Change from the earlier table:** that table used t_it·n + 200 ns overhead and a float-flood trace for [25].

### New Table IV (p99.9 latency; utilization; queue max)
| Design | p = 3×10⁻³ | p = 2×10⁻³ | p = 10⁻³ |
|---|---|---|---|
| Fully parallel [25], int4.2.8 flood, 24 ns/it | 342.5 µs; 0.065; 60 | 33.7 µs; 0.027; 36 | 1.3 µs; 0.013; 5 |
| SORTQ sweep, exact cycles | 3,576.0 µs; 0.385; 653 | 1,338.4 µs; 0.176; 285 | 10.5 µs; 0.102; 39 |
| SORTQ red-black, exact cycles | **1,003.3 µs**; 0.131; 181 | 195.1 µs; 0.056; 94 | 2.5 µs; 0.033; 12 |

| Red-black, p = 3×10⁻³ shot set | p99.9 latency | Utilization | Queue max |
|---|---|---|---|
| Test 1b shots (above) | 1,003.3 µs | 0.131 | 181 |
| Fresh shots (seed 20261120) | 1,024.4 µs | 0.128 | 178 |
| Pooled (336,000) | 1,010.3 µs | 0.130 | 208 |

- **Red-black at p = 3×10⁻³ moves just above 1 ms on all three shot sets** (+0.3% to +2.4%). It was 986–1007 µs before.
  - The added +13 cycles per leg end outweighs removing the 200 ns per job.
  - The paper's "within 1% of 1 ms" should become "1.00–1.02 ms".
- **Utilizations drop by 1–3 points.** The 200 ns per-job overhead was 1.7% of T.
- **The fully parallel latency at p = 2×10⁻³ doubles** (16.4 → 33.7 µs). The int4 flood trace has a longer tail than float flood there. The other two columns barely change (344.0 → 342.5 µs, 1.3 → 1.3 µs).
- **Speed-up ranges:** red-black vs sweep is 3.6× (p = 0.003), 6.9× (p = 0.002) and 4.2× (p = 0.001).

### Fig. 2 busy fractions with int4.2.8 flooding (computed)
Busy fraction = mean iterations × 24 ns / 12 µs.

| p | Mean iterations (int4.2.8 flood, Test 1b) | Busy | Idle |
|---|---|---|---|
| 0.003 | 32.51 | 6.50% (780 ns) | 93.5% |
| 0.002 | 13.35 | 2.67% (320 ns) | 97.3% |
| 0.001 | 6.67 | 1.33% (160 ns) | 98.7% |

## B. Hardware LFSRs in the accuracy chain

### B.1 Bit-exact software model of gamma_src (measured)
- **Model:** `hw/rb/sim/lfsr_model.py`.
  - 16-bit Galois LFSR, taps 0xB400, 16 steps per draw.
  - g8 from the low 12 bits with cumulative thresholds {187, 791, 1395, 1999, 2603, 3207, 3811, 4096} and g8 = −2 + bin.
  - Per-lane seed ((t·72 + p) + 1)·0x9E37 mod 2^16, as in engine_top_rb.
  - The state is reset only by rst, so it carries from one decode to the next.
- **Draw order:**
  - Leg k ≥ 1: 6 prefill draws for the odd home rounds 1, 3, …, 11, then 7 draws for the even rounds 0, 2, …, 12.
  - The prefill happens at the last iteration of the previous leg, even when the decode converges there; there is none after leg 300.
  - Draws per decode = 13·L + 6·[converged at the last iteration of its leg and L < 300], with L = 0 for n ≤ 80, else 1 + ⌊(n − 81) / 60⌋.
  - All 720 lanes draw together, so the stream state is one global draw counter.
- **Check:** `tb_gamma_lfsr.sv` (720 unchanged gamma_src instances, LFSR_MODE = 1, engine seeds; Verilator) against `lfsr_check.py`.
  - **0 mismatches in 720 lanes × 10,000 draws.**
  - The first run showed a one-draw offset. It came from the testbench, which released reset and raised `next` at a clock edge (a race), not from the model. The fixed testbench drives its inputs on the falling edge.
- **Period:** 65,535 on all 720 lanes. Full-period g8 distribution: −2 4.56%, −1 … 4 14.75% each, 5 6.96%.

### B.2 Accuracy with LFSR-generated g8 (measured)
**Stream model (assumption about operation):** one engine, reset once, then the shots of a set in sample order without reset. The LFSR state therefore carries from shot to shot.
- **Shots that converge in leg 0** (n ≤ 80) decode identically, since g8 = 1 there. They are copied from the PRNG trace and advance the counter.
- **Every other shot is decoded again** in order with `explicit_gammas` from the model.
  - Test 1b p = 0.003: 4,313 re-decoded, 361,102 draws (5.5 periods).
  - Fresh set: 4,165 re-decoded, 339,926 draws (5.2 periods).
  - p = 0.002: 2,226 re-decoded, 121,279 draws (1.85 periods).

| Set | p | Shots | LFSR / PRNG failures | Both / only LFSR / only PRNG | McNemar p | Ratio (95% CI) | LFSR / float flood failures | Both / only / only | McNemar p | Ratio (95% CI) |
|---|---|---|---|---|---|---|---|---|---|---|
| Test 1b | 0.003 | 168,000 | 133 / 138 | 64 / 69 / 74 | 0.74 | 0.96 (0.81–1.15) | 133 / 111 | 51 / 82 / 60 | 0.078 | 1.20 (0.99–1.45) |
| Fresh (seed 20261120) | 0.003 | 168,000 | 129 / 118 | 59 / 70 / 59 | 0.38 | 1.09 (0.91–1.31) | 129 / 113 | 51 / 78 / 62 | 0.21 | 1.14 (0.94–1.38) |
| **Pooled** | 0.003 | 336,000 | 262 / 256 | — | 0.76 | 1.02 (0.90–1.16) | **262 / 224** | — | **0.027** | **1.17 (1.02–1.34)** |
| Test 1b | 0.002 | 600,000 | 17 / 22 | 10 / 7 / 12 | 0.36 | 0.77 (0.50–1.22) | 17 / 26 | 10 / 7 / 16 | 0.093 | 0.65 (0.43–1.04) |

| Set | p | LFSR mean it / p99.9 | PRNG mean it / p99.9 | Shots with different iterations / failure |
|---|---|---|---|---|
| Test 1b | 0.003 | 24.00 / 1541 | 24.11 / 1538 | 4,257 / 143 |
| Fresh | 0.003 | 23.40 / 1409 | 23.60 / 1476 | 4,126 / 129 |
| Test 1b | 0.002 | 9.83 / 217 | 9.86 / 216 | 2,197 / 19 |

- **The LFSR γ stream is as good as the PRNG:** no set differs significantly, and the pooled p = 0.003 ratio is 1.02 (0.90–1.16).
- **Iterations agree within 1%.**
- **Red-black vs float flood, pooled at p = 0.003, is now significant** (p = 0.027, 1.17×, CI 1.02–1.34). With the PRNG it was p = 0.057.
  - The γ draws alone move the result across 0.05.
  - The honest statement is "about 1.15–1.2× at p = 3×10⁻³, borderline significant".
- **At p = 0.002 the LFSR version has the fewest failures** (17 vs 26 float flood, p = 0.093).

### B.3 Closed-loop RTL in LFSR mode vs the software LFSR model (measured)
- **Shots:** one stream with reset once (`prep_rb_lfsr.py`).
  - The 6 golden shots, then per p = 0.003 and 0.002 the first 75 leg-0 picks and all 25 legs-1–3 picks of picks_rb.json, in index order.
  - That is 206 shots and 1,755 draws.
- **Software reference:** rb13 int4.2.8 with `explicit_gammas` from the model at the stream's draw counter.
- **RTL:** engine_top_rb, unchanged, built without RB_G8LOAD so gamma_src runs its LFSRs.
  - The testbench is a copy of tb_engine_rb with LEGMAX 301.
  - Verilator, 49 s.
- **Result:** `tb_engine_rb: shots 206, mismatching 0`.
  - Iterations, hard decisions, observables and the per-shot draw counts (RTL vs model) all match.
  - 152 shots converge in leg 0; 12,210 iterations, 135 leg starts, 13.000 cycles per normal iteration.
- **Consequence:** the software model with LFSR γ is bit-exact to the RTL in its deployed mode. The B.2 accuracy is the hardware's accuracy, given the stream model.

## C. Statistics for Fig. 7 (computed, no new decoding)
- **Method:** exact two-sided McNemar on the discordant shots. Bonett–Price (2006) adjusted-Wald CI of the paired ratio, cross-checked by a multinomial bootstrap (20,000 resamples, seed 1).
- **At p = 0.001** (1–2 failures) the bootstrap is degenerate. Use Bonett–Price there.
- Full table: `stats.md`. The p = 0.003 and p = 0.002 rows:

| p | A | B | Failures A / B | Both | Only A | Only B | McNemar p | Ratio | 95% CI |
|---|---|---|---|---|---|---|---|---|---|
| 0.003 | int4.2.8 flood | float flood | 106 / 111 | 61 | 45 | 50 | 0.68 | 0.95 | 0.80–1.14 |
| 0.003 | float sweep | float flood | 124 / 111 | 51 | 73 | 60 | 0.30 | 1.12 | 0.92–1.35 |
| 0.003 | int4.2.8 sweep | float flood | 128 / 111 | 52 | 76 | 59 | 0.17 | 1.15 | 0.95–1.39 |
| 0.003 | int4.2.8 red-black | float flood | 138 / 111 | 59 | 79 | 52 | **0.023** | 1.24 | 1.04–1.49 |
| 0.003 | int4.2.8 sweep | int4.2.8 flood | 128 / 106 | 54 | 74 | 52 | 0.061 | 1.21 | 1.00–1.46 |
| 0.003 | int4.2.8 red-black | int4.2.8 flood | 138 / 106 | 54 | 84 | 52 | **0.0076** | 1.30 | 1.08–1.57 |
| 0.003 | int4.2.8 sweep | float sweep | 128 / 124 | 54 | 74 | 70 | 0.80 | 1.03 | 0.86–1.24 |
| 0.003 | int4.2.8 red-black | int4.2.8 sweep | 138 / 128 | 57 | 81 | 71 | 0.47 | 1.08 | 0.90–1.29 |
| 0.003 | int4.2.8 red-black | float sweep | 138 / 124 | 52 | 86 | 72 | 0.30 | 1.11 | 0.92–1.34 |
| 0.002 | int4.2.8 flood | float flood | 29 / 26 | 15 | 14 | 11 | 0.69 | 1.12 | 0.78–1.59 |
| 0.002 | float sweep | float flood | 25 / 26 | 11 | 14 | 15 | 1.0 | 0.96 | 0.64–1.45 |
| 0.002 | int4.2.8 sweep | float flood | 19 / 26 | 8 | 11 | 18 | 0.27 | 0.73 | 0.46–1.18 |
| 0.002 | int4.2.8 red-black | float flood | 22 / 26 | 10 | 12 | 16 | 0.57 | 0.85 | 0.55–1.31 |
| 0.002 | int4.2.8 sweep | int4.2.8 flood | 19 / 29 | 8 | 11 | 21 | 0.11 | 0.66 | 0.42–1.06 |
| 0.002 | int4.2.8 red-black | int4.2.8 flood | 22 / 29 | 10 | 12 | 19 | 0.28 | 0.76 | 0.50–1.18 |
| 0.002 | int4.2.8 sweep | float sweep | 19 / 25 | 9 | 10 | 16 | 0.33 | 0.76 | 0.49–1.21 |
| 0.002 | int4.2.8 red-black | int4.2.8 sweep | 22 / 19 | 5 | 17 | 14 | 0.72 | 1.16 | 0.68–1.94 |
| 0.002 | int4.2.8 red-black | float sweep | 22 / 25 | 6 | 16 | 19 | 0.74 | 0.88 | 0.54–1.44 |
| 0.003 | red-black, **fresh shots** | float flood | 118 / 113 | 48 | 70 | 65 | 0.73 | 1.04 | 0.86–1.27 |
| 0.003 | red-black, **pooled 336,000** | float flood | 256 / 224 | 107 | 149 | 117 | 0.057 | 1.14 | 1.00–1.31 |

- **Red-black against int4.2.8 flood on the Test 1b shots is the strongest effect** (p = 0.0076, 1.30×). It was not in the paper's text.
- **The paper's pooled "1.15×" is 1.14×** (256 / 224 = 1.143). With LFSR γ it is 1.17× (B.2).

## What this means for the paper
1. **Continuous decoding works accuracy-wise:** 12-round windows with C = 8 match global decoding within noise at p = 0.003 and 0.002, with red-black int4.2.8.
   - **Latency is the limit:** at T = 8 µs the p99.9 latency is 2.0 ms (p = 0.003) and 1.006 ms (p = 0.002), driven by cap-length windows.
2. **The 12-layer windows need no stalls:** smallest red-black distance 5, so 12 cycles per iteration. Only the 5-layer tail window needs 6 stall cycles.
3. **Table IV:** with the exact cycle formula, red-black at p = 3×10⁻³ is 1.00–1.02 ms, just above 1 ms.
4. **Hardware LFSRs:** bit-exact model (0 / 7.2 M draws; 0 / 206 closed-loop shots).
   - Accuracy equals the PRNG version.
   - The pooled red-black vs float-flood gap at p = 3×10⁻³ becomes significant (1.17×, p = 0.027).
   - The abstract's "within 1.15×" should be "about 1.15–1.2×" and not described as non-significant.
5. **Fig. 2 with int4 flooding:** busy 6.5% / 2.7% / 1.3%, idle above 93% at every p.

## Assumptions and limits
- **Exact-cycle constants:** 2, 13 and 12 are measured at L = 13 and assumed for L = 12 and 5. P(L) assumes only adjacent layers share errors.
- **Fully parallel [25]:** 24 ns per iteration with zero overhead (favours [25]).
- **LFSR stream model:** one reset, then shots in sample order. A different order or a periodic reset gives a different, equally valid γ stream.
  - B.2 shows one realisation per set; how much it varies between orders was not measured.
- **p = 0.002 windows:** 250,000 shots, limited by the 4 h budget. The 95% CI of the ratio is still 0.65–1.28.
- **Not run:**
  - window decoding with LFSR γ;
  - other (W, C);
  - T = 8 µs for the 12-round benchmark;
  - RTL simulation of 12- or 5-layer engines (the cycle formula for those L is derived, not simulated).

Files:
- **Scripts:** `scripts/review_windows.py`, `review_windows_stats.py`, `review_queue.py`, `review_lfsr_acc.py`, `review_stats.py`, `run_review_fixes.sh`.
- **RB simulation:** `hw/rb/sim/lfsr_model.py`, `tb_gamma_lfsr.sv`, `lfsr_check.py`, `prep_rb_lfsr.py`, `run_rb_lfsr.sh`.
- **Results** in `results/review_fixes/`: `windows/`, `windows_stats.json`, `queue_windows.json`, `queue_table4.json`, `lfsr/`, `stats.{md,json}`.
- **Logs:** `windows/run.log` and `lfsr/*.log` here; `hw/rb/sim/run_rb_lfsr.log` and `sim_rb_lfsr.log`.
