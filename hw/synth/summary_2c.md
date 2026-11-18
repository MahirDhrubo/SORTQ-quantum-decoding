# Test 2c: synthesis and implementation of the Test 2a blocks

## Setup
- **Tool and part:** Vivado 2025.2, xcvu19p-fsva3824-2-e, run on the server with 8 cores (2 lanes × 4 threads).
- **Flow per run:** synth_design (out of context, `-flatten_hierarchy rebuilt`) → opt_design → place_design → route_design. All reports are post-route.
- **Clock:** 2.5 ns. fmax (est.) = 1 / (2.5 ns − WNS).
  - Every design with WNS < 0 was re-run at its estimated period, rounded up to 0.01 ns, to confirm that it closes there.
  - "Confirmed clock" means a post-route run at that period with WNS ≥ 0.
- **Harness** (`gen_harness.py`): each DUT sits between real registers.
  - Every input comes from a flip-flop of one shift chain, with `shreg_extract = "no"`.
  - Every output goes into an XOR-chain register, so nothing can be optimized away.
  - Timing therefore runs register to register, including the harness flops. Resources are counted for the `dut` instance only.
- **Device totals:** LUT 4,085,760; FF 8,171,520; LUTRAM 956,160; BRAM36 2,160; DSP 3,840.
- **Blocks:**
  - cnu (DEG 35, OUT_REG 1), vnu (OUT_REG 1), vnu_nosat (bias saturator removed), gamma_src (LFSR), prior_rf (10 × 13);
  - conv_check (W 12), ctrl, commit, rot2d (72 lanes, 5 bits);
  - state_mem (W 12, width 7,920 bits = the widest engine_top field, my choice) in REG, LUTRAM and BRAM;
  - round_step (K = 1) for VNU_PASSES 1 and 2;
  - engine_top (synthesis-only integration) for VNU_PASSES 1 / 2 × STORAGE LUTRAM / BRAM.
- **Timing variant (user request after the first results):**
  - round_step_pf: the priors for the next round step are read one step ahead into a register (stage A), then copied into 18 duplicated registers (stage B; keep, max_fanout 256), each feeding 4 positions. No extra cycle per step.
  - ctrl_pf / engine_top_pf: the convergence check of iteration t overlaps iteration t + 1. If t converged, the work done in t + 1 is discarded. Hard decisions get two banks by iteration parity.
  - Synthesized: round_step_pf for VNU_PASSES 1 and 2, ctrl_pf, and engine_top_pf for VNU_PASSES 1 with LUTRAM.
- **engine_top memory layout** (user-approved): one state_mem per field, 12 slots, slot = window index.

  | Field | Bits per slot |
  |---|---|
  | v2c_o0 | 7,920 |
  | c2v_o1 | 4,680 (read at i + 1) |
  | marginals HP_r (2 ping-pong banks) | 3,528 each |
  | marginals HP_rm1 (2 banks) | 3,528 each |
  | marginals NP (2 banks) | 1,512 each |
  | g8_r (3-bit g8 + 2) | 2,160 |
  | g8_rm1 (3-bit g8 + 2) | 1,512 |
  | **Total** | **33,408 per slot = 400,896 bits for 12 slots** |

  - g8 comes from 720 LFSR lanes with distinct seeds.
  - v2c_o1 and c2v_o0 are forwarded to the next step through registers (12,600 FFs), not stored.
  - Other registers: syndromes (864 bits), hard decisions (8,640; 17,280 in engine_top_pf), emask (420).
- **Changes made during 2c (no datapath change):**
  - ctrl.sv: Vivado rejects a bit-select on a function call (Synth 8-12513). I replaced it with temporary variables; tb_ctrl still passes.
  - engine_top v1 → v2: the `% 13` for the prior row was moved into a register (rs_ridx), because v1's critical path ran through my glue logic. v1 is kept as engine_top_p1_bram_v1 (94.5 MHz est.).
- **Bit-exactness of the timing variant (measured; Verilator; test files in hw/tb):**
  - round_step_pf golden replay, 0 mismatches:

    | VNU_PASSES | Vectors | Error updates | Latency |
    |---|---|---|---|
    | 1 | 3-shot | 5,384,016 | 2 cycles |
    | 2 | 3-shot | 5,384,016 | 3 cycles |
    | 1 | 10-leg shot 53 | 8,602,560 | 2 cycles |
    | 2 | 10-leg shot 53 | 8,602,560 | 3 cycles |

    Steps run back to back, and in_ready had 0 errors.
  - Prefetch mutants: 2 of 3 caught (prior moved one cycle early in VNU_PASSES 2; wrong prev row). Not caught: removing the sign-magnitude conversion, because every prior in the table is ≥ 0.
  - ctrl_pf against ctrl, cycle by cycle (tb_ctrl_pf): 204 decodes for each of STEP_CYCLES 2 and 3, covering windows of 12, 5 and 2 rounds, every convergence iteration including leg ends, and result latencies 3–40.
    - 0 mismatches in done, success, iter_total, leg, gamma pulses and the step sequence.
    - 88 decodes per STEP_CYCLES had discarded speculative steps (451 steps for STEP_CYCLES 2, 407 for 3), never with init.
    - ctrl mutants: 3 of 4 caught. Not caught: the minimum-window guard NR_MIN, which protects a memory hazard that this testbench has no model of.

