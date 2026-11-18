# Test 2a: RTL building blocks for the SORTQ round engine (2026-11-12)

## Setup
- **Goal:** SystemVerilog blocks for the symmetry-folded round engine of the IBM gross-code X decoder, bit-exact with
  the Test 1b integer decoder (int4.2.8, round sweep, α = 1). No synthesis (that is Test 2c).
- **Where:** everything on the server under `hw/` (mirrored locally without the large dumps and
  vectors). At most 4 cores (Verilator builds `-j 4`; Python and simulations single-threaded).
- **Simulator:** **Verilator 5.054** (installed into a private conda env `the HDL environment` from conda-forge, user's choice;
  nothing system-wide). Icarus 13.0 was installed in the same env but not needed.
- **Design decisions taken by the user (2026-11-12):**
  1. Round step updates **all errors touching the round** (720 homed r + 504 homed r − 1), as the golden sweep does.
  2. Leg start by **init-flag gating** (no memory clearing).
  3. LFSR g8 **matches the golden distribution**.
  4. Simulator in a conda env.
- **Inputs used:** `results/test1c/engine_params.json` (template), the 12-round p = 0.003 circuit (golden
  dumps), the 36-round circuit (windows, commit), relay-bp with the Test 1b `quant` option.
- All numbers below are measured (simulation counts), except where marked "computed" (an exact arithmetic bound).

## Results

### Step 0: golden reference
- **`hw/ARITHMETIC.md`**: the exact integer arithmetic of the 1b decoder (check node, error node, sweep
  order, leg hand-off, rounding, saturation, the g8 grid), written from the code and then checked against the dumps.
- **Dump option added** to relay-bp (`RELAY_DUMP=<file>`, `RELAY_DUMP_LEGS`, write-only hooks; Python bindings
  unchanged). Built into a separate venv (`the relay_bp environment (dump build)`) so `the relay_bp environment` (the build used by Tests 1b/1d)
  is untouched. The 18 Rust unit tests pass.
- **Dumping changes nothing (measured):**

  | Comparison | Shots | Iterations, success, decoding, saturation counters |
  |---|---|---|
  | dump on vs dump off (new build), the 3 dumped shots | 3 | identical |
  | dump on vs pre-change build, the 3 dumped shots | 3 | identical |
  | new build (dump off) vs pre-change build: int4.2.8 sweep / int4.2.8 flood / float sweep | 2,000 each | identical |

- **Dumped shots** (p = 0.003, stim seed 20261113, picked from 2,000): converging at iteration 97 and 126 (in leg 2),
  and one needing 580 iterations (legs 1–2 dumped = 140 iterations). 363 iterations, 6 legs; 95–137 MB per shot.
- **Independent check of ARITHMETIC.md against the dumps** (numpy model, `hw/golden/check_and_vectors.py`):

  | Check | Count | Mismatches |
  |---|---|---|
  | check-node updates (sign and magnitude of every c2v) | 339,768 (11,133,936 edges) | **0** |
  | error-node updates (bias, marginal, hard decision, every v2c) | 5,384,016 | **0** |
  | ordering: every input = latest value written (prior / 0 at a leg start); memory = marginal at iteration start; g8; priors | all records | **0** |
  | hard decisions and convergence flags at iteration end | 363 iterations | **0** |
  | leg-start gating (hardware view, memories not cleared): gated CNU inputs / gated VNU inputs | 116,640 / 67,392 | **0** |

  In 116,617 of the gated CNU inputs and 33,582 of the gated VNU inputs the stored (previous-leg) value differs from
  the golden input, so the gating is really exercised.
- **g8 set used:** {−2, …, 5}. Computed probabilities: 4.574%, 14.743% (×6), 6.971%. Leg 0: g8 = 1 for all errors.
  The leg-1 g8 vector is identical in all 3 shots (the generator is re-seeded at every decode).

### Step 1: node blocks (`hw/rtl/`)
| Block | Interface (N = message magnitude bits, parameter) | Notes |
|---|---|---|
| `cnu.sv` | DEG (35) sign-magnitude inputs, syndrome, per-edge valid mask → per-edge outputs, min1, min2, min1 index, parity; `OUT_REG` | balanced 2-min tree + XOR tree; masked edges excluded, outputs 0 |
| `vnu.sv` | ≤ 6 c2v + mask + `late` flags, prior, M(t−1), g8, init → bias, marginal, hard decision, ≤ 6 v2c; `OUT_REG` | init & late gates stale c2v to 0 |
| `gamma_src.sv` | LOAD (g8 from testbench) / LFSR (16-bit Galois LFSR, 16 steps per draw, thresholds on 12 bits) | LFSR draws are not the golden draws; only the set and distribution match |

