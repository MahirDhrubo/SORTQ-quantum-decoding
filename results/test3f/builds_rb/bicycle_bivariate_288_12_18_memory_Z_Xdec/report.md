# sortq build: circuit=bicycle_bivariate_288_12_18_memory_Z,distance=18,rounds=18,error_rate=0.003,noise_model=uniform_circuit,basis=CX,A=x^3+y^2+y^7,B=y^3+x+x^2.stim — X decoder

## Flow

- 1 decoder matrix, symmetry (nauty), templates, exact reconstruction (test1c_engine_params.py): ok
- 2 round wiring + package (gen_round_wiring.py): ok
- 3 boundary type sets + observable ROM (gen_tables.py): ok
- 4 resource estimate (Test 2d block model): ok
- 5 red-black package: order, gating tables, dependency distance (gen_rb_pkg.py): ok

## Decoder matrix and symmetry
- matrix 2,736 x 26,208, nnz 91,584, 19 detector rounds (check type Z)
- group (nauty, rows coloured by round): order 144, abelian, Z12 x Z12, free and transitive on the 144 checks of every round
- reconstruction from the templates: **exact** (26,208 columns, nnz 91,584)
- bulk reference round 8; rounds with the bulk type set: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17]
- error types per home round: {0: 9, 1: 10, 2: 10, 3: 10, 4: 10, 5: 10, 6: 10, 7: 10, 8: 10, 9: 10, 10: 10, 11: 10, 12: 10, 13: 10, 14: 10, 15: 10, 16: 10, 17: 10, 18: 3}; distinct error types 10, bulk types 10
- boundary types: class a 182, class b (embedded in a bulk type, masked) 0, class c (own edges) 0; slot conflicts 0
- base edges (bulk check degree) 35: offset 0: 22, offset 1: 13
- max check degree 35; check degree histogram {16: 144, 25: 144, 35: 2448}
- error degrees (max 6): {2: 2592, 3: 15840, 4: 2592, 5: 2592, 6: 2592}; bulk type weights [2, 3, 3, 3, 3, 3, 3, 4, 5, 6]
- distinct shifts: bulk table 17, whole matrix 17
- two-round error types (updated again in layer home + 1): 7 -> VNU updates per round step 2,448 (10 + 7 types x 144); CNUs per step 144

## Generated
- engine_params.json, round_wiring_pkg.sv, round_wiring.sv (round_wiring.sv: 5040 edges per check round (x2 directions), NE0 = 22, NE1 = 13; round_wiring_pkg.sv written to ../results/test3f/builds_rb/bicycle_bivariate_288_12_18_memory_Z_Xdec)
- engine_tables_pkg.sv (engine_tables_pkg.sv: NOBS 12, TP_FIRST 0111111111, TP_LAST 1000001010, OBS_ROM 10 x 144 (home-round independent: asserted on 26208 columns))

## Resource estimate (from the Test 2c / 2d measured blocks; estimate, not synthesized)
- window W = 18 rounds (assumption: W = d), VNU_PASSES 1, LUTRAM state memory
- calibration factor 0.9715 (model / measured on the gross X engine, applied to every code)
- SORTQ k = 1 engine: **990,160 LUT (24.2%)**, LUTRAM 57,288
  - round_step 598,157 (CNU 93,866, VNU cur 300,795, VNU prev 202,230)
  - shared: memories 225,962, gamma_lanes 99,245, conv_check 58,395, commit 7,350, ctrl 891, glue 160
  - state bits per slot 66,816 ({'v2c_o0': 15840, 'c2v_o1': 9360, 'marg': 34272, 'g8': 7344}), x W = 1,202,688
- fully parallel decoder from our blocks: **8,133,408 LUT (199.1%)** standalone (CNU 2,113,056 + VNU 6,020,352); with in-context factors 7,376,356; one gamma lane per error would add 1,859,348
- ratio fully parallel / SORTQ engine: 8.21
- degrees outside the measured range (linear extrapolation): {'cnu_degrees_outside_measured': [], 'vnu_degrees_outside_measured': []}

## Red-black engine package (--order rb)
- rb_pkg.sv, rb_pkg_report.json (hw/rb/gen/gen_rb_pkg.py); order 0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 1, 3, 5, 7, 9, 11, 13, 15, 17
- leg-start gating: CNU inputs gated per pass [35, 12] of 35 base edges; VNU tables per pass and group {'pass0_cur': 13, 'pass0_prev': 10, 'pass1_cur': 0, 'pass1_prev': 0}
- minimum dependency distance 9 slots (required >= 5: v2c read -> write 4 cycles): **met**; stall cycles per iteration **0** -> 19 cycles per iteration
- consecutive steps sharing an error: none

