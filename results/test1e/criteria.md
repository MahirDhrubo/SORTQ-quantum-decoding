# Test 1e criteria: speed targets under different real-time criteria (2026-11-12)

## Setup
- Script: `scripts/test1e_criteria.py`. It reuses the queue model of `test1e_queue.py` (one engine, FIFO,
  Lindley recursion) with the same job resampling (seed 20261112, 10^7 jobs). **No new decoding.**
- Traces (measured, existing):
  - **1b float, 12 rounds**: Test 1b F32, α = 1, sweep; one job per shot, 13 detector rounds per job; T = 12 and 8 µs.
  - **1d global, 36 rounds**: one job per shot, 37 detector rounds per job; T = 36 µs.
  - **1d W12_C8 / W8_C4**: one job per window; W = 12 / 8 rounds per job; T = C µs (8 / 4 µs).
- Fixed: K uncapped (18,080), overhead 200 ns per job, 1 round = 1 µs (as in Test 1e).
- Criteria, each searched separately for the largest t_iter at 1 ns resolution:
  - **(a) throughput only:** utilization < 0.7 **and** queue max < 1000 jobs (max over the 10^7 jobs);
  - **(b)** p99.9 latency < 100 µs; **(c)** < 1 ms; **(d)** < 10 ms.
  - (b)–(d) have no 0.7 utilization condition (only util < 1, i.e. stable); the utilization at the answer is
    reported in the detail table.
- **t_iter per round** = t_iter max / rounds per job (13, 37, 12, 8).
- **IBM flood design**: the Test 1b float flood trace at 24 ns per (13-round) iteration = 1.85 ns per round,
  overhead 200 ns; 12-round traces only.
- Check: criterion (b) reproduces all earlier Part C results exactly (13, 11, 50, 38, 624, 472 ns for 1b; 7, 38 /
  6, 24 / 5, 19 ns for 1d global / W12_C8 / W8_C4).
- Run on the server, 2 cores, 70 s.

## Results

### Largest t_iter per criterion: ns per iteration (ns per round in brackets)
| Trace | rounds / job | p | T (µs) | (a) throughput | (b) < 100 µs | (c) < 1 ms | (d) < 10 ms |
|---|---|---|---|---|---|---|---|
| 1b float, 12 rounds | 13 | 0.003 | 12 | 255 ns (19.6) | 13 ns (1) | 65 ns (5) | 328 ns (25.2) |
| 1b float, 12 rounds | 13 | 0.003 | 8 | 169 ns (13) | 11 ns (0.846) | 61 ns (4.69) | 252 ns (19.4) |
| 1b float, 12 rounds | 13 | 0.002 | 12 | 363 ns (27.9) | 50 ns (3.85) | 129 ns (9.92) | 595 ns (45.8) |
| 1b float, 12 rounds | 13 | 0.002 | 8 | 241 ns (18.5) | 38 ns (2.92) | 107 ns (8.23) | 544 ns (41.8) |
| 1b float, 12 rounds | 13 | 0.001 | 12 | 1535 ns (118) | 624 ns (48) | 1396 ns (107) | 2202 ns (169) |
| 1b float, 12 rounds | 13 | 0.001 | 8 | 1011 ns (77.8) | 472 ns (36.3) | 1077 ns (82.8) | 1458 ns (112) |
| 1d global, 36 rounds | 37 | 0.003 | 36 | 310 ns (8.38) | 7 ns (0.189) | 55 ns (1.49) | 241 ns (6.51) |
| 1d global, 36 rounds | 37 | 0.002 | 36 | 1081 ns (29.2) | 38 ns (1.03) | 110 ns (2.97) | 598 ns (16.2) |
| 1d W12_C8 | 12 | 0.003 | 8 | 99 ns (8.25) | 6 ns (0.5) | 32 ns (2.67) | 145 ns (12.1) |
| 1d W12_C8 | 12 | 0.002 | 8 | 208 ns (17.3) | 24 ns (2) | 72 ns (6) | 300 ns (25) |
| 1d W8_C4 | 8 | 0.003 | 4 | 50 ns (6.25) | 5 ns (0.625) | 29 ns (3.62) | 88 ns (11) |
| 1d W8_C4 | 8 | 0.002 | 4 | 73 ns (9.12) | 19 ns (2.38) | 56 ns (7) | 217 ns (27.1) |

### Does IBM's flood design (24 ns / 13-round iteration) meet each criterion? (12-round traces)
| p | T (µs) | IBM util | IBM p99.9 (µs) | IBM queue max | (a) | (b) | (c) | (d) |
|---|---|---|---|---|---|---|---|---|
| 0.003 | 12 | 0.082 | 344.0 | 67 | **yes** | **no** | **yes** | **yes** |
| 0.003 | 8 | 0.124 | 377.3 | 104 | **yes** | **no** | **yes** | **yes** |
| 0.002 | 12 | 0.043 | 16.4 | 36 | **yes** | **yes** | **yes** | **yes** |
| 0.002 | 8 | 0.064 | 33.4 | 54 | **yes** | **yes** | **yes** | **yes** |
| 0.001 | 12 | 0.030 | 1.3 | 3 | **yes** | **yes** | **yes** | **yes** |
| 0.001 | 8 | 0.046 | 1.3 | 5 | **yes** | **yes** | **yes** | **yes** |