### Step 2: engine structure
- **`hw/gen/gen_round_wiring.py`** writes `hw/rtl/round_wiring.sv` (5,061 lines) and `hw/rtl/round_wiring_pkg.sv` from
  `engine_params.json` only: 72 checks × 35 base edges, error side grouped by offset (22 offset-0, 13 offset-1 base
  edges), both directions, parameter `K_ROUNDS` (the K check rounds are independent copies). Not hand-written.
- **`hw/gen/gen_tables.py`** writes `hw/rtl/engine_tables_pkg.sv`: boundary type sets and the logical-observable ROM.
- **`rot2d.sv`**: two-stage (Z6 then Z12) barrel rotator, W-bit payload, optional pipeline registers (latency 2).

### Step 3: global and windowing blocks
| Block | Function | Measured / built |
|---|---|---|
| `conv_check.sv` | per-detector parity over the window (W = 12: 864 detectors, 36 inputs each) + OR tree (fan-in 6) | **latency 5 cycles** (1 parity stage + 4 OR levels) |
| `ctrl.sv` | iterations as round sweeps, legs (80 / 60 / 300), init, gamma strobes, convergence request, per-round CNU and VNU masks from window and circuit boundaries | step outputs registered and duplicated `NDUP` times (`keep`) |
| `state_mem.sv` | ring buffer of W round slots, arrival port + engine read/write port, free after commit; `STORAGE` = REG / LUTRAM / BRAM, `RD_LAT` 0/1 | simple dual port (engine write has priority) |
| `commit.sv` | commit one round per beat: logical frame from a 720 × 12-bit ROM, syndrome carry into round t + C | 2-cycle frame update, 1-cycle carry |

Measured on the matrices: the observable flips depend only on (type, position) (0 exceptions in 26,064 columns of
the 36-round circuit), so the ROM has 720 entries; priors take one value per (type, home round).

### Step 4: testbenches (`hw/tb/`, Verilator)
| Block | Test | Vectors | Mismatches | Result |
|---|---|---|---|---|
| cnu (OUT_REG = 1 and 0) | golden dump replay | 339,768 (11,133,936 edges) | 0 | **PASS** |
| vnu (OUT_REG = 1 and 0) | golden dump replay, incl. 88,992 leg-start updates / 67,392 gated edges | 5,384,016 | 0 | **PASS** |
| cnu, vnu at N = 6 | random inputs vs the ARITHMETIC.md model (not golden: dumps hold 8-bit values) | 200,000 / 1,000,000 | 0 | **PASS** |
| gamma_src | LOAD: 10,000 random loads; LFSR: one full period (65,535 draws), exact bin counts | — | 0 | **PASS** |
| rot2d (PIPE = 1 and 0) | all 72 shifts × 21 payloads | 1,512 | 0 | **PASS** |
| round_wiring (K = 1 and 2) | connectivity vs H (round 5): all 2,520 edges, both directions, every slot driven once | 2,520 | 0 | **PASS** |
| conv_check | random hard decisions + syndromes vs software parity on the 36-round H, windows t = 0, 8, 24, 32; junk in absent slots | 400 (200 converged) | 0 (conv and all 864 unsat bits) | **PASS** |
| ctrl | masks of every step vs H (4 windows, 41 steps); leg sequencing; stop on convergence | 41 steps + 2 runs | 0 | **PASS** |
| commit | logical frame vs O · e and carry vs H · e (36 rounds), junk in absent types | 80 (60 with carry) | 0 | **PASS** |
| state_mem (5 storage / latency configs) | random traffic vs a reference model | 20,000 cycles each | 0 | **PASS** |
| **round step (stretch)** | wiring + 72 CNUs + 720 + 504 VNUs vs the golden dumps, every step of the 3 shots | **4,719 steps (78 at a leg start), 5,384,016 error updates** | **0** | **PASS** |

