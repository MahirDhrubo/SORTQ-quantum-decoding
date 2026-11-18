# Test 1b: quantization (integer Relay-BP), round sweep and flooding

_Generated automatically by `day1_summaries.py 1b` from `report.json` (queue step 1); review before use._

## Setup
- Decoder: `relay_bp.RelayDecoderF32` with the added `quant` option (round + saturate after every computed value;
  small integers are exact in f32) and `check_layers` (sweep = 13 layers, flood = none).
- Parameters (Test 2b): S = 1, γ0 = 0.125, α = None (α = 1), γ interval (−0.226, 0.622), pre_iter 80,
  300 legs × 60, cap 18,080. Sampler seed 20261111; all formats and schedules decode the same shots.
- Formats: float (f32); int4.2.8 (messages ±15, priors round(2·LLR), 7-bit marginals, γ on 1/8);
  int6.4.8 (±63, ×4, 9-bit marginals, γ on 1/8). Rounding: floor(x + 1/2). α = 1, so no message scaling.
- Bit-exactness: quant = none is bit-identical to the unmodified build (F32 and F64, flood and sweep, 300 shots);
  flooding = 1 layer bit-identical for float and int4 (300 shots). See `bitexact_compare.log`, `sanity.json`.
- 'wide' format vs float (1,000 shots): different decodings on 393 (sweep) / 322 (flood) shots; integer arithmetic shown exact without rounding (`exactness.log`); differences come from rounding
  amplified by BP, logical outcome equal on all 1,000 shots.

## Results
### p0.003 (168,000 shots)

| Format | Schedule | Fails | LER | Hit cap |
|---|---|---|---|---|
| float | sweep | 124 | 0.000738 | 6 |
| float | flood | 111 | 0.000661 | 17 |
| int4.2.8 | sweep | 128 | 0.000762 | 9 |
| int4.2.8 | flood | 106 | 0.000631 | 18 |
| int6.4.8 | sweep | 130 | 0.000774 | 10 |
| int6.4.8 | flood | 117 | 0.000696 | 16 |

Paired vs float (same schedule): both / only float / only int, McNemar p

| Format | Schedule | Both | Only float | Only int | McNemar p |
|---|---|---|---|---|---|
| int4.2.8 | sweep | 54 | 70 | 74 | 0.803 |
| int4.2.8 | flood | 61 | 50 | 45 | 0.682 |
| int6.4.8 | sweep | 59 | 65 | 71 | 0.668 |
| int6.4.8 | flood | 59 | 52 | 58 | 0.634 |

| Format | Schedule | Mean it. | p50 | p90 | p99 | p99.9 | % > 80 | % > 1,000 |
|---|---|---|---|---|---|---|---|---|
| float | sweep | 24.2 | 11 | 27 | 224 | 1.6e+03 | 2.57 | 0.169 |
| float | flood | 32.8 | 15 | 34 | 297 | 2.02e+03 | 4 | 0.241 |
| int4.2.8 | sweep | 23.5 | 11 | 27 | 217 | 1.26e+03 | 2.53 | 0.148 |
| int4.2.8 | flood | 32.5 | 15 | 34 | 296 | 1.98e+03 | 4 | 0.228 |
| int6.4.8 | sweep | 23.6 | 11 | 27 | 213 | 1.36e+03 | 2.54 | 0.151 |
| int6.4.8 | flood | 31.7 | 15 | 34 | 279 | 1.87e+03 | 3.95 | 0.213 |

Saturation (fraction of updates clipped, exact value outside the range):

| Format | Schedule | c2v | v2c | marginal | bias |
|---|---|---|---|---|---|
| int4.2.8 | sweep | 0 | 0.969 | 0.452 | 0 |
| int4.2.8 | flood | 0 | 0.974 | 0.447 | 0 |
| int6.4.8 | sweep | 0 | 0.869 | 0.253 | 0 |
| int6.4.8 | flood | 0 | 0.881 | 0.259 | 0 |

### p0.002 (600,000 shots)

| Format | Schedule | Fails | LER | Hit cap |
|---|---|---|---|---|
| float | sweep | 25 | 4.17e-05 | 4 |
| float | flood | 26 | 4.33e-05 | 5 |
| int4.2.8 | sweep | 19 | 3.17e-05 | 3 |
| int4.2.8 | flood | 29 | 4.83e-05 | 8 |
| int6.4.8 | sweep | 26 | 4.33e-05 | 5 |
| int6.4.8 | flood | 24 | 4e-05 | 5 |

Paired vs float (same schedule): both / only float / only int, McNemar p

| Format | Schedule | Both | Only float | Only int | McNemar p |
|---|---|---|---|---|---|
| int4.2.8 | sweep | 9 | 16 | 10 | 0.327 |
| int4.2.8 | flood | 15 | 11 | 14 | 0.69 |
| int6.4.8 | sweep | 14 | 11 | 12 | 1 |
| int6.4.8 | flood | 15 | 11 | 9 | 0.824 |