## Results (all post-route, measured)

### All runs at 2.5 ns (resources of `dut`; % of the device)

| Run | LUT | FF | LUTRAM | BRAM36 | DSP | WNS @ 2.5 ns | fmax est. | Logic levels | Routing |
|---|---|---|---|---|---|---|---|---|---|
| cnu | 810 (0.02%) | 191 (0.00%) | 0 | 0 | 0 | −1.757 | 234.9 MHz | 19 | 58.3% |
| vnu | 364 (0.01%) | 46 (0.00%) | 0 | 0 | 0 | −2.617 | 195.4 MHz | 24 | 59.0% |
| vnu_nosat | 349 (0.01%) | 46 (0.00%) | 0 | 0 | 0 | −2.154 | 214.9 MHz | 21 | 55.3% |
| gamma_src | 57 (0.00%) | 20 (0.00%) | 0 | 0 | 0 | +0.808 | 591.0 MHz | 5 | 66.7% |
| prior_rf | 536 (0.01%) | 650 (0.01%) | 0 | 0 | 0 | +0.426 | 482.2 MHz | 0 | 96.1% |
| conv_check | 15,714 (0.38%) | 1,038 (0.01%) | 0 | 0 | 0 | +0.673 | 547.3 MHz | 0 | 95.5% |
| ctrl | 516 (0.01%) | 732 (0.01%) | 0 | 0 | 0 | +0.128 | 421.6 MHz | 9 | 62.7% |
| ctrl_pf | 644 (0.02%) | 734 (0.01%) | 0 | 0 | 0 | +0.385 | 472.8 MHz | 7 | 57.6% |
| commit | 619 (0.02%) | 180 (0.00%) | 0 | 0 | 0 | +0.827 | 597.7 MHz | 3 | 72.8% |
| rot2d | 1,140 (0.03%) | 728 (0.01%) | 0 | 0 | 0 | +0.690 | 552.5 MHz | 1 | 87.3% |
| state_mem_reg | 35,672 (0.87%) | 102,969 (1.26%) | 0 | 0 | 0 | +0.163 | 427.9 MHz | 2 | 84.2% |
| state_mem_lutram | 8,504 (0.21%) | 7,929 (0.10%) | 4,528 (0.47%) | 0 | 0 | +0.437 | 484.7 MHz | 0 | 96.1% |
| state_mem_bram | 4,099 (0.10%) | 9 (0.00%) | 0 | 110 (5.1%) | 0 | +0.099 | 416.5 MHz | 2 | 90.0% |
| round_step_p1 | 444,878 (10.89%) | 68,332 (0.84%) | 0 | 0 | 0 | −6.591 | 110.0 MHz | 25 | 71.3% |
| round_step_p2 | 292,549 (7.16%) | 45,739 (0.56%) | 0 | 0 | 0 | −6.411 | 112.2 MHz | 24 | 70.9% |
| round_step_pf_p1 | 439,316 (10.75%) | 70,882 (0.87%) | 0 | 0 | 0 | −4.258 | 148.0 MHz | 24 | 61.8% |
| round_step_pf_p2 | 296,641 (7.26%) | 48,276 (0.59%) | 0 | 0 | 0 | −4.854 | 136.0 MHz | 26 | 65.6% |
| engine_top_p1_lutram | 448,124 (10.97%) | 115,547 (1.41%) | 19,096 (2.00%) | 0 | 0 | −6.823 | 107.3 MHz | 21 | 73.7% |
| engine_top_p1_bram | 429,472 (10.51%) | 82,178 (1.01%) | 0 | 464 (21.5%) | 0 | −7.222 | 102.9 MHz | 22 | 75.1% |
| engine_top_p2_lutram | 358,534 (8.78%) | 104,191 (1.28%) | 19,096 (2.00%) | 0 | 0 | −6.296 | 113.7 MHz | 21 | 78.1% |
| engine_top_p2_bram | 336,366 (8.23%) | 70,955 (0.87%) | 0 | 464 (21.5%) | 0 | −7.601 | 99.0 MHz | 19 | 72.8% |
| engine_top_pf_p1_lutram | 468,736 (11.47%) | 126,856 (1.55%) | 19,096 (2.00%) | 0 | 0 | −4.855 | 136.0 MHz | 20 | 71.5% |

No DSPs are used anywhere: the VNU's g8 products are small (3–4-bit), so they map to LUTs. Every run routed completely (0 unrouted nets).

### Confirmation runs at the estimated fmax

