# Tests 2e + 3f + 3g: the SORTQ flow as one command, other codes, logical qubits per FPGA

## 2e: `sortq build` (package)

### Setup
- **Command:** `sortq build <circuit.stim> --basis {X,Z} [--out DIR] [--window W]`. It runs `scripts/sortq.py` with the project venv that has pynauty and stim (`the SORTQ Python environment`).
  - `--basis X` = X decoder (Z-type detectors, memory_Z circuits).
  - `--basis Z` = Z decoder (X-type detectors, memory_X circuits).
- **Steps** (existing code, run as subprocesses; log in `build.log`):

  | Step | Script | Output |
  |---|---|---|
  | 1 | `scripts/test1c_engine_params.py`: decoder matrix (`dem_tools.decoder_problem`), symmetry (nauty, `idea1_symmetry.automorphisms`, rows coloured by round), template extraction, boundary embedding, exact reconstruction check (asserted) | `engine_params.json` |
  | 2 | `hw/gen/gen_round_wiring.py` | `round_wiring_pkg.sv`, `round_wiring.sv` |
  | 3 | `hw/gen/gen_tables.py` | `engine_tables_pkg.sv` (boundary type sets, observable ROM) |
  | 4 | resource estimate from the Test 2c / 2d per-block model | `estimate.json` |
  | 5 | | `report.md` |

- **Changes to the existing pieces** (parameterization only, no re-implementation):
  - `dem_tools.decoder_problem(path, det_type)`: `xdecoder_problem` is now `decoder_problem(path, "Z")`.
  - `test1c_engine_params.py`:
    - The group is detected as Z_NA × Z_NB: g1 of maximal order, g2 of order N / NA meeting ⟨g1⟩ trivially. The order must equal the number of checks per round, acting freely and transitively, or the step stops.
    - The bulk reference round is R // 2 − 1 (= 5 for the gross code).
    - The basis is selectable, and 4 keys are added (basis, check_type, bulk_ref_round, base_edge_table).
  - `labels.py`, `gen_round_wiring.py`, `gen_tables.py`: sizes come from engine_params (group structure, bulk types, DVMAX).
- **Regression on the gross-code X decoder** (measured):
  - `engine_params.json` equals the Test 1c file (no key differs; only the 4 added keys and `group.structure` are new).
  - `round_wiring_pkg.sv` and `round_wiring.sv` are identical to `hw/rtl`.
  - `engine_tables_pkg.sv` is identical except the comment line naming the source circuit: the copy in `hw/rtl` was generated from the 36-round circuit, with the same contents.
- **Generated SV check:** for every build, the existing RTL (hw/rtl + ctrl_pf + engine_top_pf2) with that build's generated packages elaborates in Verilator lint with 0 errors (`scripts/sortq_lint.sh`; W = d, C = 2d/3). This is elaboration only; no simulation or synthesis was run for the new codes.
- **Resource model** (estimate; every input is a post-route measurement from 2c / 2d):
  - **Block sizes:** CNU LUT at degrees 16 / 25 / 35 and VNU LUT at degrees 2–6. No other degrees occur in these codes, so no extrapolation was needed.
  - **In-context factors** (inside round_step_pf2): CNU × 0.828, VNU × 0.934.
  - **SORTQ k = 1 engine** (engine_top_pf2, VNU_PASSES 1, LUTRAM):
    - round_step = per-position CNU + VNUs (bulk types + two-round types);
    - shared blocks scaled from the measured gross engine: memories by state bits × W, gamma lanes by types × positions, conv_check by W × positions × base edges, commit by types × positions × observables, ctrl constant;
    - one calibration factor, 0.9728, makes the gross X engine equal its measured 450,227 LUT. It is needed because Vivado's per-instance LUT counts add up to slightly more than the parent's total.
  - **Window:** W = d (assumption; the gross code ran W = 12 = d).
  - **Fully parallel from our blocks:** Σ CNU(deg) + Σ VNU(deg) over the whole decoder matrix, standalone (as in Test 2d).
- **Run time** (server, nice 10): 1.6 s (72), 6 s (144), 35 s (288) per build.

## 3f: other codes

### Setup
- **Relay-BP data set** (`circuits/relay_memory_X`, uniform_circuit noise, CX schedule): bivariate bicycle codes **[[18,4,3]], [[72,12,6]], [[144,12,12]], [[288,12,18]]**, each as memory_X and memory_Z circuits.
- **Missing:** [[90,8,10]] and [[108,8,10]] are not in the data set (nor in `bb_ibm`). A BB n90 circuit exists only in a different family and noise model (`bb_google_si1000`), so it was not used. [[18,4,3]] was not requested and was not run.
- **Circuits:** memory_Z from `bb_ibm` (as all earlier tests) for the X decoders; memory_X from the Relay-BP set for the Z decoders; p = 0.003 (the structure does not depend on p).
  - Measured: the `bb_ibm` and Relay-BP memory_Z files give identical DEMs for all three codes (stim `==`); the files differ only in text.
