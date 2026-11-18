# SORTQ: symmetry-folded round engines for real-time QLDPC decoding

This repository is the artifact for the paper **"SORTQ"** (anonymous submission). It contains:

- **The SORTQ flow** (`./sortq build`). It reads a Stim circuit of a bivariate bicycle (BB) code and finds the detector error model's translation symmetry with nauty. From that it derives the folded decoder (one check type, a few error types, a small set of base edges) and generates the RTL packages for a round engine.
- **The RTL** of two round engines for the [[144,12,12]] gross code (X decoder, Relay-BP, 4-bit messages):
  - the **sweep engine**: 26 cycles per iteration, 138.1 MHz;
  - the **red-black engine**: 13 cycles per iteration, 210.1 MHz.

  Both come with test benches, golden-model scripts, synthesis flows and the post-route reports.
- **Every experiment script** behind the paper's tables and figures, plus the small result files (`results/`).
  - Accuracy runs use Relay-BP with bit-exact integer arithmetic.
  - The real-time numbers come from a queue model.
  - The scaling estimates cover the 72-, 144- and 288-qubit codes.

Everything runs on Linux. The decoding experiments are CPU-only, and the long ones take hours with 8 worker processes. The flow, the RTL checks and the queue model take seconds to minutes.

---

## 1. Requirements

| Tool | Version used | Needed for |
|---|---|---|
| Python | 3.11 (main), 3.14 (queue model; 3.11 also works if the numba wheel exists) | everything |
| Rust toolchain (`cargo`) + git | any recent | building the patched Relay-BP decoder |
| Verilator | 5.054 | RTL simulation and lint |
| Vivado | 2025.2, part `xcvu19p-fsva3824-2-e` | synthesis only (the reports are included, so this is optional) |

Exact package versions: `setup/requirements.txt`, `setup/requirements-queue.txt`, `setup/hdl_env.conda.yml` (Verilator via conda-forge). The machine and tool details of the original runs are in `docs/ENVIRONMENT.md`.

## 2. Setup (about 10 minutes)

```bash
# main environment: decoder, sampling, SORTQ flow
python3.11 -m venv .venv && source .venv/bin/activate
pip install -r setup/requirements.txt
setup/relay_bp/build_relay_bp.sh          # clones Relay-BP at the paper's commit, applies our patch, pip-installs it

# queue-model environment (numba)
python3 -m venv .venv-queue && .venv-queue/bin/pip install -r setup/requirements-queue.txt

# Verilator 5.054 (or use any Verilator 5.x already on PATH)
conda env create -f setup/hdl_env.conda.yml -p ./.hdl_env
```

The scripts find the tools through these environment variables. If a variable is unset, the plain command on `PATH` is used.

```bash
export RELAY_PYTHON=$PWD/.venv/bin/python        # decoding scripts (default: python3)
export SORTQ_PYTHON=$PWD/.venv/bin/python        # ./sortq (default: python3)
export QUEUE_PYTHON=$PWD/.venv-queue/bin/python  # queue-model scripts (default: python3)
export HDL_ENV=$PWD/.hdl_env                     # adds $HDL_ENV/bin (verilator) to PATH
export XILINX_SETTINGS=/path/to/Vivado/2025.2/settings64.sh   # only for synthesis
```