| Run | Period | WNS | Closes? | Confirmed clock |
|---|---|---|---|---|
| cnu | 4.26 ns | +0.094 | yes | 234.7 MHz |
| vnu | 5.12 ns | −0.044 | **no** | — (est. 193.6 MHz) |
| vnu_nosat | 4.66 ns | +0.116 | yes | 214.6 MHz |
| round_step_p1 | 9.10 ns | +0.094 | yes | 109.9 MHz |
| round_step_p2 | 8.92 ns | +0.041 | yes | 112.1 MHz |
| round_step_pf_p1 | 6.76 ns | +0.062 | yes | 147.9 MHz |
| engine_top_p1_lutram | 9.33 ns | +0.073 | yes | 107.2 MHz |
| engine_top_p1_bram | 9.73 ns | −0.462 | **no** | — (est. 98.1 MHz) |
| engine_top_p2_lutram | 8.80 ns | +0.029 | yes | 113.6 MHz |
| engine_top_p2_bram | 10.11 ns | +0.151 | yes | 98.9 MHz |
| engine_top_pf_p1_lutram | 7.36 ns | +0.086 | yes | **135.9 MHz** |

round_step_pf_p2 was run at 2.5 ns only (136.0 MHz est.); it has no confirmation run.

### Block-level fmax: which block limits

| Block | Clock | Critical path at that clock |
|---|---|---|
| cnu | 234.7 MHz (confirmed) | input register → min tree → output magnitude register; 19 logic levels, 59% routing |
| vnu | ≈193.6 MHz (est.; 5.12 ns misses by 44 ps) | input → bias → total → v2c magnitude; 24 logic levels |
| vnu_nosat | 214.6 MHz (confirmed) | same path without the bias saturator; 21 logic levels |
| round_step_p1 | 109.9 MHz (confirmed) | round_idx → prior register-file read and broadcast (fanout 224 / 150, about 3.3 ns) → VNU bias → marginal → v2c; 25 logic levels, 71% routing |
| round_step_p2 | 112.1 MHz (confirmed) | input register → shared VNU → v2c; 24–26 logic levels |
| round_step_pf_p1 | 147.9 MHz (confirmed) | At 2.5 ns: stage-B prior copy → VNU → v2c (24 logic levels, 62% routing). At 6.76 ns: stage A → stage B copy net, 0 logic levels, 6.68 ns of which 98.8% is routing. The first level of the fan-out tree (A to 18 copies spread over the die) is now the limit. |
| round_step_pf_p2 | 136.0 MHz (est.) | input register → shared VNU (pass mux) → v2c; 26 logic levels |

The standalone vnu harness drives `late` from an input register. Inside round_step, `late` is a compile-time constant.

### engine_top critical path and the block it lies in

| Run | Start → end | Logic levels | Routing | Block |
|---|---|---|---|---|
| p1_lutram @ 2.5 / 9.33 ns | rs_ridx (engine_top step register) → prior register-file read in round_step → CNU output register | 21 | 74% / 80% | prior read path inside round_step |
| p1_bram @ 2.5 ns | rs_ridx → prior read → CNU | 22 | 75% | same |
| p1_bram @ 9.73 ns | v2c_o0 BRAM read (CLKARDCLK) → CNU | 17 | 78% | BRAM clock-to-out plus CNU; 0.462 ns short |
| p2_lutram @ 8.80 ns | rs_ridx → prior read → shared-VNU v2c register | 23 | 73% | prior read path inside round_step |
| p2_bram @ 2.5 ns | v2c_o0 BRAM read → CNU | 19 | 73% | memory → round_step |
| p2_bram @ 10.11 ns | rs_ridx → prior read → shared-VNU v2c register | 22 | 72% | prior read path inside round_step |
| **pf_p1_lutram @ 2.5 ns** | round_step's `v_a` (cur_valid, replicated) → engine_top forwarding bypass mux (v2c_o1 / c2v_o0) → CNU | 20 | 71.5% | the forwarding glue I wrote in engine_top |
| **pf_p1_lutram @ 7.36 ns** | gamma lane g8 register → engine_top g8 init mux → round_step VNU (cur) → v2c | 22 | 67.5% | gamma lane → VNU |

After the prefetch, the prior read is no longer on the critical path. engine_top_pf is limited by the VNU path itself (g8 / prior → bias → total → v2c) and by the forwarding mux select, at 136 MHz.

### Memory per field (engine_top, VNU_PASSES 1)

BRAM counts come from the routed checkpoints. In the BRAM runs, the hierarchical utilization report omits some state_mem instances (bank 0, and c2v_o1 in VNU_PASSES 2), although its total of 464 includes them.

| Field | Bits per slot | × 12 slots | LUTRAM (LUTRAM run) | LUT in instance (LUTRAM run) | FF (output register) | BRAM36 (BRAM run) |
|---|---|---|---|---|---|---|
| v2c_o0 | 7,920 | 95,040 | 4,528 | 4,672 | 7,920 | 110 |
| c2v_o1 | 4,680 | 56,160 | 2,676 | 10,243 | 4,680 | 65 |
| marg HP_r, bank 0 / 1 | 3,528 | 42,336 each | 2,016 / 2,016 | 2,016 / 19,980 | 3,528 each | 49 / 49 |
| marg HP_rm1, bank 0 / 1 | 3,528 | 42,336 each | 2,016 / 2,016 | 2,016 / 4,788 | 3,528 each | 49 / 49 |
| marg NP, bank 0 / 1 | 1,512 | 18,144 each | 864 / 864 | 864 / 6,085 | 1,512 each | 21 / 21 |
| g8_r | 2,160 | 25,920 | 1,236 | 4,931 | 2,160 | 30 |
| g8_rm1 | 1,512 | 18,144 | 864 | 22,970 | 1,512 | 21 |
| **Total** | **33,408** | **400,896** | **19,096 (2.0%)** | — | 33,408 | **464 (21.5%)** |