- **Mutation check:** one realistic bug per block in a copy of the RTL (e.g. min1 instead of min2, no syndrome in the
  parity, CNU mask ignored, no rounding offset, no leg-start gating, `<` instead of `≤` for the hard decision, no
  marginal saturation, wrong rotation direction, one mis-wired edge, no edge mask, wrong ROM entry, type mask ignored,
  carry on the wrong offset, window end off by one, a threshold off by one, ring wrap error, no init mux in the round
  step): **17 of 17 caught** (`hw/tb/logs/mutation*.log`). Two candidate mutants were equivalent (no behaviour change)
  and were replaced: v2c from the saturated marginal (see "What this means" 4) and arrival-vs-engine write priority in
  state_mem (already enforced by `arr_ready`).
- Final regression on the real RTL: **20 PASS, 0 FAIL** (all testbenches and parameter settings above, run 2026-11-12 23:43–23:55 CST) (`hw/tb/logs/regression.txt`).

### Additions (2026-11-13, your 4 requests)
- **Your choices:** priors in a **loadable register file**: 10 types × 13 home rounds, written over a load port
  before decoding, broadcast to the 72 lanes. No per-error RAM (Test 2d will estimate its cost). For leg coverage:
  **dump legs 0–9 of the 580-iteration shot**, in addition to the 3 existing shots.
1. **`VNU_PASSES` parameter in `round_step.sv`:**
   - **1:** 1,224 VNUs (720 errors homed r + 504 homed r − 1); a step is 2 cycles.
   - **2:** 720 VNUs, one per (type, position), time-shared. Pass A = errors homed r; pass B = errors homed r − 1
     on the 504 units of the 7 two-round types, through a 2:1 input mux. A step is 3 cycles. The 216 units of
     the other 3 types are used in pass A only.
   - Handshake: `in_valid` / `in_ready`; `cur_valid` / `prev_valid` / `out_valid`.
2. **Init gating from the round offsets at compile time.** `gen_round_wiring.py` now derives 4 package constants
   from the offsets alone, with the derivation rule written in the generator: `INIT_CNU_PRIOR` (CNU input = prior at
   a leg start: offset 0), `INIT_ZERO_CUR` / `INIT_ZERO_PREV` (VNU slot = 0 at a leg start: slot offset > group),
   and `HAS_PREV`. round_step uses only these constants; the VNU `late` inputs are constants. Result: the same
   gating as before (round_wiring.sv regenerated byte-identical), with no run-time table.
3. **Relay-leg boundaries:** a new golden dump of shot 53, legs 0–9: 580 iterations, 9 leg boundaries, 570 MB.
   - Dump on vs off: iterations, success, decoding and saturation counters identical.
   - Independent ARITHMETIC.md checks A–D on this dump: **0 mismatches** in all 11 counters.
4. **Prior read path inside the blocks:** register file → read by `round_idx` (home r for errors homed r, r − 1 for
   errors homed r − 1) → broadcast → CNU init mux and VNUs. The read is combinational, in the CNU cycle, so Test 2c
   times it.
   - Measured: every one of the 8,784 errors has exactly its (type, home round) table value (0 differ).
   - The testbench loads the 130 entries through the load port; the vectors' per-error priors are not driven.

| Round-step test (golden replay, priors from the register file) | Steps | Leg starts (init steps) | Error updates | Mismatches | Latency (measured) | Result |
|---|---|---|---|---|---|---|
| VNU_PASSES = 1, 3 shots × 2 legs | 4,719 | 6 (78) | 5,384,016 | 0 | 2 cycles | **PASS** |
| VNU_PASSES = 1, shot 53 × 10 legs | 7,540 | 10 (130) | 8,602,560 | 0 | 2 cycles | **PASS** |
| VNU_PASSES = 2, 3 shots × 2 legs | 4,719 | 6 (78) | 5,384,016 | 0 | 3 cycles | **PASS** |
| VNU_PASSES = 2, shot 53 × 10 legs | 7,540 | 10 (130) | 8,602,560 | 0 | 3 cycles | **PASS** |

- Each step also checks `in_ready`: it is low from the start until `out_valid`, with 0 errors. So the step period
  equals the latency (2 or 3 cycles).
- "Leg starts" counts decode starts plus relay-leg starts: 3 + 3 in the first set, 1 + 9 in the second.
- **Final regression with the additions:** **23 PASS, 0 FAIL** (all earlier testbenches + the 4 round-step runs,
  `hw/tb/logs/regression.txt`, 2026-11-13 01:05–01:28 CST).