### Detail: what limits each answer, and the queue at that t_iter
| Trace | p | T (µs) | criterion | t_iter max (ns) | per round (ns) | limited by | util | p99.9 (µs) | queue max |
|---|---|---|---|---|---|---|---|---|---|
| 1b float, 12 rounds | 0.003 | 12 | a | 255 | 19.6 | queue max | 0.530 | 5,748.5 | 999 |
| 1b float, 12 rounds | 0.003 | 12 | b | 13 | 1 | p99.9 latency | 0.043 | 96.3 | 25 |
| 1b float, 12 rounds | 0.003 | 12 | c | 65 | 5 | p99.9 latency | 0.148 | 990.1 | 183 |
| 1b float, 12 rounds | 0.003 | 12 | d | 328 | 25.2 | p99.9 latency | 0.677 | 9,944.1 | 1,499 |
| 1b float, 12 rounds | 0.003 | 8 | a | 169 | 13 | queue max | 0.536 | 3,820.7 | 994 |
| 1b float, 12 rounds | 0.003 | 8 | b | 11 | 0.846 | p99.9 latency | 0.058 | 98.2 | 36 |
| 1b float, 12 rounds | 0.003 | 8 | c | 61 | 4.69 | p99.9 latency | 0.209 | 991.6 | 263 |
| 1b float, 12 rounds | 0.003 | 8 | d | 252 | 19.4 | p99.9 latency | 0.786 | 9,826.7 | 1,877 |
| 1b float, 12 rounds | 0.002 | 12 | a | 363 | 27.9 | queue max | 0.322 | 5,325.0 | 999 |
| 1b float, 12 rounds | 0.002 | 12 | b | 50 | 3.85 | p99.9 latency | 0.059 | 98.0 | 75 |
| 1b float, 12 rounds | 0.002 | 12 | c | 129 | 9.92 | p99.9 latency | 0.125 | 994.5 | 268 |
| 1b float, 12 rounds | 0.002 | 12 | d | 595 | 45.8 | p99.9 latency | 0.517 | 9,985.8 | 1,734 |
| 1b float, 12 rounds | 0.002 | 8 | a | 241 | 18.5 | queue max | 0.329 | 3,540.8 | 996 |
| 1b float, 12 rounds | 0.002 | 8 | b | 38 | 2.92 | p99.9 latency | 0.073 | 96.4 | 88 |
| 1b float, 12 rounds | 0.002 | 8 | c | 107 | 8.23 | p99.9 latency | 0.160 | 988.0 | 367 |
| 1b float, 12 rounds | 0.002 | 8 | d | 544 | 41.8 | p99.9 latency | 0.711 | 9,996.3 | 2,448 |
| 1b float, 12 rounds | 0.001 | 12 | a | 1535 | 118 | utilization < 0.7 | 0.700 | 1,251.0 | 342 |
| 1b float, 12 rounds | 0.001 | 12 | b | 624 | 48 | p99.9 latency | 0.294 | 99.6 | 95 |
| 1b float, 12 rounds | 0.001 | 12 | c | 1396 | 107 | p99.9 latency | 0.638 | 999.1 | 304 |
| 1b float, 12 rounds | 0.001 | 12 | d | 2202 | 169 | p99.9 latency | 0.996 | 9,912.7 | 879 |
| 1b float, 12 rounds | 0.001 | 8 | a | 1011 | 77.8 | utilization < 0.7 | 0.700 | 819.2 | 338 |
| 1b float, 12 rounds | 0.001 | 8 | b | 472 | 36.3 | p99.9 latency | 0.340 | 99.6 | 116 |
| 1b float, 12 rounds | 0.001 | 8 | c | 1077 | 82.8 | p99.9 latency | 0.744 | 997.5 | 365 |
| 1b float, 12 rounds | 0.001 | 8 | d | 1458 | 112 | p99.9 latency | 0.998 | 9,000.4 | 1,179 |
| 1d global, 36 rounds | 0.003 | 36 | a | 310 | 8.38 | utilization < 0.7 | 0.698 | 19,836.8 | 901 |
| 1d global, 36 rounds | 0.003 | 36 | b | 7 | 0.189 | p99.9 latency | 0.021 | 91.1 | 6 |
| 1d global, 36 rounds | 0.003 | 36 | c | 55 | 1.49 | p99.9 latency | 0.128 | 994.6 | 67 |
| 1d global, 36 rounds | 0.003 | 36 | d | 241 | 6.51 | p99.9 latency | 0.544 | 9,930.2 | 475 |
| 1d global, 36 rounds | 0.002 | 36 | a | 1081 | 29.2 | queue max | 0.565 | 21,638.4 | 999 |
| 1d global, 36 rounds | 0.002 | 36 | b | 38 | 1.03 | p99.9 latency | 0.025 | 95.2 | 19 |
| 1d global, 36 rounds | 0.002 | 36 | c | 110 | 2.97 | p99.9 latency | 0.062 | 993.0 | 70 |
| 1d global, 36 rounds | 0.002 | 36 | d | 598 | 16.2 | p99.9 latency | 0.315 | 9,989.9 | 527 |
| 1d W12_C8 | 0.003 | 8 | a | 99 | 8.25 | queue max | 0.570 | 4,159.7 | 992 |
| 1d W12_C8 | 0.003 | 8 | b | 6 | 0.5 | p99.9 latency | 0.058 | 80.6 | 27 |
| 1d W12_C8 | 0.003 | 8 | c | 32 | 2.67 | p99.9 latency | 0.201 | 987.5 | 233 |
| 1d W12_C8 | 0.003 | 8 | d | 145 | 12.1 | p99.9 latency | 0.823 | 9,994.1 | 1,890 |
| 1d W12_C8 | 0.002 | 8 | a | 208 | 17.3 | queue max | 0.445 | 5,981.6 | 999 |
| 1d W12_C8 | 0.002 | 8 | b | 24 | 2 | p99.9 latency | 0.073 | 98.9 | 107 |
| 1d W12_C8 | 0.002 | 8 | c | 72 | 6 | p99.9 latency | 0.170 | 996.0 | 324 |
| 1d W12_C8 | 0.002 | 8 | d | 300 | 25 | p99.9 latency | 0.631 | 9,967.1 | 1,558 |
| 1d W8_C4 | 0.003 | 4 | a | 50 | 6.25 | queue max | 0.538 | 1,876.0 | 981 |
| 1d W8_C4 | 0.003 | 4 | b | 5 | 0.625 | p99.9 latency | 0.099 | 81.4 | 44 |
| 1d W8_C4 | 0.003 | 4 | c | 29 | 3.62 | p99.9 latency | 0.333 | 980.9 | 492 |
| 1d W8_C4 | 0.003 | 4 | d | 88 | 11 | p99.9 latency | 0.908 | 9,349.6 | 2,812 |
| 1d W8_C4 | 0.002 | 4 | a | 73 | 9.12 | queue max | 0.323 | 1,667.7 | 988 |
| 1d W8_C4 | 0.002 | 4 | b | 19 | 2.38 | p99.9 latency | 0.121 | 96.5 | 255 |
| 1d W8_C4 | 0.002 | 4 | c | 56 | 7 | p99.9 latency | 0.259 | 993.3 | 757 |
| 1d W8_C4 | 0.002 | 4 | d | 217 | 27.1 | p99.9 latency | 0.861 | 9,952.5 | 2,974 |

