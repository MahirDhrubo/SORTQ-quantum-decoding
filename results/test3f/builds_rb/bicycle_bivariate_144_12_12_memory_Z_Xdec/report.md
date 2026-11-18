# sortq build: circuit=bicycle_bivariate_144_12_12_memory_Z,distance=12,rounds=12,error_rate=0.003,noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim — X decoder

## Flow

- 1 decoder matrix, symmetry (nauty), templates, exact reconstruction (test1c_engine_params.py): ok
- 2 round wiring + package (gen_round_wiring.py): ok
- 3 boundary type sets + observable ROM (gen_tables.py): ok
- 4 resource estimate (Test 2d block model): ok
- 5 red-black package: order, gating tables, dependency distance (gen_rb_pkg.py): ok

## Decoder matrix and symmetry
- matrix 936 x 8,784, nnz 30,672, 13 detector rounds (check type Z)
- group (nauty, rows coloured by round): order 72, abelian, Z12 x Z6, free and transitive on the 72 checks of every round
- reconstruction from the templates: **exact** (8,784 columns, nnz 30,672)
- bulk reference round 5; rounds with the bulk type set: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11]
- error types per home round: {0: 9, 1: 10, 2: 10, 3: 10, 4: 10, 5: 10, 6: 10, 7: 10, 8: 10, 9: 10, 10: 10, 11: 10, 12: 3}; distinct error types 10, bulk types 10
- boundary types: class a 122, class b (embedded in a bulk type, masked) 0, class c (own edges) 0; slot conflicts 0
- base edges (bulk check degree) 35: offset 0: 22, offset 1: 13
- max check degree 35; check degree histogram {16: 72, 25: 72, 35: 792}
- error degrees (max 6): {2: 864, 3: 5328, 4: 864, 5: 864, 6: 864}; bulk type weights [2, 3, 3, 3, 3, 3, 3, 4, 5, 6]
- distinct shifts: bulk table 14, whole matrix 14
- two-round error types (updated again in layer home + 1): 7 -> VNU updates per round step 1,224 (10 + 7 types x 72); CNUs per step 72

## Generated
- engine_params.json, round_wiring_pkg.sv, round_wiring.sv (round_wiring.sv: 2520 edges per check round (x2 directions), NE0 = 22, NE1 = 13; round_wiring_pkg.sv written to ../results/test3f/builds_rb/bicycle_bivariate_144_12_12_memory_Z_Xdec)
- engine_tables_pkg.sv (engine_tables_pkg.sv: NOBS 12, TP_FIRST 0111111111, TP_LAST 1000001010, OBS_ROM 10 x 72 (home-round independent: asserted on 8784 columns))

## Resource estimate (from the Test 2c / 2d measured blocks; estimate, not synthesized)
- window W = 12 rounds (assumption: W = d), VNU_PASSES 1, LUTRAM state memory
- calibration factor 0.9715 (model / measured on the gross X engine, applied to every code)
- SORTQ k = 1 engine: **448,213 LUT (11.0%)**, LUTRAM 19,096
  - round_step 299,079 (CNU 46,933, VNU cur 150,398, VNU prev 101,115)
  - shared: memories 75,321, gamma_lanes 49,623, conv_check 19,465, commit 3,675, ctrl 891, glue 160
  - state bits per slot 33,408 ({'v2c_o0': 7920, 'c2v_o1': 4680, 'marg': 17136, 'g8': 3672}), x W = 400,896
- fully parallel decoder from our blocks: **2,722,752 LUT (66.6%)** standalone (CNU 706,608 + VNU 2,016,144); with in-context factors 2,469,401; one gamma lane per error would add 623,188
- ratio fully parallel / SORTQ engine: 6.07
- degrees outside the measured range (linear extrapolation): {'cnu_degrees_outside_measured': [], 'vnu_degrees_outside_measured': []}

## Red-black engine package (--order rb)
- rb_pkg.sv, rb_pkg_report.json (hw/rb/gen/gen_rb_pkg.py); order 0, 2, 4, 6, 8, 10, 12, 1, 3, 5, 7, 9, 11
- leg-start gating: CNU inputs gated per pass [35, 12] of 35 base edges; VNU tables per pass and group {'pass0_cur': 13, 'pass0_prev': 10, 'pass1_cur': 0, 'pass1_prev': 0}
- minimum dependency distance 6 slots (required >= 5: v2c read -> write 4 cycles): **met**; stall cycles per iteration **0** -> 13 cycles per iteration
- consecutive steps sharing an error: none