- **Builds:** X and Z decoder for all three codes (6 builds; the task asked for X for every code and Z for the gross code; 288 Z was added for 3g, 72 Z for completeness).

### Results (measured by `sortq build`; LUT columns are estimates)

| Code / basis | Matrix (checks × errors), nnz | Rounds | Group | Reconstruction | Error types per home round | Base edges (offset 0 / 1) | Max degree check / error | Distinct shifts | Two-round types | VNU updates per step |
|---|---|---|---|---|---|---|---|---|---|---|
| [[72,12,6]] X | 252 × 2,232, 7,776 | 7 | order 36, Z6 × Z6 | exact | 9, 10 × 5, 3 | 35 (22 / 13) | 35 / 6 | 14 | 7 | 612 |
| [[72,12,6]] Z | 252 × 2,232, 7,776 | 7 | order 36, Z6 × Z6 | exact | 10 × 6, 2 | 35 (25 / 10) | 35 / 6 | 18 | 7 | 612 |
| [[144,12,12]] X | 936 × 8,784, 30,672 | 13 | order 72, Z12 × Z6 | exact | 9, 10 × 11, 3 | 35 (22 / 13) | 35 / 6 | 14 | 7 | 1,224 |
| [[144,12,12]] Z | 936 × 8,784, 30,672 | 13 | order 72, Z12 × Z6 | exact | 10 × 12, 2 | 35 (25 / 10) | 35 / 6 | 16 | 7 | 1,224 |
| [[288,12,18]] X | 2,736 × 26,208, 91,584 | 19 | order 144, Z12 × Z12 | exact | 9, 10 × 17, 3 | 35 (22 / 13) | 35 / 6 | 17 | 7 | 2,448 |
| [[288,12,18]] Z | 2,736 × 26,208, 91,584 | 19 | order 144, Z12 × Z12 | exact | 10 × 18, 2 | 35 (25 / 10) | 35 / 6 | 14 | 7 | 2,448 |

- **Common to all six:**
  - one check type per round; check degrees {16, 25, 35}: the first and last rounds and the bulk;
  - error degrees {2, 3, 4, 5, 6}, with the same 10 bulk error types (weights 2, 3, 3, 3, 3, 3, 3, 4, 5, 6) and 7 two-round types;
  - every boundary type is already a bulk type (class a only): 0 embedded or own-edge types, 0 slot conflicts;
  - the group acts freely and transitively on the checks of every round.
- **"Distinct shifts"** is the number of distinct (Δa, Δb) rotator settings in the bulk table; the whole matrix has no more.
- **X vs Z decoders** differ only in how the 35 base edges split between offset 0 and offset 1 (22 / 13 vs 25 / 10) and in the boundary type sets.

**LUT estimates** (xcvu19p, 4,085,760 LUT):

| Code (either basis) | W | SORTQ k = 1 engine | round_step | Shared (memories / gamma lanes / conv_check / commit / ctrl) | LUTRAM | State bits | Fully parallel from our blocks | + gamma lane per error | Parallel / SORTQ |
|---|---|---|---|---|---|---|---|---|---|
| [[72,12,6]] | 6 | 201,472 (4.9%) | 149,750 | 19,134 / 24,872 / 4,955 / 1,869 / 875 | 4,774 | 100,224 | 689,400 (16.9%) | +158,512 | 3.4 |
| [[144,12,12]] | 12 | **450,227 (11.0%)** = measured X engine | 299,499 | 76,535 / 49,743 / 19,818 / 3,738 / 875 | 19,096 | 400,896 | 2,722,752 (66.6%) | +623,823 | 6.0 |
| [[288,12,18]] | 18 | 995,913 (24.4%) | 598,999 | 229,604 / 99,486 / 59,455 / 7,475 / 875 | 57,288 | 1,202,688 | 8,133,408 (199%) | +1,861,241 | 8.2 |

- The X and Z engines of a code have the same estimate: same type weights and state bits per slot (35 base edges × 5 bits either way).
- For the gross code the X number is the measured post-route value (pre-3d-fix); the Z number is the model.

