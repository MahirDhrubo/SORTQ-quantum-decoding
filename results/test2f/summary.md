# Test 2f: red-black pipelined round engine (engine_top_rb)

## Setup
- **Goal:** a round engine for the gross-code X decoder that issues one round step per cycle, in red-black order 0, 2, …, 12, 1, 3, …, 11. It uses the same int4.2.8 arithmetic (ARITHMETIC.md), VNU_PASSES 1 and LUTRAM. Test 1g showed that this order is bit-identical to the 2-layer even / odd schedule.
- **Where:** the server `hw/rb/` (`gen`, `rtl`, `tb`, `golden`, `sim`, `synth`), mirrored locally.
  - New files only. engine_top_pf2, round_step_pf2, ctrl_pf and their testbenches are untouched.
  - cnu, vnu_nosat, gamma_src, state_mem, round_wiring, conv_check and commit are reused unchanged.
- **Tools:** Verilator 5.054 (`the HDL environment`, at most 4 cores, nice 10). Vivado 2025.2, xcvu19p-fsva3824-2-e, 4 threads; runs started after the other session's re-synthesis job.
- **Problem:** one window = the whole 12-round circuit (13 detector rounds, win_t = 0, W = 13, C = 13), as in Test 3d.

### Step 1: golden reference (rb13)
- **Decoder:** relay_bp int4.2.8 with the Test 1b settings. The layer id of a round-r check is its position in the order (`golden_rb.py`). The dump field "layer" is that position, so round = ORDER[layer].
- **The dump build accepts the layer ids:** dump build (dump off) vs `the relay_bp environment` on the 2,000 Test 2a syndromes: identical iterations, success, decodings and saturation counters. Against the sweep, 1,818 shots differ in iterations, as expected.
- **Dumps:** dump on vs dump off gives identical results for every dumped shot.

  | File | Shots (syndrome index) | Iterations (rb13) | Legs dumped | Leg starts |
  |---|---|---|---|---|
  | `dump_rb_shot{0,1,2}` | 96, 106, 53 (Test 2a picks) | 31, 41, 164 | 0–1 | 1 + 1 + 2 |
  | `dump_rb_legs10_shot0` | 53 | 164 | 0–2 (all) | 3 |
  | `dump_rbx_shot{0,1}` | 5, 141 (picked from the rb decodes: leg 1) | 91, 139 | 0–1 | 2 + 2 |
  | `dump_rb_legs10b_shot0` | 1855 (rb, 10 legs) | 586 | 0–9 (all) | 10 |

  Under rb, the 3 Test 2a picks converge earlier: 96 and 106 in leg 0, 53 in leg 2. They have only 2 relay-leg boundaries between them, so 5, 141 and 1855 were added for leg coverage.

### Step 2: design
- **Leg-start gating (your rule):** derived from H and the order by enumeration over every edge (`rb/gen/gen_rb_pkg.py` → `rb_pkg.sv`). The generator asserts that the result depends only on the pass, so the hardware has one table per pass.
  - CNU input (check round c, error e) = L0 iff no round of e comes before c in the order. VNU c2v from check round c′ = 0 iff c′ comes later than the current step.

  | Pass | CNU inputs gated | VNU c2v gated |
  |---|---|---|
  | even rounds (first colour) | all 35 base edges | cur group: the offset-1 slots (13); prev group: the offset-0 slots (10) |
  | odd rounds | 12 of 35: the one-round types T01, T03, T09 (offset 0) | none |

- **Hazard distance (from H):**
  - Consecutive steps never share an error, including 12 → 1 and 11 → 0 (next iteration).
  - Two steps that share an error are at least **6** issue slots apart. Example: step 1 (slot 7) → step 0 of the next iteration (slot 13).
