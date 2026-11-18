"""Test 3d: per-shot results from the simulation logs -> results_3d.csv and table_initial.md (first 103 shots)."""
import re, csv, os
HERE = os.path.dirname(os.path.abspath(__file__))
PAT = re.compile(r"shot_(p[0-9.]+)_(\w+?)_(\d+)\.txt it (\d+)/(\d+) succ (\d)/(\d) hard_bad (\d+)/(\d+) obs (\w+)/(\w+) "
                 r"legs (\d+) cycles start->done (\d+) done->obs (\d+) first_iter_start (\d+) norm_iters (\d+) mean ([\d.]+) "
                 r"leg_end_iters (\d+) mean ([\d.]+) last_iter_to_done (\d+)\s+(\w+)")
rows = []
for f, sett in (("sim_3d.log", "initial"), ("sim_3d_2.log", "extended")):
    for l in open(os.path.join(HERE, f)):
        if not l.startswith("SHOT"):
            continue
        g = PAT.search(l).groups()
        it = int(g[3])
        rows.append(dict(set=sett, p=g[0][1:], kind=g[1], shot=int(g[2]), iter_engine=it, iter_sw=int(g[4]),
                         succ_engine=int(g[5]), succ_sw=int(g[6]), hard_mismatch=int(g[7]), hard_compared=int(g[8]),
                         obs_engine=g[9], obs_sw=g[10], legs=int(g[11]), cycles_start_done=int(g[12]),
                         cycles_commit=int(g[13]), leg_end_iters=int(g[17]),
                         formula_cycles=1 + 26 * it + 10 * int(g[17]) + 10,
                         cycles_per_iter=round(int(g[12]) / it, 3), result=g[20]))
with open(os.path.join(HERE, "results_3d.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
with open(os.path.join(HERE, "table_initial.md"), "w") as f:
    f.write("| Shot | p | Kind | Iterations (engine / sw) | Success | Hard mismatches / compared | Observables (engine / sw) "
            "| Legs | Cycles start→done | Cycles / iteration | Result |\n|---|---|---|---|---|---|---|---|---|---|---|\n")
    for r in rows:
        if r["set"] != "initial":
            continue
        f.write(f"| {r['shot']} | {r['p']} | {r['kind']} | {r['iter_engine']} / {r['iter_sw']} | {r['succ_engine']} / {r['succ_sw']} "
                f"| {r['hard_mismatch']} / {r['hard_compared']:,} | {r['obs_engine']} / {r['obs_sw']} | {r['legs']} "
                f"| {r['cycles_start_done']:,} | {r['cycles_per_iter']:.2f} | {r['result']} |\n")
print(len(rows), "rows; formula residual nonzero:", sum(r["cycles_start_done"] != r["formula_cycles"] for r in rows))