### Optional accuracy check: [[72,12,6]], int4.2.8, sweep vs flood (measured)
- **Settings:** Test 1b settings (alpha = 1, S = 1, gamma0 = 0.125, pre_iter 80, 300 legs × 60); X decoder, p = 0.003, 100,000 shots (sampler seed 20261111). Run with the Test 1f script, which also gave k = 2–4. 8 workers at nice 10, 85 s.

| Schedule (layers) | Failures (LER) | Paired vs sweep: both / only sweep / only this, McNemar p | Mean iterations | p50 / p90 / p99 / p99.9 / max |
|---|---|---|---|---|
| sweep k = 1 (7) | 1,566 (1.566%) | — | 8.54 | 5 / 15 / 67 / 243 / 1,216 |
| k = 2 (4) | 1,551 (1.551%) | 1,108 / 458 / 443, p = 0.64 | 9.78 (+15%) | 6 / 16 / 90 / 296 / 3,001 |
| k = 3 (3) | 1,547 (1.547%) | 1,092 / 474 / 455, p = 0.55 | 10.55 (+24%) | 7 / 17 / 95 / 305 / 2,053 |
| k = 4 (2) | 1,534 (1.534%) | 1,078 / 488 / 456, p = 0.31 | 10.90 (+28%) | 7 / 18 / 96 / 319 / 2,579 |
| flood (1) | 1,565 (1.565%) | 1,101 / 465 / 464, p = 1.0 | 11.64 (+36%) | 7 / 18 / 99 / 360 / 3,006 |

No shot hit the 18,080 cap. The pattern is the same as the gross code in Test 1f: no LER difference, and more iterations with fewer layers.

## 3g: logical qubits per FPGA

### Assumptions
- **A code block's decoder** = one X engine + one Z engine, each a complete SORTQ k = 1 engine with its own shared blocks: memories, conv_check, gamma lanes, ctrl, commit. Sharing ctrl and commit would save only about 5k LUT per block (< 1%); memories and conv_check are per basis.
- **Budget:** ≤ 80% of the xcvu19p LUTs = 3,268,608 LUT. FF, LUTRAM, BRAM and DSP are not binding (checked below).
- **Engine sizes:** gross X = measured 450,227 (pre-fix); gross Z and all of [[288,12,18]] = model estimates (sortq).
  - The Test 3d fix (v2c_o0 write-back merge) is not in these numbers. It adds about 15.8k FF and a 7,920-bit 2:1 mux, an estimated ≈ 4–8k LUT per engine. That would not change any block count below.
- **IBM:** X decoder alone 2.1M LUT (51.6%), as given. Assumed Z decoder = X decoder. IBM has no [[288,12,18]] number, so that row is our estimate: IBM 144 × (our fully-parallel 288 / 144 ratio = 2.99).

### Results (estimates from measured blocks)

| Design | LUT per code block (X + Z) | % of device | Blocks per FPGA at ≤ 80% | Logical qubits per FPGA (k = 12 per block) |
|---|---|---|---|---|
| **SORTQ [[144,12,12]]** | 900,454 | 22.0% | **3** (3.63) | **36** |
| SORTQ [[288,12,18]] | 1,991,826 | 48.8% | **1** (1.64) | **12** |
| IBM fully parallel [[144,12,12]] | ≈ 4.2M (2 × 2.1M) | ≈ 103% | **0** full blocks; equivalent 0.78 → 9.3 logical qubits; as built, one block needs 2 FPGAs → 6 per FPGA | 0 (6 with 2 FPGAs per block) |
| IBM-style [[288,12,18]] (scaled estimate) | ≈ 12.5M | ≈ 307% | 0; one block needs 4 FPGAs at ≤ 80% | ≈ 3 per FPGA (4 FPGAs per block) |

- **Other resources at 3 gross blocks:** FF ≈ 3 × 255k = 766k (9.4%); LUTRAM ≈ 3 × 38k = 115k (12%); no BRAM / DSP.
- **SORTQ vs IBM:** for the gross code, SORTQ fits 3 complete decoders (36 logical qubits) where IBM's design does not fit one. That is about 6× the logical qubits per FPGA (36 vs 6), or 3.9× against IBM's fractional equivalent (9.3).
- **Speed:** SORTQ trades speed for this. 177.8 ns per 13-round iteration (measured clock, Test 2c follow-up / 3d) against IBM's 24 ns. Test 2d has which real-time criteria each still meets.

## What this means
- **The flow is general across this code family.** The same pieces, parameterized, handle [[72,12,6]], [[144,12,12]] and [[288,12,18]] in both bases with exact reconstruction.
  - All six decoders reduce to the same 10 error types, 35 base edges and 7 two-round types, on Z6 × Z6, Z12 × Z6 and Z12 × Z12.
  - The round-step hardware therefore scales with the number of checks per round only (36 / 72 / 144). The generated packages elaborate with the unchanged RTL.