| Format | Schedule | Mean it. | p50 | p90 | p99 | p99.9 | % > 80 | % > 1,000 |
|---|---|---|---|---|---|---|---|---|
| float | sweep | 10.1 | 7 | 16 | 38 | 212 | 0.357 | 0.0115 |
| float | flood | 13.1 | 10 | 20 | 52 | 276 | 0.634 | 0.0162 |
| int4.2.8 | sweep | 10.3 | 8 | 17 | 39 | 216 | 0.37 | 0.0118 |
| int4.2.8 | flood | 13.4 | 10 | 20 | 55 | 280 | 0.693 | 0.0157 |
| int6.4.8 | sweep | 10.1 | 7 | 16 | 38 | 181 | 0.362 | 0.0105 |
| int6.4.8 | flood | 13.3 | 10 | 20 | 53 | 245 | 0.639 | 0.0138 |

Saturation (fraction of updates clipped, exact value outside the range):

| Format | Schedule | c2v | v2c | marginal | bias |
|---|---|---|---|---|---|
| int4.2.8 | sweep | 0 | 0.971 | 0.426 | 0 |
| int4.2.8 | flood | 0 | 0.98 | 0.428 | 0 |
| int6.4.8 | sweep | 0 | 0.859 | 0.184 | 0 |
| int6.4.8 | flood | 0 | 0.905 | 0.195 | 0 |

### p0.001 (600,000 shots)

| Format | Schedule | Fails | LER | Hit cap |
|---|---|---|---|---|
| float | sweep | 2 | 3.33e-06 | 0 |
| float | flood | 1 | 1.67e-06 | 0 |
| int4.2.8 | sweep | 2 | 3.33e-06 | 0 |
| int4.2.8 | flood | 1 | 1.67e-06 | 0 |
| int6.4.8 | sweep | 1 | 1.67e-06 | 0 |
| int6.4.8 | flood | 1 | 1.67e-06 | 0 |

Paired vs float (same schedule): both / only float / only int, McNemar p

| Format | Schedule | Both | Only float | Only int | McNemar p |
|---|---|---|---|---|---|
| int4.2.8 | sweep | 2 | 0 | 0 | 1 |
| int4.2.8 | flood | 0 | 1 | 1 | 1 |
| int6.4.8 | sweep | 1 | 1 | 0 | 1 |
| int6.4.8 | flood | 1 | 0 | 0 | 1 |

| Format | Schedule | Mean it. | p50 | p90 | p99 | p99.9 | % > 80 | % > 1,000 |
|---|---|---|---|---|---|---|---|---|
| float | sweep | 5.34 | 4 | 10 | 20 | 40 | 0.0268 | 0.0005 |
| float | flood | 6.9 | 6 | 13 | 24 | 45 | 0.0373 | 0.0005 |
| int4.2.8 | sweep | 5.52 | 4 | 10 | 21 | 41 | 0.0313 | 0.0005 |
| int4.2.8 | flood | 6.67 | 5 | 12 | 24 | 54 | 0.0655 | 0.001 |
| int6.4.8 | sweep | 5.32 | 4 | 10 | 20 | 39 | 0.0242 | 0.000333 |
| int6.4.8 | flood | 6.61 | 5 | 12 | 24 | 44 | 0.0358 | 0.000333 |

Saturation (fraction of updates clipped, exact value outside the range):

| Format | Schedule | c2v | v2c | marginal | bias |
|---|---|---|---|---|---|
| int4.2.8 | sweep | 0 | 0.973 | 0.498 | 0 |
| int4.2.8 | flood | 0 | 0.988 | 0.538 | 0 |
| int6.4.8 | sweep | 0 | 0.87 | 0.152 | 0 |
| int6.4.8 | flood | 0 | 0.952 | 0.179 | 0 |

## What this means (computed)
- **int4.2.8, sweep:** McNemar p vs float = p0.003: 0.803, p0.002: 0.327, p0.001: 1 → statistically indistinguishable from float (p > 0.05 at every p). Mean iterations vs float: p0.003: ×0.974, p0.002: ×1.012, p0.001: ×1.033.
- **int6.4.8, sweep:** McNemar p vs float = p0.003: 0.668, p0.002: 1, p0.001: 1 → statistically indistinguishable from float (p > 0.05 at every p). Mean iterations vs float: p0.003: ×0.976, p0.002: ×0.997, p0.001: ×0.996.

## Not tested
- α schedules other than α = 1 (the integer mode refuses them).
- Formats between int4 and int6, other rounding rules, other γ grids.
- Hardware cost of each format (Test 3).