- **BRAM count is set by width, not depth.** Each field uses ⌈bits per slot ÷ 72⌉ BRAM36, so only 12 of each BRAM's 512 rows are used, about 2.3%.
- **LUT per instance:** with `flatten_hierarchy rebuilt`, Vivado moves surrounding logic into some instances, such as the read-bank mux and the g8 decode. Examples are 19,980 LUT in bank-1 HP_r and 22,970 in g8_rm1. So LUT per instance is not memory-only; the LUTRAM column is the memory itself.
- **Rest of engine_top (LUTRAM, VNU_PASSES 1):**
  - round_step: 298,459 LUT, 39,308 FF.
  - 720 gamma lanes: 50,498 LUT, 14,400 FF.
  - conv_check: 17,562 LUT. commit: 3,021 LUT. ctrl: 772 LUT.
  - engine_top's own registers: 26,724 FF.

### Time per W12_C8 iteration (computed from the measured clocks)

The formula is 12 round steps × cycles per step × period, plus the conv-check latency (5 cycles) once. That is 29 cycles for VNU_PASSES 1 and 41 cycles for VNU_PASSES 2. With the overlapped check in engine_top_pf, the check is hidden, so 24 cycles. Test 1e W12_C8 targets (ns per iteration):

| p | (a) | (b) | (c) | (d) |
|---|---|---|---|---|
| 0.003 | 99 | 6 | 32 | 145 |
| 0.002 | 208 | 24 | 72 | 300 |

| Design | Clock | Cycles per iteration | ns per iteration | Meets at p = 0.003 | Meets at p = 0.002 |
|---|---|---|---|---|---|
| engine_top P1 LUTRAM | 107.2 MHz (9.33 ns) | 29 | 270.6 | none | (d) |
| engine_top P1 BRAM | ≈98.1 MHz (est.) | 29 | ≈295.6 | none | (d), est. |
| engine_top P2 LUTRAM | 113.6 MHz (8.80 ns) | 41 | 360.8 | none | none |
| engine_top P2 BRAM | 98.9 MHz (10.11 ns) | 41 | 414.5 | none | none |
| **engine_top_pf P1 LUTRAM** | **135.9 MHz (7.36 ns)** | **24** | **176.6** | none | **(a), (d)** |

- **p = 0.001:** there is no W12_C8 row; Test 1d did not run W12_C8 at p = 0.001. I did not substitute another trace.
- **As built, the gap between iterations is longer than the formula's 5 cycles.** Derived from the RTL, not simulated: it is VNU_PASSES + 10 cycles (conv_req delay VNU_PASSES + 3, check 5, ctrl turnaround 2). That gives 36 cycles (335.9 ns) for P1 LUTRAM and 49 cycles (431.2 ns) for P2 LUTRAM. engine_top_pf hides the gap except in the first iteration of each relay leg.
- **Clock needed (derived, 24 cycles per iteration):**

  | p | Criterion | Target | Clock needed |
  |---|---|---|---|
  | 0.003 | (d) | 145 ns | 6.04 ns (165.5 MHz) |
  | 0.003 | (a) | 99 ns | 242 MHz |
  | 0.003 | (c) | 32 ns | 750 MHz |
  | 0.002 | (c) | 72 ns | 333 MHz |

### Run times
- engine_top runs: 22–25 min synth, 30–49 min place, 19–41 min route.
- round_step runs: about 11 min synth, 24–35 min place, 12–27 min route.

## What this means
- **The prior read was the first wall, and prefetching removes it.** In every original engine_top and round_step run, the critical path starts at the round index, goes through the 13:1 prior read and the broadcast to 72 positions, and ends in the CNU or VNU (21–25 logic levels, 70–80% routing).
  - Prefetching one step ahead with duplicated copies raises round_step (VNU_PASSES 1) from 109.9 to 147.9 MHz (+35%).
  - It raises engine_top (VNU_PASSES 1, LUTRAM) from 107.2 to 135.9 MHz (+27%), confirmed post-route, with bit-exactness re-verified on the golden vectors.
- **The next limits in the engine are the VNU path and integration glue, not a new arithmetic problem.**
  - engine_top_pf is bound by gamma lane / prior → VNU bias → total → v2c, and by the forwarding-mux select (one valid flag driving the bypass mux into every CNU input).
  - The single VNU is only good for about 194 MHz on its own (215 MHz without the bias saturator). So the VNU sets a ceiling of roughly 190–200 MHz for this pipeline depth even with perfect integration.
  - In round_step_pf_p1, the stage A → stage B net (6.7 ns of pure wire) is now the limit. Giving that transfer two cycles, or adding a second tree level, would remove it.