- **New mutants (round_step):** **5 of 5 caught** (`hw/tb/logs/mutation_par.log`, `hw/tb/logs/mut_round_init_v2.out`).
  Each was replayed on the 3-shot vectors; the counts are mismatching steps.

  | Mutant | VNU_PASSES | Mismatching steps |
  |---|---|---|
  | no init mux (stored v2c into the CNU at a leg start) | 1 | 78 (all init steps) |
  | prior read for errors homed r − 1 uses round r | 1 | 726 |
  | no leg-start gating in the time-shared VNUs | 2 | 36 |
  | pass select wrong (prev inputs in pass A) | 2 | 4,719 (all) |
  | time-shared VNU always gets the cur prior | 2 | 726 |

  - Speed-up: round_step builds take about 45 min under the server load. 4 mutants ran in parallel, one build job
    each, so still ≤ 4 cores.

## What this means for Idea 1
1. **The round engine's datapath reproduces the Test 1b decoder bit for bit.** A whole round step (72 check nodes,
   1,224 error-node updates, generated wiring, leg-start handling) matches the golden decoder on every step of three
   shots, including leg starts. Test 2c can synthesize these exact blocks and the LER of Test 1b applies to them.
2. **A round step needs 1,224 error-node updates, not 720.** 7 of the 10 error types span two rounds and are updated
   in both layers. Two exact implementations now exist (same decoder, same LER):
   - `VNU_PASSES = 1`: 1,224 VNUs, 2 cycles per step;
   - `VNU_PASSES = 2`: 720 VNUs, 3 cycles per step (1.5× the step time for 0.59× the VNUs, plus a 2:1 input mux on
     504 units).

   Test 2c decides between them with real LUT and clock numbers. A design with 720 VNUs and one update per
   iteration would be a different decoder and would need its own LER test.
3. **Leg starts cost no extra cycles.** Gating with init (prior into the CNU, 0 into the VNU for stale edges) is
   exactly equivalent to the golden reset, so the memories never need clearing. This now holds over 9 consecutive
   relay-leg boundaries of one shot. The gated set is fixed by the round offsets at compile time.
4. **Two simplifications are proven safe (computed, and confirmed by equivalent mutants):**
   - v2c can be computed from the **saturated 7-bit marginal** instead of the 9-bit total: identical for every N,
     because the marginal only saturates at |total| ≥ 2^(N+2), where both forms saturate the message.
   - The **bias never saturates** for the g8 set {−2..5}: |bias| ≤ (10·(2^N − 1) + 5·2^(N+2)) / 8 < 2^(N+2).
     (Measured bias range in the dumps: −37..45.) The saturator can be removed if g8 stays in this set.
5. **The convergence check is short:** 5 cycles for a 12-round window (864 detectors).
6. **The windowing blocks are consistent with H:** ctrl's masks, conv_check and commit match the 36-round matrix for
   the first, bulk and last windows of W12_C8.

## Not tested
- **Synthesis, timing and resources** (Test 2c). No clock frequency or LUT/BRAM numbers yet.
- **A closed-loop engine:** state_mem ↔ round_step ↔ ctrl ↔ conv_check ↔ commit together, running whole decodes.
  The round step was replayed open-loop (inputs = golden memory state at each step); ctrl, state_mem, conv_check and
  commit were tested separately.
- **Windowed golden decodes:** the dumps are global 12-round decodes; W12_C8 windowing was checked only through
  masks, convergence and commit against H.
- **N = 6** only against the model with random inputs (no int6 golden dump: the dump format is 8-bit).
- **LFSR mode in decoding:** its draws differ from the golden draws; the LER with LFSR-generated g8 is not measured.
- **K_ROUNDS > 1:** only the wiring (K = 2 connectivity); no multi-round datapath (VNUs that combine two check
  rounds of the same step).
- **rot2d** only as a full 72-lane rotator; no reduced-lane engine configuration uses it yet.
- Golden coverage: 4 decodes at p = 0.003. 3 shots × legs 0–1 plus shot 53 × legs 0–9: 16 decode/leg starts,
  12,259 round steps. Not tested: other p, more shots, legs beyond 9. The bias saturator is never exercised
  (unreachable).
- **Prior register file:** only uniform priors per (type, home round), loaded once. Not tested: reloading between
  decodes, or per-error priors (Test 2d, analytic).
- **The new mutants** were replayed on the 3-shot vectors only, not the 10-leg set.
