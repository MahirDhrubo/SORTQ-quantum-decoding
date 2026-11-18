# Test 1c: engine parameters and boundary embedding (2026-11-12)

## Setup
- Circuit: IBM gross-code memory circuit from the Relay-BP data set (`bb_ibm`, d = 12, 12 rounds, p = 0.001,
  uniform_circuit). Matrix: X-decoder projection "xdec" (Z detectors only, empty columns dropped, identical columns
  merged), 936 × 8,784, 30,672 nonzeros, 13 rounds × 72 checks. H only (level L1, no priors).
- Labels from the circuit, as in Test 1: check = ancilla qubit; round = occurrence of that ancilla's measurement
  (+1 for detectors that use the final data measurement).
- Group action: nauty on the Tanner graph, rows coloured by round (Test 1 "type+round" mode). Asserted by the script:
  order 72, abelian, every element keeps rounds, induces the **same ancilla permutation in every round**, acts
  consistently on columns, and is free on ancillas.
- **Convention (coordinates and shifts):**
  - anc0 = ancilla 216 (smallest id). g1 = order-12 element whose image of anc0 has the smallest id (→ 222);
    g2 = order-6 element with ⟨g1⟩ ∩ ⟨g2⟩ = {e}, smallest image of anc0 (→ 217). The ancilla g1^a g2^b (anc0) has
    coordinate x = (a, b) ∈ Z12 × Z6 (full map in the JSON). Verified: g(u) maps coordinate x to x + u in every round.
  - Error column: home round h = round of its earliest detector; position t ∈ Z12 × Z6. Each edge to check (x, r)
    has round offset o = r − h and shift s = t − x. The column's type is its set {(o, s)}; t is chosen so this set is
    lexicographically smallest (unique, because the action is free).
  - So every edge (check (x, r), error) is the image under g = x of the base edge (check (0, r), error type at
    position s). In hardware terms: the rotator for a base edge reads the error node at x + s.
- Script: `scripts/test1c_engine_params.py`; results `engine_params.json`, log `run.log` (2.6 s on the server).
  All numbers are measured from the matrix.

## Results

### Sanity check
**Reconstruction: exact.** H rebuilt from the 10-type template, the group action (72 positions), the round shifts and
the per-round type lists has the same 8,784 columns and 30,672 nonzeros as xdec (0 mismatches).

### 1. Base-edge table (bulk round 5): 35 base edges, 1 check type, 10 error types
| Error type | Weight | Edges to the round-5 check: (offset; shift a, b) |
|---|---|---|
| T00 | 2 | (0; 0,0), (1; 0,0) |
| T01 | 3 | (0; 0,0), (0; 0,1), (0; 9,2) |
| T02 | 3 | (0; 0,0), (0; 0,1), (1; 9,2) |
| T03 | 3 | (0; 0,0), (0; 1,0), (0; 2,3) |
| T04 | 3 | (0; 0,0), (0; 1,0), (1; 2,3) |
| T05 | 3 | (0; 0,0), (1; 0,5), (1; 9,1) |
| T06 | 3 | (0; 0,0), (1; 1,0), (1; 2,3) |
| T07 | 4 | (0; 0,0), (0; 2,3), (1; 1,5), (1; 10,1) |
| T08 | 5 | (0; 0,0), (1; 1,5), (1; 2,2), (1; 10,1), (1; 11,4) |
| T09 | 6 | (0; 0,0), (0; 1,0), (0; 2,3), (0; 3,4), (0; 4,4), (0; 5,1) |