- **VNU_PASSES 2 saves area but not time.** It uses about 20% fewer LUTs in engine_top (358,534 vs 448,124 for LUTRAM) at a similar clock, but needs 3 cycles per step instead of 2. So it is about 33% slower per iteration in every variant.
- **LUTRAM is cheaper than BRAM for this memory.** The 12-deep, very wide fields waste BRAM: 464 BRAM36 (21.5% of the device) hold 400,896 bits at 2.3% depth use. The same memory in LUTRAM is 19,096 LUTs (2.0% of LUTRAM), and the clocks are similar or better (107 vs 98 MHz for P1).
- **Against the Test 1e W12_C8 targets:** the best engine (pf, 176.6 ns per iteration) meets (a) and (d) at p = 0.002 and nothing at p = 0.003. Meeting p = 0.003 (d) would need about 165 MHz with this cycle count; the stricter latency criteria need a clock far above what this engine reaches. These are computed from measured clocks; no engine has been simulated end to end.

## For Test 2d (analytic only, as requested)
- **Compressed c2v storage per check:** store min1, min2, the min1 index and 35 signs instead of 35 messages (c2v_o1: 4,680 bits per slot today).
- **v2c not stored:** recompute it as sat(marginal − c2v) at the CNU input (v2c_o0: 7,920 bits per slot today, the largest field).
- **Per-error prior RAM:** cost for non-uniform noise, instead of the 10 × 13 register file.

## Not tested
- **engine_top and engine_top_pf as whole engines** are synthesis-only integrations with no functional simulation. Their "identical results" rest on the round_step_pf replay and the ctrl_pf testbench. Simplifications kept: no sliding window, syndromes by window index, prior row = global round mod 13.
- **The NR_MIN guard in ctrl_pf** (the memory read-after-write order for windows shorter than 4 rounds in P1, 3 in P2) is untested, because no testbench models the engine memories.
- **Negative priors:** the sign-magnitude conversion is not exercised, since every prior in the test data is ≥ 0. The original round_step has the same gap.
- **Variants not built:** engine_top_pf for P1 BRAM and for P2; round_step_pf_p2 at its estimated fmax; the fixes named under "What this means" (forwarding-mux select, the A → B tree level). The VNU path itself was not pipelined.
- **Placement settings:** everything uses default directives and one seed; no phys_opt_design, retiming, or placement strategies.
- **Power:** not reported.

Files: hw/synth/ (scripts `run_block.tcl`, `queue_2c.sh`, `queue_pf.sh`, `rerun_fmax.sh`, `gen_harness.py`, `collect.py`, `bram_by_field.tcl`; logs in `logs/`; per-run reports in `runs/<run>/`; `results.json`). RTL: `hw/rtl/round_step_pf.sv` (verified) and `hw/synth/rtl_2c/{engine_top,engine_top_pf,ctrl_pf,prior_rf,vnu_nosat}.sv` (synthesis only). Tests: `hw/tb/tb_round_step_pf.sv`, `hw/tb/tb_ctrl_pf.sv`, `hw/tb/pf_verify.sh`.

---

# 2c follow-up: engine_top_pf2 (three timing fixes, no datapath change)

## Setup
- **Changes from engine_top_pf (LUTRAM):**
  1. **Forwarding-mux select duplicated:** round_step_pf2 outputs `cur_valid_dup[72]`, one copy of cur_valid per position (keep, max_fanout 256; same input and reset as cur_valid). In engine_top_pf2, copy p selects the v2c_o1 / c2v_o0 bypass muxes of position p and enables their capture registers, about 175 mux bits per copy.
  2. **Two-level prior fan-out tree:** stage A (registered read) → 6 copies (stage A2) → 18 copies (stage B). Each hop takes one cycle, so the priors are prefetched two steps ahead in the static round order.
     - B is replaced at most once per step, after the step has started (`b_fresh`).
     - `pf_flush` (driven by `start`) drops priors prefetched for steps that never ran at the end of the previous decode. I found this need while designing it: without it, the next decode's first step could use stale priors.
     - Still VNU_PASSES + 1 cycles per step.
  3. **vnu_nosat inside round_step:** the bias saturator is removed (unreachable, Test 2a). vnu_nosat.sv moved from synth/rtl_2c into hw/rtl, since it was verified in 2a.
- **Files:** `hw/rtl/round_step_pf2.sv` (verified), `hw/synth/rtl_2c/engine_top_pf2.sv` (synthesis only), `hw/tb/tb_round_step_pf2.sv`, `hw/tb/pf2_verify.sh`, `hw/synth/queue_pf2.sh`.
- **Flow:** same as 2c (OOC, post-route, 2.5 ns, then a confirmation run at the estimated period); 8 cores for Vivado, 4 for Verilator at nice 5.

## Bit-exactness (measured, Verilator)

