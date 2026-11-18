# Test 1d preparation: sliding-window decoding with the round sweep (2026-11-12)

## Setup
- Decoder: Relay-BP (relay_bp (`setup/relay_bp`), with `check_layers` and `quant`), `RelayDecoderF32`, `quant = "none"`
  (float, as the Test 1b float runs), sweep = one layer per round. Parameters as Test 2b / 1b: S = 1, γ0 = 0.125,
  α = None (α = 1), γ interval (−0.226, 0.622), pre_iter 80, 300 legs × 60.
- Circuits: IBM gross-code memory circuit from the Relay-BP data set (bb_ibm, d = 12, uniform_circuit, Z basis);
  X-decoder projection "xdec" built with `dem_tools.xdecoder_problem` (the Test 1 / 1c pipeline).
- Work done on the server with at most 2 cores, while Test 1b was running. All numbers are measured.

## Results

### Step 1: 24- and 36-round circuits
**How they were made.**
- There is no generator for the bb_ibm circuits in the Relay-BP data set: the repo only contains the finished
  `.stim` files.
- The 12-round file has no REPEAT block: it is fully unrolled, with 26,411 lines.
- The user chose to splice and rebuild (2026-11-12). Script: `circuits/make_bb_ibm_rounds.py`.
- **Gate section.** Each round is the block from one Z-ancilla measurement to the next, 2,021 lines.
  - Blocks 1–10 are identical text (asserted). Block 11 (the last round) differs.
  - The new circuit is the prefix (up to round 0's measurement), then block 1 repeated R − 2 times, then
    block 11, then the original tail (last X-ancilla measurement and final data measurement).
- **Detector section.** All 1,728 DETECTOR lines sit at the end of the file, using `rec[-k]` offsets.
  - Each line is rewritten as (coordinate, targets as (qubit, measurement type, occurrence or final)).
  - Rounds 1–10 follow the round-1 pattern, shifted by one occurrence and 216 in coordinate per round
    (asserted). Round 11 has the same detectors but only 2 TICK separators before the final detectors, so it
    is kept as its own segment.
  - The new section is: round 0, the round-1 pattern for rounds 1..R − 2, the round-11 segment shifted, the
    final detectors shifted, and the 12 observables. The observables use only final measurements, so their
    offsets are unchanged. All `rec` offsets are recomputed.
- **Validation:** rebuilding R = 12 reproduces the original file **byte for byte**, for p = 0.001, 0.002 and
  0.003. Nothing changes except the number of rounds.
- Files: `circuits/bb_ibm_rounds/…rounds={24,36},error_rate={0.001,0.002,0.003}…stim`, 6 files.
  They are also on the server under `circuits/bb_ibm_rounds/`.

| Rounds | Detectors | DEM errors | Z detectors | = 72 × (R + 1) | Noiseless: detectors and observables all zero (200 shots) |
|---|---|---|---|---|---|
| 12 (original) | 1,728 | 67,752 | 936 | yes | yes |
| 24 | 3,456 | 138,600 | 1,800 | yes | yes |
| 36 | 5,184 | 209,448 | 2,664 | yes | yes |

Identical at p = 0.003 and 0.002. Stim builds the DEM without error, so all detectors are deterministic.

### Step 2: the Test 1c template still holds
| Rounds | xdec | nonzeros | Reconstruction from the 1c template | Bulk rounds (all 10 types) | Round 0 | Final round |
|---|---|---|---|---|---|---|
| 12 | 936 × 8,784 | 30,672 | **exact** | 1..11 | T00–T08 (no T09) | T01, T03, T09 |
| 24 | 1,800 × 17,424 | 60,912 | **exact** | 1..23 | T00–T08 | T01, T03, T09 |
| 36 | 2,664 × 26,064 | 91,152 | **exact** | 1..35 | T00–T08 | T01, T03, T09 |

- The rebuild uses the 1c coordinates, the 10 error types (35 base edges) and per-round masks:
  round 0 = T00–T08; rounds 1..R − 1 = all 10 types; round R = T01, T03, T09.
- The type sets per round were also measured independently from the columns. 0 columns are of an unknown type,
  and the bulk is rounds 1..R − 1, as expected.

### Step 3: sliding-window decoder (`scripts/test1d_window.py`)
- **Window (W, C):**
  - rows = rounds [t, t + W);
  - columns = errors whose home round is in [t, t + W), restricted to those rows;
  - priors from xdec.
- **Syndrome:** the observed syndrome of those rows, XOR the effect of everything already committed.
- **Decode and commit:**
  - decode with the sweep, with layer = round − t;
  - commit columns whose home round is in [t, t + C);
  - advance t by C;
  - the last window (t + W ≥ R + 1) commits everything left.
- **Non-converged window:** it commits the decoding the relay decoder returns. With S = 1 and no converged leg,
  that is the hard decision of the first leg (pre_iter, 80 iterations), the same rule as the global decode.
- **Traces (.npz):**
  - `iterations` (shots × windows, total over relay legs);
  - `window_converged`;
  - `logical_fail` (per shot);
  - `window_t`, `W`, `C`, `R`.
- **Reading the traces in `test1e_queue.py`:**
  - The script now accepts 2-D window traces: a job is one window.
  - Part A counts a shot as failed if it failed or if any of its windows exceeds K.
  - Sweep-only traces are accepted, and `--Ts` sets the arrival period.
  - Format check: it runs on the dry-run traces (`dry/test1e_format_check/`, 200 shots, not a result).

### Step 4: validation (passed)
| Check | Result |
|---|---|
| One window (W ≥ R + 1) vs global sweep decode, 12 rounds, p = 0.003, 300 shots | decisions **bit-identical** (0 differing), iterations **identical** (0 shots differ) |
| (W, C) = (6, 3), 4 windows, same 300 shots: H · e_total = syndrome on shots where every window converged | 300 / 300 shots fully converged, **0 mismatches** |
| (W, C) = (8, 4), 3 windows, same check | 300 / 300 fully converged, **0 mismatches** |

### Step 5: timing dry run (not results)
36 rounds, p = 0.003, the same 200 shots (seed 7) for each setting, 2 threads (Rayon). Test 1b was running on the
server at the same time (load ≈ 33 on 32 cores), so these times are pessimistic.

| (W, C) | Windows | s / shot (2 threads) | Windows not converged | Shots with a non-converged window | Mean it. per window | Fails / 200 |
|---|---|---|---|---|---|---|
| (6, 3) | 12 | 0.052 | 0 | 0 | 10–59 | 1 |
| (8, 4) | 9 | 0.066 | 0 | 0 | 19–93 | 2 |
| (12, 8) | 5 | 0.055 | 0 | 0 | 19–68 | 2 |
| global | 1 | 0.067 | 0 | 0 | 82 | 1 |

All four settings: 0 syndrome mismatches. The fail counts from 200 shots say nothing about LER.

### Proposed shot counts for the real runs (estimate)
The 36-round LER is predicted from the measured 12-round Test 2b sweep LERs. Per round:
LER_round = (1 − (1 − 2·LER)^(1/R)) / 2. For 36 rounds: LER_36 = (1 − (1 − 2·LER_round)^36) / 2.

| p | 12-round LER (2b sweep) | per round | predicted 36-round LER | shots for ~50 global fails | proposal |
|---|---|---|---|---|---|
| 0.003 | 6.01e-4 | 5.01e-5 | 1.8e-3 | ~28,000 | **30,000** |
| 0.002 | 3.5e-5 | 2.92e-6 | 1.05e-4 | ~476,000 | **500,000** |

**Runtime estimate** (4 settings per p: global, (6, 3), (8, 4), (12, 8), all on the same shots):
- **p = 0.003:** 0.10–0.13 core-s per shot per setting, from the dry run. 30,000 × 4 × 0.10–0.13 core-s ≈
  3.3–4.3 core-h ≈ **25–35 min on 8 cores**.
- **p = 0.002:** about 0.42× the p = 0.003 cost per shot. That is the ratio of CPU time per shot in Test 2b at
  12 rounds; the per-shot cost was not measured at 36 rounds. 500,000 × 4 × 0.042–0.055 core-s ≈ 23–31 core-h ≈
  **3–4 h on 8 cores**.
- **Total ≈ 3.5–4.5 h on 8 cores.**

## What this means for Idea 1
1. **Longer circuits are now available without changing the physics.** The 24- and 36-round circuits are the IBM
   circuit with more identical rounds. The rebuild of the original is byte-identical, so the gates, noise and
   detectors are those of the data set.
2. **The round template is independent of the length.** One check type, 10 error types and 35 base edges
   describe 12, 24 and 36 rounds exactly. The only special rounds are the first (no T09) and the last (3 types).
   A streaming round engine therefore sees the same structure in every bulk window.
3. **Windowing is implemented and validated.** A single window reproduces the global decode bit for bit.
   Real windows give syndrome-consistent corrections. With 200 shots at p = 0.003, every window converged.

## Not tested
- The LER of windowed vs global decoding: this needs the real runs, at the proposed shot counts.
- Other window settings, overlap or commit rules: for example committing by detector round instead of home round,
  or W = 2C.
- Per-window latency in the queue: Test 1e can run on these traces once they exist.
- Timing without other load on the server, and timing at p = 0.002.
- XYZ / full-DEM decoding: only the X-decoder projection is used.