(Each type's edges to one check are exactly its column edges, so this table is also the type definition.)
**Every round 1–11 gives the identical table**: all 72 checks of each round share their round's table, and the
tables of rounds 1–11 are equal to round 5. Rounds 0 and 12 differ (see 2 and 5).

### 2. Check degree
| Rounds | Checks | Degree | Offset 0 | Offset 1 |
|---|---|---|---|---|
| 0 | 72 | 16 | 16 | 0 |
| 1–11 | 792 | 35 | 22 | 13 |
| 12 | 72 | 25 | 12 | 13 |

Max degree 35. Distribution over all 936 checks: {16: 72, 25: 72, 35: 792}.

### 3. Error degree
| Weight | Types | Round offsets touched |
|---|---|---|
| 2 | T00 | {0, 1} |
| 3 | T01, T03 | {0} |
| 3 | T02, T04, T05, T06 | {0, 1} |
| 4 | T07 | {0, 1} |
| 5 | T08 | {0, 1} |
| 6 | T09 | {0} |

Max column weight 6; no type spans more than two consecutive rounds (offsets 0 and 1 only).

### 4. Rotator settings
**14 distinct shifts**, both in the bulk table and in the whole matrix:
(0,0), (0,1), (0,5), (1,0), (1,5), (2,2), (2,3), (3,4), (4,4), (5,1), (9,1), (9,2), (10,1), (11,4).
(0,0) is the identity, so 13 non-trivial rotations.

### 5. Boundary embedding (against the round-5 template, shifted in time)
| Home round | Types present | (a) identical | (b) subset (maskable) | (c) new | Template slots unused |
|---|---|---|---|---|---|
| 0 | 9 | 9 | 0 | 0 | T09 |
| 1–10 | 10 | 10 | 0 | 0 | none |
| 11 | 10 | 10 | 0 | 0 | none |
| 12 | 3 (T01, T03, T09) | 3 | 0 | 0 | T00, T02, T04–T08 |

**No class (b) or (c) types**: there are no truncated or new error types at the boundaries. The whole matrix uses
only the 10 bulk types. The boundaries differ only in which **whole types are absent** (all 72 copies):
- round 0: T09 absent;
- round 12: only the three offset-0-only types exist (T01, T03, T09).

This also explains Test 1's "round 11 → 12: 216 of 720 map": round 11 is a normal bulk round; round 12 simply has
only 3 of the 10 types. Rounds 0 and 12 have fewer edges per check (16 and 25) for the same reason.

### 6. Memory (marginal = message + 3 bits; 36Kb BRAM = 36,864 bits, no packing)
The prior width is not specified in the task, so both options are shown.

Per bulk round (10 types, 35 edges per check → 2,520 edges):
| Message bits | Error state, prior = w | Error state, prior = w + 3 | Messages |
|---|---|---|---|
| 4 | 72 × 10 × (4 + 7 + 7) = 12,960 b (1 BRAM) | 15,120 b (1 BRAM) | 2,520 × 4 = 10,080 b (1 BRAM) |
| 6 | 72 × 10 × (6 + 9 + 9) = 17,280 b (1 BRAM) | 19,440 b (1 BRAM) | 2,520 × 6 = 15,120 b (1 BRAM) |

All 13 rounds (measured per-round types and edges; rounds 0 and 12 smaller):
| Message bits | Error state, prior = w | Error state, prior = w + 3 | Messages | Total BRAM (prior = w / w + 3) |
|---|---|---|---|---|
| 4 | 158,112 b (5 BRAM) | 184,464 b (6 BRAM) | 122,688 b (4 BRAM) | 9 / 10 |
| 6 | 210,816 b (6 BRAM) | 237,168 b (7 BRAM) | 184,032 b (5 BRAM) | 11 / 12 |

Per round, rounds 0 / 1–11 / 12 at w = 4, prior = w: error state 11,664 / 12,960 / 3,888 b; messages 4,608 /
10,080 / 7,200 b; each fits in 1 BRAM. If the engine reserves the full template in every round (unused types masked),
the totals become 13 × the bulk round: 168,480 + 131,040 b at w = 4 (prior = w).

These are raw bit counts. Real BRAM use depends on port width and on how many words the engine reads per cycle,
which this test does not model (Test 3).

## What this means for Idea 1
1. **The template is complete.** One check type, 10 error types and 35 base edges describe the whole X-decoder matrix.
   Every edge is a base edge rotated by the check's coordinate. Reconstruction is exact.
2. **Boundaries are only masking of whole types.** No truncated or new types, so the engine needs no special boundary
   datapath: round 0 switches off T09; round 12 keeps only T01, T03, T09. Rounds 1–11 are identical, one more than Test
   1's "bulk" (1–10), which was cut short by round 12 rather than by round 11.
3. **Only two consecutive rounds interact** (offsets 0 and 1). A round engine needs at most the current and the previous
   round of error state at once.
4. **Rotators:** 14 fixed shift settings (13 non-trivial) cover every edge. Each base edge has one fixed shift, so
   each rotator can be hardwired rather than programmable.
5. **Memory is small:** the whole 13-round state is 9–12 BRAM36 (raw bits) for 4–6-bit messages, about 1 BRAM per round
   for error state plus 1 for messages.

## Not tested
- Priors (L2). Test 1 found priors are time-symmetric only in rounds 1–9, so in rounds 0, 10 and 11 some types have
  different prior values even though H is identical. The engine would need per-round prior values (or a per-round
  prior table); not quantified here.
- The full correlated DEM (X + Z, 82 error types per round) and other circuits or noise models.
- BRAM port widths, banking and parallelism, clock and latency: Test 3.
- Other conventions. Changing the generators (an automorphism of Z12 × Z6) relabels the shifts but keeps their count.
  Moving one type's representative by u adds u to all of that type's shifts, so the count can change. 14 is for the
  lexicographic representatives; the choice that minimises the number of distinct shifts was not searched.