**About the Relay-BP patch** (`setup/relay_bp/relay_bp_sortq.patch`, against https://github.com/trmue/relay commit `cdfdc99`). It adds:
- `check_layers`: layered schedules (round sweep, red-black);
- `quant`: bit-exact integer arithmetic, e.g. `int4.2.8`, defined in `hw/ARITHMETIC.md`;
- `RELAY_DUMP`: write-only per-step dumps, used as golden vectors for the RTL.

With these options unset, the decoder behaves exactly as upstream.

## 3. Quick start (about 5 minutes, no long runs)

```bash
# (a) SORTQ flow on the gross code: symmetry, folded decoder, generated RTL packages, resource estimate
./sortq build "circuits/bb_ibm/circuit=bicycle_bivariate_144_12_12_memory_Z,distance=12,rounds=12,error_rate=0.003,noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim" \
        --basis X --order rb --out build/gross_X
cat build/gross_X/report.md               # Z12 x Z6 symmetry, 10 error types, 35 base edges, red-black schedule
diff build/gross_X/rb_pkg.sv hw/rb/rtl/rb_pkg.sv && echo "generated package = the one in the verified engine"

# (b) elaborate the red-black engine with the generated packages (Verilator lint)
scripts/sortq_lint_rb.sh build/gross_X 13

# (c) hardware LFSRs: bit-exact check of the 720 gamma lanes against the software model (10,000 draws per lane)
cd hw/rb/sim && verilator --binary -j 4 -Wno-fatal --top-module tb_gamma_lfsr -Mdir obj_lfsr ../../rtl/gamma_src.sv tb_gamma_lfsr.sv \
  && ./obj_lfsr/Vtb_gamma_lfsr +NDRAWS=10000 +OUT=lfsr_rtl.txt && $RELAY_PYTHON lfsr_check.py lfsr_rtl.txt lfsr_check.json; cd -
```

## 4. Reproducing the paper

### 4.1 Where each result comes from

| Paper item | Script(s) (in `scripts/` unless noted) | Result files (included) |
|---|---|---|
| Symmetry of the three BB codes; folded decoder sizes (Table II) | `./sortq build`, `run_sortq_rb.sh`; symmetry details `test1c_engine_params.py`, `idea1_symmetry.py` | `results/test1c/`, `results/test3f/summary.md`, `results/test3f/builds_rb/*/report.md`, `results/idea1_sym_ibm_d12_p001.json` |
| Accuracy and iterations: float / int4.2.8 × flooding / sweep / red-black (Fig. 7) | `run_test1b.sh`, `run_test1g.sh`, `run_test1g_p001.sh`, then `eval_accuracy.py` | `results/eval/accuracy.md`, `results/test1b/`, `results/test1g/` |
| Paired statistics for Fig. 7 (McNemar, 95% CI of failure ratios) | `review_stats.py` | `results/review_fixes/stats.md` |
| Red-black accuracy on a second shot set, parameter study | `run_test1h.sh` | `results/test1h/summary.md`, `robustness.md` |
| k rounds per layer (sweep k = 1–4) | `run_test1f.sh` | `results/test1f/` |
| Idle fraction of a fully parallel decoder (Fig. 2) | `review_queue.py table4` (busy fractions) | `results/review_fixes/queue_table4.json` |
| Hardware table (LUT, FF, LUTRAM, clock, cycles; Tables I and III) | Vivado flows in `hw/synth/`, `hw/rb/synth/`; cycles from closed-loop simulation (§5) | `hw/synth/runs/engine_top_pf2fix_p1_lutram_fmax/`, `hw/rb/synth/tc/runs/A_explore_4.76/`, `hw/rb/synth/runs/engine_top_rb_fmax2/`, `hw/summary_3d.md`, `hw/summary_2f.md` |
| p99.9 latency and utilization, T = 12 µs (Table IV) | `review_queue.py table4` (exact cycle formulas); queue model `test1e_queue.py` | `results/review_fixes/queue_table4.json`, `results/review_fixes/summary.md` |
| Design space and real-time target lines (Fig. 8a) | `test2d_model.py` (OUT_SUB=refix REF_RUN=engine_top_pf2fix_p1_lutram_fmax), `review_fig8_lines.py`, `fig6.py` | `results/test2d/refix/pareto.csv`, `results/review_fixes/fig8_lines.json` |
| LUT per code block, logical qubits per FPGA (Fig. 8b) | `eval_scaling.py` (run by `fig6.py`) | `results/eval/scaling.md` |
| Continuous (sliding-window) decoding, 36 rounds | `review_windows.py`, `review_windows_stats.py`, `review_queue.py windows` (`run_review_fixes.sh A`); earlier float study `test1d_window.py` | `results/review_fixes/windows*.json`, `queue_windows.json`, `results/test1d/summary.md` |
| Accuracy with the hardware LFSR memory strengths | `review_lfsr_acc.py`, `hw/rb/sim/run_rb_lfsr.sh` (`run_review_fixes.sh B`) | `results/review_fixes/lfsr/`, `results/review_fixes/summary.md` |

`docs/PAPER_SOURCES.md` has a finer map down to individual numbers.

### 4.2 Shots (the sampled syndromes)

All shots are drawn by Stim from the circuits in `circuits/` with fixed seeds. They are not stored here; regenerate them with:

```bash
cd scripts
$RELAY_PYTHON archive_shots.py make         # 12-round sets, p = 0.003 / 0.002 / 0.001 (seed 20261111) and the fresh p = 0.003 set (seed 20261120)
$RELAY_PYTHON archive_shots2.py make        # 36-round sets, golden-test shots, [[72,12,6]] set
```

Stim's output depends on the sample call sizes, so the scripts reproduce the exact call pattern. Each file is checked against the SHA-256 in `archive/shots/*.json`. The decoding scripts sample the same shots themselves, so this step is only needed to inspect or verify them.

### 4.3 Decoding runs (long)

Run them from `scripts/`. Each run script writes per-shot traces (`results/**/*.npz`) and summaries.

| Command | Content | Wall time of the paper's runs (8 worker processes) |
|---|---|---|
| `./run_test1b.sh` | 3 formats × 2 schedules, p = 0.003 (168,000 shots), 0.002 and 0.001 (600,000 each) | ~1.6 h |
| `./run_test1g.sh`, `./run_test1g_p001.sh` | red-black order (rb13) | ~45 min + p = 0.001 run |
| `./run_test1h.sh` | red-black on fresh shots, parameter study | ~1.2 h |
| `./run_test1f.sh` | k rounds per layer | ~1.2 h (+ `p001` mode) |
| `./run_review_fixes.sh A` / `B` | sliding windows (36 rounds) / hardware-LFSR accuracy and RTL check | ~6 h (p = 0.002 limited to a 4 h budget) / ~0.5 h |

Every run script also has a `smoke` mode (`./run_test1g.sh smoke` and so on) that decodes a few thousand shots in minutes.

### 4.4 Tables and figures from the traces (seconds to minutes, `QUEUE_PYTHON`)

```bash
cd scripts
$QUEUE_PYTHON eval_accuracy.py            # Fig. 7 table
$QUEUE_PYTHON review_stats.py             # McNemar / confidence intervals
$QUEUE_PYTHON review_queue.py table4      # Table IV, Fig. 2 busy fractions
$QUEUE_PYTHON review_fig8_lines.py        # Fig. 8a target lines
OUT_SUB=refix REF_RUN=engine_top_pf2fix_p1_lutram_fmax $RELAY_PYTHON test2d_model.py   # design-space model
$RELAY_PYTHON fig6.py                     # Fig. 8 -> figures/fig_results.pdf (needs Times New Roman; FIG_FONT_DIR)
```

## 5. Hardware verification

Simulation uses Verilator. Each step compares the RTL with the bit-exact software decoder.

1. **Golden dumps.** `hw/golden/golden.py` and `hw/rb/golden/golden_rb.py` (with the `RELAY_DUMP` build) record every message of a few decodes; `check_and_vectors.py` checks them against `hw/ARITHMETIC.md` and writes block test vectors.
2. **Block and round-step replay.**
   - Sweep engine: `hw/tb/run_all.sh`, about 30 test benches. See `hw/tb/README.md` for the vector generators.
   - Red-black engine: `hw/rb/tb/build_rs_rb.sh`, `gen_vectors_rb.py`.
3. **Closed loop** (whole engine against the software decoder, shot by shot, with a read-after-write hazard checker):
   - Sweep: `hw/sim3d/run_3d.sh`.
   - Red-black: `hw/rb/sim/run_rb.sh` (506 shots, 0 mismatches, exactly 13 cycles per iteration; log `hw/rb/sim/sim_rb.log`).
   - Red-black with the hardware LFSRs: `hw/rb/sim/run_rb_lfsr.sh`.
4. **Injected bugs.** `hw/tb/mutate*.sh`, `hw/rb/tb/mut_rs.sh`, `hw/rb/sim/mut_eng.sh`: every mutant must be caught.

The large inputs (dumps of 95–137 MB per shot, about 1 GB of vectors) are regenerated by these scripts and not stored. The logs of the paper's runs are included next to the scripts.

## 6. Synthesis, placement and routing (optional, Vivado 2025.2)

All runs are out-of-context on `xcvu19p-fsva3824-2-e`. Every run reads the released RTL plus a small harness and writes the post-route reports into its folder:
- `result.txt`: worst negative slack (WNS) and the critical path;
- `util_route.rpt`, `util_route_hier.rpt`: LUT, FF, LUTRAM and BRAM, in total and per block;
- `timing_summary.rpt`.

The clock frequency is 1 / period when WNS ≥ 0.

Set up Vivado first: `source $XILINX_SETTINGS` (or have `vivado` on `PATH`).

```bash
# Red-black engine, paper's best result (210.1 MHz = 4.76 ns): synthesize once, then place and route with directives
cd hw/rb/synth/tc
vivado -mode batch -source synth_dcp.tcl                                  # -> synth.dcp
mkdir -p runs/my_explore_4.76 && (cd runs/my_explore_4.76 && vivado -mode batch -source ../../impl.tcl -tclargs 4.76 Explore .)
#   compare with runs/A_explore_4.76/ (the paper's run). ./queue_tc.sh runs all four directive variants.

# Red-black engine, default flow (190.5 MHz = 5.25 ns)
cd hw/rb/synth
mkdir -p runs/my_rb && (cd runs/my_rb && vivado -mode batch -source ../../run_block_rb.tcl -tclargs engine_top_rb 5.25 4 .)
#   compare with runs/engine_top_rb_fmax2/

# Sweep engine (138.1 MHz = 7.24 ns)
cd hw/synth
mkdir -p runs/my_sweep && (cd runs/my_sweep && vivado -mode batch -source ../../run_block.tcl -tclargs engine_top_pf2fix_p1_lutram 7.24 4 .)
#   compare with runs/engine_top_pf2fix_p1_lutram_fmax/
```

- **Arguments of `run_block*.tcl`:** `<run> <period_ns> <threads> <outdir> [write checkpoint 0/1]`. The paper's runs took about 1–2 h each with 4 threads (synthesis about 25 min; placement and routing the rest).
- **Other parts and clock targets:** to place and route on another device or at another clock, change `set part …` in the Tcl script and the period argument. The RTL is plain SystemVerilog with no vendor primitives or IP; memories are inferred (`state_mem.sv` only adds `ram_style` hints that other tools ignore).
- **Block runs:** the block-level runs behind the resource model (CNU and VNU at several degrees) use the same `run_block.tcl` with their harness names, e.g. `cnu_d25` or `vnu_d4`; the harnesses are in `hw/synth/harness/`, generated by `gen_harness.py`. `hw/synth/results.json` collects their measurements for the model and for `./sortq`.

## 7. Repository layout

```
sortq                      SORTQ flow entry point (./sortq build <circuit> --basis X|Z [--order rb|sweep] [--out DIR])
setup/                     Python requirements, Verilator conda env, Relay-BP patch + build script
circuits/                  Stim circuits: BB codes [[72,12,6]], [[144,12,12]], [[288,12,18]] (source: §8),
                           36-round gross-code circuits and the script that makes them
scripts/                   flow, decoding experiments, queue model, statistics, figures
hw/rtl/                    shared RTL blocks (CNU, VNU, state memories, gamma LFSRs, ...) and generated wiring
hw/synth/rtl_2c/           sweep engine top (engine_top_pf2) and its controller
hw/rb/rtl/                 red-black engine (engine_top_rb, round_step_rb, ctrl_rb, ...)
hw/gen/, hw/rb/gen/        RTL generators used by ./sortq
hw/golden/, hw/rb/golden/  golden-model scripts (software decoder dumps)
hw/tb/, hw/rb/tb/          block and round-step test benches; hw/sim3d/, hw/rb/sim/: closed-loop engine simulation
hw/synth/, hw/rb/synth/    Vivado flows and post-route reports
hw/ARITHMETIC.md           the integer arithmetic (bit-exact definition shared by software and RTL)
results/                   small result files (Markdown / JSON / CSV) of the paper's runs
archive/shots/             shot-set metadata and checksums (the shots themselves are regenerated, §4.2)
docs/                      environment of the original runs, detailed result-to-source map
```

**Naming.** The scripts and result folders keep the identifiers of the original experiment log:

| Identifier | Experiment |
|---|---|
| test1b | number formats × schedules |
| test1c | symmetry and folded decoder |
| test1d | sliding windows, float |
| test1e | queue model |
| test1f | k rounds per layer |
| test1g | red-black order |
| test1h | red-black robustness |
| test2a | block RTL verification |
| test2c / test2d | synthesis and resource model |
| test2e | `./sortq` |
| test2f | red-black engine |
| test3d | sweep-engine closed loop |
| test3f | three codes |
| review_* | latest additions: exact-cycle queue model, hardware LFSRs, statistics |

**Engine names.** `engine_top_pf2` (run `engine_top_pf2fix_*`) is the sweep engine of the paper, and `engine_top_rb` is the red-black engine. `round_step.sv`, `round_step_pf.sv`, `ctrl.sv`, `rot2d.sv`, `engine_top.sv` and `engine_top_pf.sv` are earlier variants. They are kept because the block test benches and the design-space model still use them.

## 8. Third-party material

- **Relay-BP** (https://github.com/trmue/relay, Apache-2.0): not included. It is fetched and patched by `setup/relay_bp/build_relay_bp.sh`.
- **Circuits:** the 12-round and [[72,12,6]] / [[288,12,18]] circuits are Relay-BP's test circuits (Apache-2.0, licence in `circuits/LICENSE-relay-bp.txt`).
  - In the `circuits/bb_ibm/` copies the final measurement tag `M[disable_noise]` is written as plain `M`. This does not change the detector error model or the samples (`docs/ENVIRONMENT.md`).
  - The 36-round circuits are generated from them by `circuits/make_bb_ibm_rounds.py`.