| Test | Result |
|---|---|
| round_step_pf2 replay, 3-shot vectors, VNU_PASSES 1 / 2 | 4,719 steps, 5,384,016 error updates, **0 mismatches**; latency 2 / 3 cycles; in_ready errors 0 |
| round_step_pf2 replay, 10-leg shot 53, VNU_PASSES 1 / 2 | 7,540 steps, 8,602,560 error updates, 10 leg starts, **0 mismatches** |
| `+FLUSH` replay, 3-shot, VNU_PASSES 1 / 2 | 362 flushes: at every iteration start the two prefetches carry round 12 (wrong), then flush and reload; **0 mismatches** |
| cur_valid_dup == cur_valid, checked every cycle (simulation-only $fatal) | never fired in any run |
| tb_ctrl_pf (ctrl_pf vs ctrl), STEP_CYCLES 2 / 3 | 204 decodes each, **0 mismatches** (unchanged from 2c) |
| Mutants | **4 of 4 caught:** B replaced before its step ran; A2 move blocked when B moves; move in pass A for VNU_PASSES 2; flush not clearing A2 / B |

## Results (post-route, measured)

| Run | Period | WNS | LUT | FF | LUTRAM | Logic levels | Routing |
|---|---|---|---|---|---|---|---|
| engine_top_pf2 P1 | 2.5 ns | −4.339 (est. 146.2 MHz) | 443,894 (10.86%) | 127,804 (1.56%) | 19,096 (2.00%) | 20 | 69.9% |
| engine_top_pf2 P1 | **6.84 ns** | **+0.048 → 146.2 MHz confirmed** | 450,227 (11.02%) | 127,677 (1.56%) | 19,096 (2.00%) | 19 | 69.5% |
| engine_top_pf2 P2 | 2.5 ns | −5.145 (est. 130.8 MHz) | 372,856 (9.13%) | 120,071 (1.47%) | 19,096 (2.00%) | 19 | 73.7% |
| engine_top_pf2 P2 | **7.65 ns** | **+0.086 → 130.7 MHz confirmed** | 375,741 (9.20%) | 119,816 (1.47%) | 19,096 (2.00%) | 19 | 74.6% |

No BRAM or DSP in any of these runs; every run routed completely (0 unrouted nets).

**Confirmed clocks against earlier variants:**

| Design | VNU_PASSES 1 | VNU_PASSES 2 |
|---|---|---|
| engine_top | 107.2 MHz | 113.6 MHz |
| engine_top_pf | 135.9 MHz | not built |
| **engine_top_pf2** | **146.2 MHz (+7.6% vs pf, +36% vs engine_top)** | **130.7 MHz (+15% vs engine_top)** |

**Critical paths:**

| Run | Start → end | Logic levels | Routing | Block |
|---|---|---|---|---|
| P1 @ 6.84 ns | VNU v2c output register (round_step, cur unit) → bypass mux → CNU → CNU output register | 19 | 69.5%, 6.77 ns datapath | step-to-step loop: a VNU result goes through the forwarding path into the next step's CNU |
| P1 @ 2.5 ns | cur_valid copy `g_cvd[25]` → bypass mux → CNU output register | 20 | 69.9% | CNU tree behind the bypass mux (the select now has a fanout of ~175, not ~12,600) |
| P2 @ 7.65 ns | cur_valid copy `g_cvd[47]` → bypass mux → CNU output register | 19 | 74.6% | same |
| P2 @ 2.5 ns | gamma lane g8 register → shared VNU (pass mux) → v2c | 19 | 73.7% | gamma lane → VNU |

- **Instance sizes in the confirmation runs:**
  - round_step_pf2: 301,131 LUT / 42,662 FF (P1) and 212,871 / 35,113 (P2).
  - conv_check: about 20,400–20,800 LUT.
  - ctrl_pf: about 900–1,060 LUT.
- **Gone from the critical path:** the prior read and broadcast, the A → B wire, and the single-flop mux select. The remaining limit is the 35-input CNU tree with the bypass mux in front of it. On its own the CNU closes at 4.26 ns (234.7 MHz); inside the engine it takes 6.8–7.5 ns, about 70% of it routing.

## Time per iteration (computed from the confirmed clocks)
- **Cycles per iteration (derived from the RTL):** with the overlapped convergence check, an iteration is steps × cycles per step. That gives 12 × 2 = 24 cycles (P1) or 12 × 3 = 36 (P2) for W12_C8, and 13 × 2 = 26 or 13 × 3 = 39 for the full 13-round decode.
- **Leg starts:** the first iteration of each relay leg is not overlapped and adds VNU_PASSES + 10 cycles. With the formula's single 5-cycle conv latency instead, the numbers are in the "+5" column.

| Design | Clock | W12_C8, overlapped | W12_C8, +5 cycles | 13 rounds, overlapped | 13 rounds, +5 cycles |
|---|---|---|---|---|---|
| **pf2 P1** | 146.2 MHz (6.84 ns) | **164.2 ns** (24 cycles) | 198.4 ns (29) | **177.8 ns** (26) | 212.0 ns (31) |
| pf2 P2 | 130.7 MHz (7.65 ns) | 275.4 ns (36) | 313.7 ns (41) | 298.4 ns (39) | 336.6 ns (44) |

**Against the Test 1e W12_C8 targets** (ns per iteration):

| p | Targets (a / b / c / d) | pf2 P1 (164.2 ns) | pf2 P2 (275.4 ns) |
|---|---|---|---|
| 0.003 | 99 / 6 / 32 / 145 | none | none |
| 0.002 | 208 / 24 / 72 / 300 | (a), (d) | (d) |

