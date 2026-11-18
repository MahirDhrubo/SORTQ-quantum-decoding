# ARITHMETIC.md — golden integer arithmetic of the Test 1b decoder (int4.2.8, round sweep)

Source of truth: `relay_bp/crates/relay_bp/src/bp/min_sum.rs` and `relay.rs` (relay-bp at cdfdc99 plus the
SORTQ changes: `check_layers`, `quant`, and the Test 2a dump). Everything below was read from that code and
**checked record by record** against the golden dumps (Step 0 below: 0 mismatches).
Integers are held in f32 inside the decoder; every value is an exact integer, so f32 = integer arithmetic.

## 1. Format intN.S.M (int4.2.8: N = 4, S = 2, M = 8)
| Quantity | Range | Bits | Rule |
|---|---|---|---|
| message (v2c, c2v) | ±(2^N − 1) = ±15 | sign + N | saturate (clip) |
| prior L0 | ±15 | sign + N | L0 = sat_msg(round(S · ln((1 − p)/p))) |
| g8 (memory strength) | {−2, …, 5} used | 4-bit signed in RTL | g8 = round(M · γ) |
| bias Λ | [−2^(N+2), 2^(N+2) − 1] = [−64, 63] | N + 3, two's complement | saturate |
| marginal (posterior) | [−64, 63] | N + 3, two's complement | saturate |

- round(x) = floor(x + 1/2) (half up). For an integer numerator, round(num / 8) = (num + 4) >> 3 (arithmetic).
- Saturation is applied to each computed value, once, right after it is computed (rules below).
- Priors here are all positive (p < 1/2), so L0 ∈ [0, 15].

## 2. Check node (one check `c`, degree d, syndrome bit s_c)
Inputs: the d v2c messages q_e currently stored for the check's edges.
```
parity  = s_c XOR (XOR over e of neg(q_e))          neg(q) = (q < 0); a v2c is never "−0" (measured: 0 cases)
min1    = min_e |q_e| ;  min2 = second smallest |q_e| (= min1 if the minimum is repeated; = MAX if d = 1)
out_e   = (|q_e| == min1 ? min2 : min1), then sat to 15      (alpha = 1: no scaling)
sign_e  = parity XOR neg(q_e)
c2v_e   = sign_e ? −out_e : +out_e
```
- Every edge whose magnitude equals min1 gets min2. If min1 is repeated, min2 = min1, so this is identical to
  "the min1 index gets min2, all others get min1": an index-based CNU is bit-exact.
- **Sign of zero:** the sign is applied even when out_e = 0, so a c2v can be −0 (sign 1, magnitude 0).
  Measured: 35,622 such outputs in the dumps. In sums −0 = 0, so only the sign-magnitude output bit is affected;
  the RTL produces the same sign bit and the testbench compares sign and magnitude.
- The saturation of out_e never acts (inputs are already ≤ 15); measured: c2v magnitudes 0..15.

## 3. Error (variable) node (one error `v`, degree d ≤ 6)
Inputs: L0_v, g8_v (of the current leg), M_v(t−1) = marginal at the end of the previous iteration (memory), the d
c2v messages r_e currently stored for its edges.
```
bias   Λ_v = sat_marg( round( ((8 − g8) · L0 + g8 · M_v(t−1)) / 8 ) )
total      = Λ_v + Σ_e r_e                                (exact, |total| ≤ 64 + 6·15 = 154: 9 bits)
marginal   = sat_marg(total)                              → stored as M_v (memory of the next iteration)
v2c_e      = sat_msg(total − r_e)                         (exact extrinsic sum, then saturated)
hard_v     = (marginal ≤ 0)                               (≤: a zero marginal decides "error")
```
- v2c_e is computed from the **unsaturated** total, not from the saturated marginal.
- Measured ranges in the dumps: bias −37..45 (never clipped), marginal −64..63 (clips at both ends),
  v2c −15..15.