- **Scaling:**
  - The SORTQ engine grows roughly with checks per round × window: 0.20M / 0.45M / 1.0M LUT.
  - The fully parallel decoder grows with checks × rounds: 0.69M / 2.7M / 8.1M.
  - So the advantage grows with code size: 3.4× / 6.0× / 8.2×. At [[288,12,18]] a fully parallel decoder no longer fits one device (199% for one basis), while a complete SORTQ X + Z decoder uses 49%.
- **Logical qubits per FPGA:** 36 for the gross code and 12 for [[288,12,18]] with SORTQ, against 0 complete blocks for IBM's fully parallel design (6 with two FPGAs per block).

## Not tested
- **Synthesis and simulation of the new codes:** none. The 72 and 288 engines and all Z engines are model estimates, and their generated RTL was only linted, not simulated.
- **Clock for other code sizes:** not measured; a 144-position engine (288 code) has twice the fan-out and wiring of the gross engine.
- **Accuracy:** only the [[72,12,6]] sweep vs flood check was run; nothing for 288 or the Z decoders.
- **Window choice:** W = d is an assumption for 72 and 288; their windowed accuracy was not checked.
- **[[90,8,10]] / [[108,8,10]]:** not in the data set.
- **IBM:** only its total LUT figure is used; the 288 IBM number is our scaling, not published.
- **The Test 3d fix:** not re-synthesized; its LUT is estimated.

## Update (2026-11-14): estimates with the re-synthesized engine (Test 3d fixes)
- `SORTQ_REF_RUN=engine_top_pf2fix_p1_lutram_fmax` → `results/test3f/builds_refix/`. Calibration 0.9715.
- **Engine estimates:**

  | Code | Old → new |
  |---|---|
  | [[72,12,6]] | 201,472 → 200,936 |
  | [[144,12,12]] | 450,227 → 448,213 (measured) |
  | [[288,12,18]] | 995,913 → 990,160 |

- **3g blocks (X + Z):**

  | Code | Old → new | Blocks per FPGA | Logical qubits per FPGA |
  |---|---|---|---|
  | [[144,12,12]] | 900,454 → 896,426 (21.9%) | 3 | **36 (unchanged)** |
  | [[288,12,18]] | 1,991,826 → 1,980,321 (48.5%) | 1 | **12 (unchanged)** |

- The SORTQ iteration time becomes 188.2 ns at the confirmed 138.1 MHz (was 177.8 ns). The IBM comparison is unchanged.

## Update (2026-11-16): `sortq build --order rb` (red-black engine package)

### Setup
- **New option** `--order {rb,sweep}`, default `rb`. With `rb`, step 5 runs `hw/rb/gen/gen_rb_pkg.py`, now generalized, on the build's circuit and `engine_params.json`. It writes:
  - `rb_pkg.sv`: order, leg-start gating tables, CNU stage-1 groups;
  - `rb_pkg_report.json`;
  - a "Red-black engine package" section in `report.md`.
  
  `--order sweep` skips step 5, and every other output is unchanged.
- **Derived from H for any code and basis** (enumeration over every edge, then asserted to depend only on the pass):
  - **order:** even rounds, then odd rounds;
  - **CNU gating:** an input is gated iff no round of its error comes before the check in the order;
  - **VNU gating:** an input is gated iff its check comes later in the order;
  - **minimum dependency distance:** cyclic issue slots between steps that share an error.
- **Pipeline check:** the engine reads v2c 4 cycles before writing it back, so dependent steps must be at least 5 slots apart (cyclic). If the plain order is closer, the generator searches for the fewest cycles per iteration with idle issue slots and reports the stall cycles.
- **Generator changes** (no RTL change):
  - It reads any build's `engine_params.json`, `base_edge_table` and decoder basis (`dem_tools.decoder_problem`).
  - The old hard assertion "distance ≥ 6" is replaced by the reported distance and stall search.
  - With no arguments it still regenerates `hw/rb/rtl/rb_pkg.sv` from the Test 1c files.
- **Lint:** `scripts/sortq_lint_rb.sh` runs Verilator lint on the unchanged rb RTL plus the build's four generated packages, with top `engine_top_rb` and W = C = NRND = detector rounds (one window over the whole circuit, as engine_top_rb was built and measured).
- **Driver:** `scripts/run_sortq_rb.sh` (server, nice 10, `the SORTQ Python environment`, `SORTQ_REF_RUN` = pf2fix as for `builds_refix`). Outputs go to `results/test3f/builds_rb/` (rb) and `builds_sweepcheck/` (sweep regression); log in `builds_rb.log`.