There is no W12_C8 row at p = 0.001.

**Against the Test 1f k = 1 targets for the 13-round decode** (int4.2.8; a / b / c / d):

| p, T | Targets | pf2 P1 (177.8 ns) | pf2 P2 (298.4 ns) |
|---|---|---|---|
| 0.003, T = 12 µs | 277 / 13 / 63 / 327 | (a), (d) | (d) |
| 0.003, T = 8 µs | 184 / 11 / 60 / 258 | (a), (d) | none |
| 0.002, T = 12 µs | 626 / 56 / 162 / 631 | (a), (d) | (a), (d) |
| 0.002, T = 8 µs | 417 / 43 / 133 / 569 | (a), (d) | (a), (d) |

- **Clock needed for W12_C8 at p = 0.003, criterion (d)** (derived, 24 cycles per iteration): 165.5 MHz. pf2 P1 is 12% short of it at 146.2 MHz.

## What this means
- **The three fixes add another +7.6% for P1** (135.9 → 146.2 MHz), and the prior, A → B and mux-select paths are gone from the top of the timing report. **For P2, pf2 brings 113.6 → 130.7 MHz.**
- **The limit is now the datapath loop itself:** VNU result → forwarding → 35-input CNU tree of the next step, in one cycle. Going further means changing that loop (more cycles per step, or a pipelined CNU), which is a datapath or schedule change and was outside this task.
- **P1 is still the faster engine per iteration:** 164 vs 275 ns for W12_C8, at 20% more LUTs (450k vs 376k).
- **Targets:** the best engine meets W12_C8 (a) and (d) at p = 0.002 and nothing at p = 0.003. For the full 13-round decode it meets (a) and (d) at both p.

## Not tested
- **engine_top_pf2 as a whole engine** (synthesis only), like engine_top and engine_top_pf. The two-ahead prefetch order and the flush in the engine rely on ctrl issuing the first step at least 3 cycles after `start` (step_valid at start + 2, round_step start at start + 3). That is read from the ctrl RTL, not simulated.
- **Which fix bought what:** no ablation; the three fixes were synthesized together.
- **P1 / P2 BRAM variants of pf2;** round_step_pf2 on its own.
- **Implementation settings:** default directives and one seed only.

---

# 2c re-synthesis (3d fixes)

## Setup
- **Design:** engine_top_pf2, VNU_PASSES 1, LUTRAM. Run name `engine_top_pf2fix_p1_lutram`; the earlier `engine_top_pf2_*` runs are kept unchanged.
- **Changes since the 2c follow-up** (all found or required by the Test 3d closed-loop simulation):
  1. **v2c_o0 prev write-back merge:** edges of the one-round types keep the value of the cur write. Registers `lc_v2c_o0` / `lc_q`, plus a 7,920-bit 2:1 merge.
  2. **No prev write for step 0** (it targeted window slot −1).
  3. **Decode-start path M(−1) = L0:**
     - At `start`, a fill unit writes the priors into all W slots of both marginal banks, one slot per cycle.
     - The source is an engine copy of the 10 × 13 prior register file, written by the same load port. round_step_pf2 is unchanged.
     - The fill shares the banks' write ports, before any engine write. It runs in parallel with the prefetch preload; syndromes arrive on their own port.
     - ctrl starts when the fill ends, and `done` is held low meanwhile.
- **Flow:** same as 2c: OOC synth → opt → place → route, 2.5 ns, then a confirmation run at the estimated period. Run in tmux sortq_queue (window `fix`), 4 threads.

## Functional check (measured, Verilator)
The Test 3d closed-loop testbench was re-run **without the backdoor**: the engine now fills M(−1) itself, and the backdoor is only active with `+BACKDOOR`.
- **Shots:** the 3 golden shots + 200 random from the 3d extended set (per p: 90 converging in leg 0 + 10 converging in legs 1–3).
- **Result: 203 shots, 0 mismatches** in iterations, success, all hard decisions and all 12 observables. 180 converged in leg 0; 5,398 iterations in total.
- **Cycles added by the fill: 14 per decode** (W = 13 fill cycles + 1 to hand the start to ctrl). Measured: the first iteration starts 15 cycles after `start` instead of 1, and start → done is exactly 14 cycles longer on every shot (e.g. shot 106: 3,311 vs 3,297).
  - Iteration timing is unchanged: 26 cycles, 36 at leg ends, 10 at the end.
  - Decode cycles = 14 + 1 + 26·n + 10·(leg ends) + 10.
  - Only the bank read in the first iteration needs the fill. Filling that bank alone, without delaying ctrl, would cost 0 cycles. Not done, because both banks were asked for.

## Results (post-route, measured)

