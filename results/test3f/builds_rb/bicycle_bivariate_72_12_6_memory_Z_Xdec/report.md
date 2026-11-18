# sortq build: circuit=bicycle_bivariate_72_12_6_memory_Z,distance=6,rounds=6,error_rate=0.003,noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim — X decoder

## Flow

- 1 decoder matrix, symmetry (nauty), templates, exact reconstruction (test1c_engine_params.py): ok
- 2 round wiring + package (gen_round_wiring.py): ok
- 3 boundary type sets + observable ROM (gen_tables.py): ok
- 4 resource estimate (Test 2d block model): ok
- 5 red-black package: order, gating tables, dependency distance (gen_rb_pkg.py): ok

## Decoder matrix and symmetry
- matrix 252 x 2,232, nnz 7,776, 7 detector rounds (check type Z)
- group (nauty, rows coloured by round): order 36, abelian, Z6 x Z6, free and transitive on the 36 checks of every round
- reconstruction from the templates: **exact** (2,232 columns, nnz 7,776)
- bulk reference round 2; rounds with the bulk type set: [1, 2, 3, 4, 5]
- error types per home round: {0: 9, 1: 10, 2: 10, 3: 10, 4: 10, 5: 10, 6: 3}; distinct error types 10, bulk types 10
- boundary types: class a 62, class b (embedded in a bulk type, masked) 0, class c (own edges) 0; slot conflicts 0
- base edges (bulk check degree) 35: offset 0: 22, offset 1: 13
- max check degree 35; check degree histogram {16: 36, 25: 36, 35: 180}
- error degrees (max 6): {2: 216, 3: 1368, 4: 216, 5: 216, 6: 216}; bulk type weights [2, 3, 3, 3, 3, 3, 3, 4, 5, 6]
- distinct shifts: bulk table 14, whole matrix 14
- two-round error types (updated again in layer home + 1): 7 -> VNU updates per round step 612 (10 + 7 types x 36); CNUs per step 36

## Generated
- engine_params.json, round_wiring_pkg.sv, round_wiring.sv (round_wiring.sv: 1260 edges per check round (x2 directions), NE0 = 22, NE1 = 13; round_wiring_pkg.sv written to ../results/test3f/builds_rb/bicycle_bivariate_72_12_6_memory_Z_Xdec)
- engine_tables_pkg.sv (engine_tables_pkg.sv: NOBS 12, TP_FIRST 0111111111, TP_LAST 1000001010, OBS_ROM 10 x 36 (home-round independent: asserted on 2232 columns))

## Resource estimate (from the Test 2c / 2d measured blocks; estimate, not synthesized)
- window W = 6 rounds (assumption: W = d), VNU_PASSES 1, LUTRAM state memory
- calibration factor 0.9715 (model / measured on the gross X engine, applied to every code)
- SORTQ k = 1 engine: **200,936 LUT (4.9%)**, LUTRAM 4,774
  - round_step 149,539 (CNU 23,466, VNU cur 75,199, VNU prev 50,557)
  - shared: memories 18,830, gamma_lanes 24,811, conv_check 4,866, commit 1,838, ctrl 891, glue 160
  - state bits per slot 16,704 ({'v2c_o0': 3960, 'c2v_o1': 2340, 'marg': 8568, 'g8': 1836}), x W = 100,224
- fully parallel decoder from our blocks: **689,400 LUT (16.9%)** standalone (CNU 178,344 + VNU 511,056); with in-context factors 625,312; one gamma lane per error would add 158,351
- ratio fully parallel / SORTQ engine: 3.43
- degrees outside the measured range (linear extrapolation): {'cnu_degrees_outside_measured': [], 'vnu_degrees_outside_measured': []}

## Red-black engine package (--order rb)
- rb_pkg.sv, rb_pkg_report.json (hw/rb/gen/gen_rb_pkg.py); order 0, 2, 4, 6, 1, 3, 5
- leg-start gating: CNU inputs gated per pass [35, 12] of 35 base edges; VNU tables per pass and group {'pass0_cur': 13, 'pass0_prev': 10, 'pass1_cur': 0, 'pass1_prev': 0}
- minimum dependency distance 3 slots (required >= 5: v2c read -> write 4 cycles): **NOT met**; stall cycles per iteration **4** -> 11 cycles per iteration (issue cycles [0, 1, 2, 3, 6, 7, 8]; the RTL has no stall logic, a modified ctrl_rb is needed)
- consecutive steps sharing an error: none