### Regression (measured)
| Check | Result |
|---|---|
| `rb_pkg.sv` from `sortq build --order rb`, gross-code X decoder, vs `hw/rb/rtl/rb_pkg.sv` | **byte-identical** (the header names the same circuit file) |
| standalone `gen_rb_pkg.py` (Test 1c inputs) vs `hw/rb/rtl/rb_pkg.sv` | **byte-identical** |
| `--order sweep`, all 6 decoders, vs `builds_refix` (6 files each; the runtime field `seconds` and the output path in `report.md` normalized) | **identical** |
| `--order rb`, all 6 decoders, the same files except `report.md` vs `builds_refix` | **identical** (`report.md` adds step 5 and the new section) |

### Results (measured; generated and linted, not simulated)
| Build | Rounds | Runtime: whole build / rb step | Order | Min. dependency distance (need ≥ 5) | Stall cycles per iteration | Cycles per iteration | Lint (engine_top_rb) |
|---|---|---|---|---|---|---|---|
| [[72,12,6]] X | 7 | 2.0 s / 0.6 s | 0, 2, 4, 6, 1, 3, 5 | **3** | **4** (issue cycles 0, 1, 2, 3, 6, 7, 8) | 11 | 0 errors, 56 warnings (see below) |
| [[72,12,6]] Z | 7 | 2.0 s / 0.5 s | same | **3** | **4** | 11 | 0 errors, 56 warnings |
| [[144,12,12]] X | 13 | 8.1 s / 2.3 s | 0, 2, …, 12, 1, …, 11 | 6 | 0 | 13 | 0 errors, 1 warning |
| [[144,12,12]] Z | 13 | 8.2 s / 2.3 s | same | 6 | 0 | 13 | 0 errors, 1 warning |
| [[288,12,18]] X | 19 | 46.1 s / 10.4 s | 0, 2, …, 18, 1, …, 17 | 9 | 0 | 19 | 0 errors, 3 warnings |
| [[288,12,18]] Z | 19 | 44.1 s / 10.2 s | same | 9 | 0 | 19 | 0 errors, 3 warnings |

- **Gating tables:**
  - CNU: all 35 base edges gated in the even pass, 12 in the odd pass, in every build.
  - VNU, even pass (current / previous group): X decoders 13 / 10 slots, Z decoders 10 / 13 (the X / Z edge split). Odd pass: none.
  - So the X and Z packages differ. No two consecutive steps share an error in any build.
- **Stall cycles (as expected):** 0 for 144 and 288, and 4 for 72. The 72 result matches the earlier computed estimate in `results/eval/scaling.md` (11 cycles).
  - `HAZ_DIST` in `rb_pkg.sv` is informational only: `ctrl_rb` issues one step per cycle and checks only W = NSTEP.
  - So a 72 engine would elaborate but needs stall logic in ctrl_rb (not built).
- **Warnings:** the 1–3 warnings of 144 / 288 are Verilator's replication-limit notice on wide `'0` constants in `engine_top_rb` (lines 163–174). The 56 warnings of 72 are a real issue (next point).

### Finding: `conv_check.sv` and `commit.sv` hard-code the Z12 × Z6 position layout
- Both compute error positions with literal `12` and `6` (`PA = ((x / 6) + BE_SA[k]) % 12`, `PB = ((x % 6) + BE_SB[k]) % 6`, index `PA * 6 + PB`). The generated wiring and packages are general (index a × NB + b).
- **[[72,12,6]]** (Z6 × Z6, 36 positions): out-of-range selects, which are the 56 SELRANGE warnings. The same warnings were in the Test 2e / 3f sweep lint logs, which counted errors only.
- **[[288,12,18]]** (Z12 × Z12, 144 positions): indices stay in range, so there is **no warning, but the wrong error positions are read**.
- **Effect:**
  - For codes other than the gross code, the convergence check and the observable commit of both engines (sweep and red-black) would be wrong. The round step itself (CNU / VNU wiring) is generated and general.
  - The gross code is unaffected (NA = 12, NB = 6). No measured result, synthesis number or resource estimate changes.
  - The earlier statement "the generated packages elaborate with the unchanged RTL" holds only for elaboration, not for correctness on the other codes.
- **Fix (not applied; this task allowed no RTL changes):**
  - export `localparam int NA, NB` from `gen_round_wiring.py`;
  - use them in `conv_check.sv` and `commit.sv`.
  - For the gross code this elaborates identically.