| Run | Period | WNS | LUT | FF | LUTRAM | Logic levels | Routing |
|---|---|---|---|---|---|---|---|
| pf2fix, P1 | 2.5 ns | −4.732 (est. 138.3 MHz) | 445,137 (10.89%) | 136,468 (1.67%) | 19,096 (2.00%) | 20 | 70.3% |
| pf2fix, P1 | **7.24 ns** | **+0.063 → 138.1 MHz confirmed** | **448,213 (10.97%)** | **136,206 (1.67%)** | 19,096 (2.00%) | 17 | 74.2% |
| pf2 (before the fixes), P1 | 6.84 ns | +0.048 → 146.2 MHz confirmed | 450,227 (11.02%) | 127,677 (1.56%) | 19,096 | 19 | 69.5% |

No BRAM or DSP; 0 unrouted nets.

- **Change vs pf2** (confirmation runs):
  - **LUT:** −2,014 (−0.4%). At 2.5 ns it is +1,243, so the fixes cost about 1–2k LUT, within the run-to-run variation between the two clocks.
  - **FF:** +8,529, mostly the merge registers and the prior-file copy.
  - **Clock:** −5.5% (146.2 → 138.1 MHz).
- **Critical paths:**
  - At 2.5 ns: VNU v2c output register (round_step, cur unit) → forwarding bypass mux → CNU → CNU output register; 20 logic levels, 7.21 ns datapath, 70% routing. The same loop as pf2.
  - At 7.24 ns: gamma lane g8 register → g8 init mux → VNU (cur) → v2c; 17 logic levels, 7.16 ns datapath, 74% routing. The same kind of path as engine_top_pf.
  - None of the new logic (merge, fill) is on the critical path. The lower clock appears to come from the extra registers adding placement / routing pressure on the existing VNU → CNU and g8 → VNU paths. That is inferred, not measured.
- **Time per iteration** (measured 26-cycle iteration, Test 3d):
  - 13-round iteration: **26 × 7.24 ns = 188.2 ns** (was 177.8);
  - W12_C8 iteration (24 cycles): **173.8 ns** (was 164.2);
  - leg-end iterations: 36 cycles = 260.6 ns;
  - plus 25 cycles per decode (14 fill + 1 + 10 end) = 181 ns, and 16 commit cycles.
- **Criteria** (Test 1e / 1f, same targets as before): unchanged.
  - W12_C8: meets (a) and (d) at p = 0.002 (208 / 300 ns), nothing at p = 0.003.
  - 13-round decode: meets (a) and (d) at p = 0.002 and 0.003 for both T = 12 and 8 µs.

## Re-run of the models with the new engine (`REF_RUN` / `SORTQ_REF_RUN` = this run)
Outputs: `results/test2d/refix/`, `results/test3f/builds_refix/`; the old outputs are kept.

**Test 2d Pareto (`refix/pareto.csv`)**, only rows that changed:

| Design | LUT old → new | Clock old → new | ns / 13-round iteration old → new | W12_C8 old → new |
|---|---|---|---|---|
| SORTQ pf2 P1 k = 1 | 450,227 → 448,213 | 146.2 → 138.1 MHz (measured) | 177.8 → 188.2 | 164.2 → 173.8 |
| SORTQ pf2 P1 k = 2 | 751,358 → 749,071 | 146.2 → 138.1 (assumed) | 95.8 → 101.4 | n/a |
| SORTQ pf2 P1 k = 3 | 1,052,489 → 1,049,929 | 146.2 → 138.1 (assumed) | 68.4 → 72.4 | n/a |
| SORTQ pf2 P1 k = 4 | 1,353,620 → 1,350,787 | 146.2 → 138.1 (assumed) | 54.7 → 57.9 | n/a |

The criteria met (a / b / c / d at p = 0.001 / 0.002 / 0.003) are the same in every row. The P2 and pf rows are unchanged; they still use their old runs, which don't have the fixes.

**sortq estimates (2e / 3f)**, calibration 0.9728 → 0.9715:

| Code | Engine old → new |
|---|---|
| [[72,12,6]] | 201,472 → 200,936 |
| [[144,12,12]] | 450,227 → 448,213 (measured X) |
| [[288,12,18]] | 995,913 → 990,160 |

The fully parallel figures don't depend on the engine and are unchanged.

**3g:**

| Code | Block (X + Z) old → new | Blocks per FPGA | Logical qubits per FPGA |
|---|---|---|---|
| [[144,12,12]] | 900,454 → 896,426 (21.9%) | 3 (3.65) | **36, unchanged** |
| [[288,12,18]] | 1,991,826 → 1,980,321 (48.5%) | 1 (1.65) | **12, unchanged** |

IBM comparison unchanged.

## What this means
- **The engine is now complete for a decode** without testbench help: it fills M(−1) at `start` in 14 cycles. It decodes exactly like the software on all 203 shots, and the fixes cost no LUT to speak of.
- **The price is clock, not area:** 146.2 → 138.1 MHz (−5.5%), so 188 ns per 13-round iteration and 174 ns per W12_C8 iteration.
  - No real-time criterion changes.
  - The logical-qubit counts per FPGA don't change (36 / 12).

## Not tested
- **The 0-cycle variant** (filling only the first-read bank): not built.
- **Other engine variants with the fixes:** the P2, BRAM and pf variants were not re-synthesized.
- **Placement settings:** default directives and one seed; the 5.5% clock change may be partly placement noise between two runs.
- **Gate-level / post-route simulation:** none.