## 4. One iteration = one round sweep (layered schedule)
Layers = detector rounds 0, 1, …, R (13 layers for the 12-round circuit), in this order. At the start of the
iteration the memory is latched: M(t−1) ← current marginals. Then for each layer r:
1. **Check update:** every check of round r computes its c2v from the stored v2c (section 2) and writes them.
2. **Error update:** every error with at least one edge into round r is updated (section 3), in increasing column
   order (the order does not matter: no error reads another error's new value). It reads the stored c2v of all its
   edges (round r just written; the other round as stored) and writes its v2c for **all** its edges, its marginal
   and hard decision.
   - Errors have edges in their home round h (offset 0) and possibly h + 1 (offset 1). Layer r therefore updates
     the errors of home r (720 in the bulk: 10 types × 72) **and** the errors of home r − 1 that have an offset-1
     edge (7 two-round types T00, T02, T04–T08: 504). These 7 types are updated twice per iteration
     (in layers h and h + 1); the second update overwrites the first.
After the last layer: hard decisions from the marginals; **converged** ⇔ H · hard = syndrome over all detectors.

## 5. Relay legs and the leg hand-off
- Leg 0 (pre_iter = 80 iterations): marginals ← L0, g8 = round(8 · 0.125) = 1 for every error, v2c ← L0, c2v ← 0.
- Leg k ≥ 1 (up to 60 iterations, 300 legs): new g8 per error = round(8 · γ), γ ~ Uniform(−0.226, 0.622);
  **v2c ← L0, c2v ← 0, marginals kept** (the memory M(t−1) of the first iteration is the last marginal of the
  previous leg).
- Stop at the first converged iteration (stop_nconv S = 1), else after the cap 80 + 300 · 60 = 18,080 iterations.
- The γ generator is re-seeded (seed 0) at the start of every decode, so **every shot uses the same g8 vector per
  leg** (measured: leg-1 g8 identical in all 3 dumped shots).

### Leg start in hardware (chosen design: init-flag gating, memories not cleared)
In the first iteration of a leg (init = 1) the stored messages from the previous leg must be ignored:
- CNU of round r: for edges to errors of home r (offset 0) the input is L0 instead of the stored v2c
  (those errors have not been updated yet in this iteration). Offset-1 edges are already fresh.
- VNU: for an error of home h updated in layer h, edges to round h + 1 use c2v = 0 instead of the stored value.
  In layer h + 1 (second update) all its c2v are fresh.
Checked against the golden decoder (rule D in `golden/check_and_vectors.py`): 116,640 gated CNU inputs and 67,392
gated VNU inputs, 0 mismatches; in 116,617 and 33,582 of them the stored value was different, so the gating is
really exercised.

## 6. γ grid (g8 values)
g8 = floor(8γ + 1/2) with γ ~ U(−0.22628, 0.62160):

| g8 | −2 | −1 | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|---|---|
| probability (computed) | 4.574% | 14.743% | 14.743% | 14.743% | 14.743% | 14.743% | 14.743% | 6.971% |
| leg-1 count in the dumps (8,784 errors) | 408 | 1,284 | 1,318 | 1,242 | 1,257 | 1,320 | 1,382 | 573 |

Set used: **{−2, −1, 0, 1, 2, 3, 4, 5}** (leg 0: only g8 = 1). 8 − g8 ∈ [3, 10].

## 7. Golden dumps (Step 0)
- Option added: environment variable `RELAY_DUMP=<file>` (and `RELAY_DUMP_LEGS`, default 2) read when the decoder is
  built; write-only hooks (record format in `min_sum.rs`, `DumpState`). Python bindings unchanged.
- Shots: 2,000 syndromes of the 12-round p = 0.003 circuit (stim seed 20261113); picked the first 2 shots that
  converge in leg 2 (iterations 97 and 126) and the first that needs more than 2 legs (580 iterations;
  dumped: legs 1–2 = 140 iterations). Files `golden/dump_p0.003_shot{0,1,2}.bin` (95–137 MB).
- "Dump on gives identical results": dump on vs dump off (new build) vs the pre-change build (`the relay_bp environment`):
  identical iterations, success, decoding and saturation counters on the 3 shots; and the new build (dump off) vs
  the pre-change build on all 2,000 shots for int4.2.8 sweep, int4.2.8 flood and float sweep: identical.
  The 18 Rust unit tests pass.
- Independent check of this document against the dumps (numpy model, `golden/check_and_vectors.py`):
  339,768 check updates (11,133,936 edges) and 5,384,016 error updates, **0 mismatches**; ordering, memory,
  g8, priors, hard decisions and convergence flags (363 iterations) also 0 mismatches.