- **Pipeline (`round_step_rb`, one new step every cycle):**

  | Stage | Work |
  |---|---|
  | S0 | ctrl outputs; prior register-file read (A) |
  | S1–S2 | prior fan-out copies A2 (6) → B (18); S2: v2c read (LUTRAM, asynchronous) → register |
  | S3 | leg-start init mux → wiring → **CNU stage 1** (5 groups of ≤ 8 edges, each the unchanged cnu.sv: min1 / min2 / index / parity); M(t−1) and g8 read → register; first iteration of a decode: M(t−1) = prior (**M(−1) = L0 path**) |
  | S4 | **CNU stage 2** (`cnu_merge_rb`: same 2-min merge); **bias** = vnu_nosat (bias output only), in parallel with the CNU; stored c2v read |
  | S5 | c2v valid → C memories written; back wiring → `vnu_post_rb` (vnu_nosat's total / marginal / v2c, copied, bias as input) |
  | S6 | marginals, hard decisions, v2c written |

- **Read → write latency (no stalls needed):**
  - v2c: 4 cycles (read S2, write S6). M: 3. c2v: 1.
  - **Maximum allowed: 5 cycles.** LUTRAM writes synchronously and reads asynchronously, so a write in cycle t is seen by a read in t + 1, not t. With a 6-slot hazard distance, the dependent read is at t_issue + 6 + a, so write ≤ read + 5. This is measured below.
  - No bubbles at colour or iteration boundaries.
- **Memory (`engine_top_rb`):**
  - Banked by home-round parity: bank = window index i[0], address i >> 1, 7 slots.
  - Per-type-class instances serve as per-type write enables, so the one-round types are never written by the prev write-back. The 3d bug cannot occur and there is no merge register.
  - Role muxes: cur = bank g[0], prev = the other bank.

  | Field (per home h) | Bits | Read | Write |
  |---|---|---|---|
  | VHP: v2c of the 7 two-round types (10 o0 + 13 o1 edges) | 8,280 | S2 | S6, cur or prev |
  | VNP: v2c of T01, T03, T09 (12 o0 edges) | 4,320 | S2 | S6, cur only |
  | C0: c2v from round h, two-round types | 3,600 | S4 (prev) | S5 (cur) |
  | C1: c2v from round h + 1 | 4,680 | S4 (cur) | S5 (prev) |
  | MHP / MNP marginals × 2 copies (iteration parity) | 2 × 5,040 | S3, copy ~par | S6, copy par |
  | G: g8 + 2, 3 bits | 2,160 | S3 | S3 / prefill |
  | **Total per home (13 homes)** | **33,120 (430,560 bits)** | | |

- **Decode start (0 extra cycles):** M(−1) = L0 through the bias-input mux, and g8 = G0 = 1 as a constant in leg 0. This replaces pf2's fill unit (W cycles per decode).
- **Relay legs ≥ 1:** the even pass needs new g8 for two home rounds per step (g and g − 1).
  - So the 720 lanes pre-draw the 6 odd rounds during the leg-end wait (starting 3 cycles after the last step's g8 read).
  - They draw the even rounds at the even init steps (draw at S2, used and written at S3).
  - 13 draws per leg, as in pf2. ctrl_rb waits for the prefill (never needed: the convergence wait is longer).
- **Convergence check:** overlapped with the next iteration, as in pf2. Hard decisions are in 2 banks by iteration parity, and the check starts 7 cycles after the last step (after its S6 write).
- **Hazard assertion (simulation only, in engine_top_rb):**
  - Schedule model: every step registers its write cycles per (field, bank, address). Every read is checked against the latest write scheduled by an earlier step (it must land before the read), and every write against reads already scheduled (WAR).
  - Every real memory write-port event must match the schedule.
- **Window:** only W = 13 = NRND with win_t = 0 (asserted in simulation).

### Step 3: verification set-up
- **Vectors (`gen_vectors_rb.py`):** hardware memory view. Nothing is cleared at a leg start, never-written messages hold junk (deterministic random), and M at decode start is junk.
- **Round-step replay (`tb_round_step_rb`):** steps back to back, every input in its stage (S0 / S2 / S3 / S4), so up to 7 steps are in flight.
  - Compared every step: all 2,520 c2v (sign and magnitude), the bias, and the marginal, hard decision and v2c of every updated error.
- **Closed loop (`tb_engine_rb`):** the Test 3d testbench adapted.
  - No backdoor. The engine is not reset between shots, so every decode starts on the previous shot's memory contents.
  - Gamma lanes in LOAD mode, loaded with the software g8 of (lane_leg, lane_home).
  - **Shots:** the 6 golden shots, plus 250 random shots per p (225 converging in leg 0, 25 in legs 1–3). They are drawn from the first 40,000 shots of the Test 1g rb13 traces (seed 20261116).
  - **Software reference:** rb13 decoder. Its iterations equal the Test 1g trace for all 500 random shots (asserted).
  - g8 per leg comes from the dump 'L' records. It is identical in all sweep and rb dumps that contain a leg (asserted), so it depends neither on the shot nor on the order.

## Results

### Gating rule D′ against the golden inputs (measured, all 6 shots)
| Check | Count | Mismatches |
|---|---|---|
| CNU inputs = (init ∧ gate) ? L0 : stored | 36,561,024 (435,456 gated; 430,771 of them stale ≠ golden) | **0** |
| VNU stored c2v inputs = (init ∧ gate) ? 0 : stored | 23,687,424 (208,656 gated; 206,009 stale ≠ golden) | **0** |
| first-iteration mem_post = L0 (M(−1)) | 103,824 | **0** |
| g8 = L record of the leg | every error update | **0** |

### Round-step replay (measured)
| Vectors | Steps | Init steps / first-iteration steps | Leg starts | c2v compared | Error updates | Mismatches |
|---|---|---|---|---|---|---|
| shots 96, 106, 53 (legs 0–1) | 2,756 | 52 / 39 | 4 | 6,945,120 | 3,144,384 | **0** |
| shot 53 (all 3 legs) | 2,132 | 39 / 13 | 3 | 5,372,640 | 2,432,448 | **0** |
| shots 5, 141 | 2,990 | 52 / 26 | 4 | 7,534,800 | 3,411,360 | **0** |
| shot 1855 (10 legs) | 7,618 | 130 / 13 | 10 | 19,197,360 | 8,691,552 | **0** |
| **Total** | **15,496** | 273 / 91 | 21 | 39,049,920 | 17,679,744 | **0** |

### Closed loop (measured, 506 shots, final RTL)
- **506 / 506 OK:** same iterations, success, all 4,444,704 hard decisions and all 12 observables as the rb13 software. 12,047 iterations, 82 relay-leg starts.
- **Hazard assertion:** 1,336,864 reads checked, **0** RAW and **0** WAR violations. All 1,264,697 real writes matched their scheduled cycle.
- **Issue gaps inside an iteration:** 0. PEND_WAIT cycles: 0.

| p | Kind | Shots | OK | Iterations min / median / max | Mean | Leg starts | Cycles / iteration (whole decode: mean, range) |
|---|---|---|---|---|---|---|---|
| 0.003 | golden | 6 | 6 | 31 / 115 / 586 | 175.3 | 13 | 13.29 (13.19–13.45) |
| 0.003 | leg0 | 225 | 225 | 4 / 10 / 80 | 12.4 | 0 | 14.49 (13.18–16.50) |
| 0.003 | legs1to3 | 25 | 25 | 86 / 103 / 243 | 138.4 | 40 | 13.26 (13.19–13.31) |
| 0.002 | leg0 | 225 | 225 | 2 / 8 / 52 | 8.7 | 0 | 15.11 (13.27–20.00) |
| 0.002 | legs1to3 | 25 | 25 | 89 / 103 / 167 | 111.3 | 29 | 13.26 (13.22–13.30) |

**Cycles (measured in simulation):**
- **Normal iteration: 13 cycles** (iter_start to iter_start), all 11,375 of them; the check of iteration t is hidden under t + 1.
- **Exact for all 506 shots:** cycles(start → done) = **2 + 13·n + 13·(leg ends) + 12**, 0 residual. So:
  - decode start: 2 cycles to the first step (pf2 with its fill: 1 + W);
  - each relay-leg end: +13 cycles (not overlapped: last step → write S6 → check 5 cycles → ctrl; pf2: +10);
  - decode end: 12 cycles after the last iteration starts.
- **Against pf2 (Test 3d):** 13 vs 26 cycles per normal iteration.

The first full run flagged 2 shots (29512 and 23359), although they matched the software in everything. Both converged in the last iteration of a leg (iterations 80 and 140). The engine had already pre-drawn the next leg's g8, which is correct, because the words are unused once the decode stops, but the testbench counted that draw as "g8 of a leg the shot never reaches". The check now flags a prefill leg only if that leg actually starts. Final run: 506 / 506 (above).

### Maximum read-to-write depth (measured)
`V_WB_DLY` (simulation-only parameter) adds register stages to the v2c write-back. Closed loop on 56 shots (6 golden + 50 random):

| v2c read → write | Mismatching shots | RAW hazards (reads before a pending write landed) |
|---|---|---|
| 4 cycles (design) | 0 / 506 | 0 |
| 5 cycles | 0 / 56 | 0 |
| 6 cycles | 55 / 56 | 28,942 (first: step of round 1 reads VHP bank 1 in the cycle the write lands) |

**The exact maximum is 5 cycles from read to write-back** (6 stages counting the read stage). At 5 the checker also reports 32,866 "unscheduled" writes. Those come from its single-entry schedule per word (two writes to a word are then pending at once), not from wrong data.

### Mutants (one bug each; all caught)
| Mutant | Test | Result |
|---|---|---|
| no CNU gating in the odd pass (the planning error you corrected) | replay, shots 5 / 141 | 24 steps mismatch |
| sweep gating rule (offset 0 gated in both passes) | replay | 47 steps |
| no VNU gating | replay | 28 steps |
| no M(−1) = L0 path | replay | 26 steps (bias) |
| syndrome one stage early | replay | 2,989 steps |
| bias from the wrong prior stage | replay | 1,149 steps |
| CNU merge: min2 to the local minimum of every group | replay | 2,510 steps |
| CNU merge: group parity only | replay | 2,858 steps |
| M(t−1) read from the copy being written | closed loop | 51 / 52 shots |
| no g8 prefill (odd rounds keep the old leg's g8) | closed loop | first shot with a leg start mismatches |
| c2v C1 written to the cur bank | closed loop | mismatch, hazard model flags unscheduled writes |
| VNP written by the prev group (the 3d write-back bug) | closed loop | mismatch, hazard model flags unscheduled writes |
| convergence check one cycle early (CDLY 6) | closed loop | 11 / 56 shots |

### Step 4: synthesis (post-route, measured; resources of `dut`)
| Run | Period | WNS | LUT | LUTRAM | FF | BRAM / DSP | Logic levels | Routing |
|---|---|---|---|---|---|---|---|---|
| engine_top_rb | 2.5 ns | −2.395 (est. 204.3 MHz) | 534,474 (13.08%) | 37,868 (3.96%) | 140,584 (1.72%) | 0 / 0 | 13 | 69.5% |
| engine_top_rb | 4.90 ns | **−0.345 (does not close)** | 518,572 (12.69%) | 37,868 | 140,298 | 0 / 0 | 11 | 79.2% |
| engine_top_rb | **5.25 ns** | **+0.016 → 190.5 MHz confirmed** | 512,746 (12.55%) | 37,868 (3.96%) | 140,182 (1.72%) | 0 / 0 | 13 | 71.5% |

Every run routed completely (0 unrouted nets).

**Instance sizes (4.90 ns run):**
| Instance | LUT | LUTRAM | FF |
|---|---|---|---|
| round_step_rb | 380,362 | 0 | 102,887 |
| memories (18 state_mem) | 62,741 (incl. 24,873 of role / write muxes Vivado moved in) | 37,868 | 0 |
| 720 gamma lanes | 46,818 | 0 | 14,400 |
| conv_check | 22,613 | 0 | 1,125 |
| commit | 5,288 | 0 | 180 |
| ctrl_rb | 708 | 0 | 225 |

**Critical paths:**
| Run | Start → end | Levels | Where |
|---|---|---|---|
| 2.5 ns | CNU merge output register (S4 → S5) → back wiring → vnu_post_rb (prev) → v2c register | 13 | VNU stage |
| 4.90 ns | v2c input register (S2 → S3, `r_o1`) → leg-start init mux → wiring → CNU stage-1 min2 register | 11 (first net 1.65 ns) | wiring from the memory-side register to the CNU, across the die |
| 5.25 ns | CNU merge output register → back wiring → vnu_post_rb (prev, type T08) → v2c register | 13 (5 CARRY8) | VNU stage (total and extrinsic sums); 71.5% routing |

**Against pf2 (post-route):**
| Design | W | Clock | LUT | LUTRAM | FF | Cycles / 13-round iteration | ns / iteration |
|---|---|---|---|---|---|---|---|
| engine_top_pf2 (2c follow-up, pre-3d-fix) | 12 | 146.2 MHz (6.84 ns) | 450,227 | 19,096 | 127,677 | 26 | 177.8 |
| engine_top_pf2fix (other session, 3d fixes) | 12 | 138.1 MHz (7.24 ns) | 448,213 | 19,096 | 136,206 | 26 | 188.2 |
| **engine_top_rb** | 13 | **190.5 MHz (5.25 ns)** | 512,746 | 37,868 | 140,182 | **13** | **68.25** |

### Real-time criteria (ns per 13-round iteration; targets from test1e_criteria.py)
Targets are the largest t_iter, a / b / c / d. p = 0.003 and 0.002 use the Test 1g **rb13** traces; p = 0.001 uses the Test 1f k = 1 (**sweep**) trace, since there is no rb trace at p = 0.001. engine_top_rb is 13 × 5.25 = 68.25 ns per iteration; pf2fix (a sweep engine) is checked against the Test 1g sweep targets (277 / 13 / 63 / 327, 184 / 11 / 60 / 258, 626 / 56 / 162 / 631, 417 / 43 / 133 / 569; p = 0.001 as below). Leg ends are +13 cycles, not in the per-iteration model.

| p | T | rb13 targets a / b / c / d | engine_top_rb (68.25 ns) meets | pf2fix (188.2 ns) meets (sweep targets) |
|---|---|---|---|---|
| 0.003 | 12 µs | 282 / 11 / 62 / 308 | **(a), (d)** | (a), (d) |
| 0.003 | 8 µs | 187 / 9 / 59 / 240 | **(a), (d)** | (d) |
| 0.002 | 12 µs | 524 / 49 / 134 / 628 | **(a), (c), (d)** | (a), (d) |
| 0.002 | 8 µs | 349 / 37 / 111 / 568 | **(a), (c), (d)** | (a), (d) |
| 0.001 (1f sweep) | 12 µs | 1487 / 493 / 1163 / 2125 | **all** | all |
| 0.001 (1f sweep) | 8 µs | 979 / 370 / 903 / 1408 | **all** | all |

### Step 5: k = 2 (not built; computed)
- Two same-colour rounds per cycle gives 7 slots per iteration: {0, 2}, {4, 6}, {8, 10}, {12}, {1, 3}, {5, 7}, {9, 11}.
- An error that spans rounds r and r + 1 is then in steps 3 or 4 slots apart. For example, {0, 2} → {1, 3} is 4 slots, and back to the next iteration's {0, 2} is 3.
- With this pipeline (read → write 4 cycles) the dependent step must be ≥ 5 slots away. So without forwarding, k = 2 needs about 10 cycles per iteration (5 + 5), not 7, for about twice the round-step logic.

## What this means
- **Red-black removes the step-to-step loop.** pf2's limit was VNU → forwarding mux → the next step's CNU in one cycle. In rb order no two consecutive steps share an error, and every dependent step is ≥ 6 slots later. So the round step pipelines into 6 stages with no forwarding and no stalls, and the iteration takes **13 cycles instead of 26**, measured exactly in simulation.
- **The engine decodes exactly like the rb13 software decoder:** 506 / 506 shots, including 82 relay-leg starts, decode starts on stale memory, and the overlapped check. The step datapath matches 15,496 golden steps. Leg-start gating follows your order-based rule, 0 mismatches on 60M golden inputs.
- **Clock:** 190.5 MHz confirmed post-route, against 138.1 MHz for pf2fix (+38%). The critical path is now inside one pipeline stage: the VNU sum (CNU merge register → vnu_post → v2c register, 13 levels, 5 of them carry chains), or wire from the S2 register to the CNU (4.90 ns run). There is no longer a loop across steps.
- **Cost:** 512,746 LUT (12.6% of the device), +64.5k (+14%) over pf2fix. FF +4k (140,182 vs 136,206).
  - The two-stage CNU, the bias / post split and the pipeline registers roughly replace pf2's forwarding registers and bypass muxes; the role and write muxes of the banked memory add about 25k LUT.
  - LUTRAM doubles (37,868 vs 19,096), because banking puts 7 slots in 32-deep LUTRAMs and the v2c of the offset-1 edges and both c2v directions are now stored instead of forwarded.
- **Time per iteration:** 68.25 ns vs 188.2 ns (pf2fix): **2.76× faster** per 13-round iteration (13 cycles at 190.5 MHz vs 26 at 138.1 MHz), for 14% more LUT.
  - Against the Test 1g rb13 targets it meets (a) and (d) at p = 0.003, and (a), (c) and (d) at p = 0.002, at both T. At p = 0.001 (Test 1f sweep targets) it meets everything. pf2fix meets (a) and (d) at most.
  - **(c) at p = 0.003 needs 62 ns** (59 at T = 8 µs): 4.77 ns per cycle = 210 MHz, 10% above the confirmed clock. (b) needs 11 / 49 ns, out of reach for one step per cycle.
- **Leg ends cost more** (+13 cycles vs +10). They are rare (82 in 12,047 iterations here), but the leg-end wait could be shortened by starting the check from the last write (S6) instead of a fixed 7-cycle delay.

## Not tested
- **Windowing:** W = 13 = one window only (win_t = 0, asserted). The 6-slot hazard distance and the gating tables were derived for this order and H. W = 12 sliding windows with C = 8 and the syndrome carry were not run. The pf2 synthesis numbers are for W = 12, so the memory size differs by one slot.
- **LFSR gamma mode in decoding:** LOAD mode only (as in 3d). LFSR mode was only synthesized.
- **Long decodes:** shots needing more than 10 legs, and non-converging shots.
- **k = 2:** analysis only (above).
- **Timing closure options:** default directives, one seed, no phys_opt or retiming. The limiting paths are 71–79% routing (VNU stage at 5.25 ns, S2 → CNU wiring at 4.90 ns).
- **Gate level:** RTL simulation with behavioural memories only; no post-route simulation.
- **p = 0.001 rb trace:** the criteria there use the Test 1f sweep trace.
- **Power:** not reported.

Files: `rb/gen/gen_rb_pkg.py` (→ `rb/rtl/rb_pkg.sv`, `rb_pkg_report.json`); `rb/rtl/{round_step_rb, cnu_merge_rb, vnu_post_rb, ctrl_rb, engine_top_rb}.sv`; `rb/golden/{golden_rb.py, run_golden_rb*.sh}`; `rb/tb/{gen_vectors_rb.py, tb_round_step_rb.sv, build_rs_rb.sh, mutants_rs.py, mut_rs.sh}`, logs in `rb/tb/logs/`; `rb/sim/{prep_rb.py, tb_engine_rb.sv, run_rb.sh, mutants_eng.py, mut_eng.sh}`, logs `sim_rb.log`, `mutation_eng.log`; `rb/synth/{gen_harness_rb.py, run_block_rb.tcl, queue_rb*.sh}`, runs in `rb/synth/runs/`.

---

# Timing closure attempt (engine_top_rb, no RTL change)

## Setup
- **Goal:** 4.76 ns (210 MHz), the clock that criterion (c) at p = 0.003, T = 12 µs (62 ns per 13-round iteration) needs at 13 cycles per iteration.
- **Netlist:** the same RTL and harness as above, synthesized once (`synth_design -flatten_hierarchy rebuilt`, out of context, 26 min) into `rb/synth/tc/synth.dcp`. Every variant starts from this identical netlist.
- **Implementation per variant** (`rb/synth/tc/impl.tcl`): opt_design → place_design -directive P → phys_opt_design -directive AggressiveExplore → route_design -directive Explore → phys_opt_design (post-route).
- **Variants:** 4 in parallel, 4 threads each (each peaks at about 20 GB).

  | Variant | Placement directive |
  |---|---|
  | A | Explore (item 1) |
  | B | ExtraTimingOpt (item 2) |
  | C | ExtraNetDelay_high (item 3) |
  | D | WLDrivenBlockPlacement (item 3) |

  place_design has no seed option, so item 3 uses two other placement directives instead of seeds.
- **Confirmation:** a variant that misses 4.76 ns is re-run with the same flow at period + |WNS| (rounded up to 0.01 ns), until it closes (`queue_tc.sh`, tmux sortq_queue window tc). "Confirmed clock" = a post-route run with WNS ≥ 0.

## Results (post-route, measured; resources of `dut`)
| Variant | Period | WNS after place / after route / final | Result | LUT | FF | LUTRAM | Critical path (start → end) | Levels | Routing |
|---|---|---|---|---|---|---|---|---|---|
| **A Explore** | **4.76** | +0.392 / +0.009 / **+0.009** | **closes: 210.1 MHz** | 520,369 | 140,289 | 37,868 | step-pipeline register `sp[6].i` (replica) → hard-decision register write | 2 | 96.2% |
| B ExtraTimingOpt | 4.76 | +0.129 / −0.346 / −0.294 | misses | 524,030 | 140,364 | 37,868 | VNU hard output register → hard-decision register | 0 | 98.4% |
| B ExtraTimingOpt | 5.06 | +0.386 / +0.021 / +0.021 | closes: 197.6 MHz | 515,894 | 140,295 | 37,868 | CNU stage-1 parity (group 2) → merge sign register | 1 | 97.4% |
| C ExtraNetDelay_high | 4.76 | +0.422 / −0.039 / −0.014 | misses | 518,764 | 140,296 | 37,868 | CNU stage-1 parity (group 1) → merge sign register | 1 | 97.6% |
| C ExtraNetDelay_high | 4.78 | +0.194 / +0.011 / +0.011 | closes: 209.2 MHz | 518,279 | 140,258 | 37,868 | CNU stage-1 parity (group 4) → merge sign register | 1 | 95.8% |
| D WLDrivenBlockPlacement | 4.76 | +0.348 / −0.130 / −0.107 | misses | 520,324 | 140,288 | 37,868 | `first` control copy (S3) → M(t−1) register | 1 | 97.3% |
| D WLDrivenBlockPlacement | 4.87 | +0.125 / −0.023 / +0.000 | closes: 205.3 MHz | 518,306 | 140,271 | 37,868 | `first` control copy (S3) → M(t−1) register | 1 | 97.3% |

Every run routed completely (0 unrouted nets); no BRAM or DSP.

**Confirmed clock per variant:**
| Variant | Confirmed clock |
|---|---|
| A Explore | **210.1 MHz (4.76 ns)** |
| C ExtraNetDelay_high | 209.2 MHz (4.78 ns) |
| D WLDrivenBlockPlacement | 205.3 MHz (4.87 ns) |
| B ExtraTimingOpt | 197.6 MHz (5.06 ns) |
| default flow (above) | 190.5 MHz (5.25 ns) |

**Best confirmed clock: 210.1 MHz (4.76 ns), variant A.** The target closes.

**Run times (implementation only):** opt + place 40–56 min, phys_opt 1 min, route 42–58 min, post-route phys_opt 1–11 min. About 1 h 40 min to 2 h per run.

**Time per 13-round iteration at 210.1 MHz:** 13 × 4.76 = **61.88 ns** (default flow: 68.25 ns).

| p | T | rb13 targets a / b / c / d | 190.5 MHz (68.25 ns) meets | 210.1 MHz (61.88 ns) meets |
|---|---|---|---|---|
| 0.003 | 12 µs | 282 / 11 / 62 / 308 | (a), (d) | **(a), (c), (d)** |
| 0.003 | 8 µs | 187 / 9 / 59 / 240 | (a), (d) | (a), (d) |
| 0.002 | 12 µs | 524 / 49 / 134 / 628 | (a), (c), (d) | (a), (c), (d) |
| 0.002 | 8 µs | 349 / 37 / 111 / 568 | (a), (c), (d) | (a), (c), (d) |
| 0.001 (1f sweep) | 12 / 8 µs | 1487 / 493 / 1163 / 2125; 979 / 370 / 903 / 1408 | all | all |

## What this means
- **engine_top_rb reaches 210 MHz with implementation directives only.** That is +10% over the default flow (190.5 MHz) for +7.6k LUT (+1.5%), with identical RTL and the same verified design. Against pf2fix (138.1 MHz, 26 cycles), it is 3.04× faster per iteration: 61.9 vs 188.2 ns.
- **(c) at p = 0.003, T = 12 µs is now met, with 0.12 ns to spare per iteration.** (c) at T = 8 µs (59 ns) would need 4.54 ns (220 MHz). (b) remains out of reach.
- **The datapath is no longer the limit.** The worst paths are plain wires with 0–2 logic levels and 96–98% routing: hard-decision bits from the VNUs to the register file conv_check reads; CNU stage-1 → merge registers; one control copy to many M(t−1) registers.
  - In every run, placement ends with +0.13 to +0.42 ns of slack and routing takes 0.3–0.5 ns of it back.
  - Further gains would come from floorplanning or an extra register on those long nets (an RTL change, not tried).
- **The directive matters about as much as the target.** At 4.76 ns, Explore closes; ExtraNetDelay_high misses by 14 ps, WLDrivenBlockPlacement by 107 ps, and ExtraTimingOpt by 294 ps. Each variant's confirmed clock spans 197.6–210.1 MHz.
- **Post-route phys_opt** gained 0.02–0.05 ns where it had something to do (B, C, D at 4.76; D at 4.87 from −0.023 to 0.000) and nothing in A.

## Not tested
- **Placement seeds:** not available in place_design; directive variants instead. One run per (variant, period), so the run-to-run spread at a fixed directive is unknown. Margins are 0–21 ps at the closing periods.
- **Other options:** phys_opt or route directive variants, -tns_cleanup, incremental implementation, Pblocks / floorplanning, and retiming were not run.
- **Below 4.76 ns:** not tried (A's own next step would be about 4.70 ns).
- **Functional check of the implemented netlist:** no post-route simulation. The RTL is unchanged and verified as above.