## What this means for Idea 1
1. **The criterion decides the speed target, by more than an order of magnitude.** For the 12-round traces at
   p = 0.003, T = 12 µs: 13 ns (p99.9 < 100 µs) → 65 ns (< 1 ms) → 328 ns (< 10 ms); throughput only allows 255 ns.
   The decoder just has to keep up on average; it is the rare long decodes (up to 18,080 iterations) that set
   the tight latency targets.
2. **IBM's flood design fails only the strictest criterion, only at p = 0.003** (p99.9 = 344 / 377 µs). It meets
   (a), (c) and (d) at every p, and (b) at p = 0.002 and 0.001.
3. **Per round, windows relax the target vs global 36-round decoding** under the latency criteria:
   p = 0.003, < 100 µs: 0.50–0.63 ns per round (W12_C8, W8_C4) vs 0.19 (global); < 1 ms: 2.7–3.6 vs 1.5. Under
   throughput only (a), the order flips: global 8.4 ns per round vs 6.3–8.3 for windows. For the windows the
   queue-max limit (1000 jobs) binds first; for global p = 0.003 it is utilization.
4. **(a) alone is not a real-time guarantee.** At the (a) limit the p99.9 latency is milliseconds
   (e.g. 5.7 ms for 12-round, p = 0.003, T = 12 µs; 20 ms for global, p = 0.003).
5. **Under (d) the utilization can exceed 0.7**: 0.79–0.91 for several traces at p = 0.003, and 0.996–0.998 for
   12-round, p = 0.001. With so little margin, these targets are sensitive to the arrival model.

## Not tested
- Queue max depends on the simulated length (10^7 jobs = 40–360 s of operation). A longer run would give a larger
  maximum and a smaller (a) target.
- K < 18,080 (iteration caps): earlier Part A showed every cap ≤ 1000 raises LER more than 1.1×.
- Overhead other than 200 ns; W6_C3; flood traces for 1d (not decoded); multiple engines; non-FIFO scheduling.
- IBM's design on 1d traces (no 36-round flood traces exist).
