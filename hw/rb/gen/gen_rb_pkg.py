"""Test 2f: generate rb_pkg.sv (red-black round engine constants) from the decoder matrix H and the processing order.

Order (Test 1g schedule (2), rb13): rounds 0, 2, 4, ..., R(even), 1, 3, ..., i.e. all even rounds, then all odd rounds.
pos(r) = position of round r in the order; pass(r) = 0 for the first colour (even rounds), 1 for the second.

Everything below is derived by enumeration over H (every check row, every error column) and then asserted to depend
only on (pass, base edge) or (pass, group, type, slot), so the hardware needs one table per pass:

  Leg-start gating (init = 1, first iteration of a relay leg; memories are NOT cleared):
    CNU  input on edge (check round c, error e) is gated to the prior L0  iff  no round of e comes before c in the
         order (e has not been updated yet in this iteration; one-round errors are therefore always gated).
    VNU  c2v input of error e from a check of round c', while e is updated in the step of round c, is gated to 0
         iff pos(c') > pos(c) (that check has not run yet in this iteration).
  Hazard distance: the smallest number of issue slots (cyclic over iterations, 13 slots per iteration) between two
    steps that touch a common error. A step reads the state of the errors it touches and writes it back D cycles
    later, so steps issued one per cycle need no forwarding iff every such distance is > D. Reported (gross code: 6).
  Consecutive steps sharing an error are listed in the report (none for the gross code; Test 1g H check).
  CNU split (two pipeline stages): the 35 base edges in NG groups of at most GSZ (stage 1: one cnu per group gives
    min1 / min2 / index / parity; stage 2 merges the groups).

Pipeline check (Test 2e / sortq build --order rb): the engine reads an error's state (v2c) 4 cycles before writing it
  back, so two steps that share an error must issue >= MIN_DIST = 5 slots apart (cyclic). If the distance of the plain
  order is smaller, the fewest cycles per iteration with idle issue slots (stalls) is searched and reported; the RTL
  itself has no stall logic, so such an order needs a modified ctrl_rb.

Usage (the SORTQ Python environment python): python gen_rb_pkg.py [circuit.stim] [outdir] [engine_params.json]
  defaults: the Test 2a gross-code circuit, ../rtl, results/test1c/engine_params.json (= the files in hw/rb/rtl).
  sortq build --order rb calls it with the build's circuit, output directory and engine_params.json (any code, basis).
"""
import sys, os, json
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
for p in ("../../gen", "../../golden", "../../../scripts"): sys.path.insert(0, os.path.join(HERE, p))
GSZ = 8
MIN_DIST = 5        # v2c read -> write 4 cycles; a write in cycle t is seen by a read in t + 1


def order_of(R):
    return [r for r in range(R + 1) if r % 2 == 0] + [r for r in range(R + 1) if r % 2 == 1]


def min_period(NS, pairs, dmin):
    """fewest cycles per iteration (issue period P) for NS steps in the given order, with idle slots allowed, such that
    every pair of steps sharing an error is >= dmin cycles apart in both directions (cyclic) and P >= dmin."""
    def full_ok(c, P):
        return all(min((c[b] - c[a]) % P, (c[a] - c[b]) % P) >= dmin for a, b in pairs)
    for P in range(max(NS, dmin), 4 * NS + dmin):
        def dfs(c):
            if len(c) == NS:
                return full_ok(c, P)
            for t in range(c[-1] + 1, P - (NS - len(c)) + 1):
                c.append(t)
                if all(c[b] - c[a] >= dmin for a, b in pairs if b == len(c) - 1) and dfs(c):
                    return True
                c.pop()
            return False
        c = [0]
        if dfs(c):
            return dict(cycles_per_iteration=P, stall_cycles=P - NS, issue_cycles=list(c))
    raise RuntimeError("no schedule")


def main():
    from golden import problem, CIRC
    from labels import labels
    circ = sys.argv[1] if len(sys.argv) > 1 else CIRC
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(HERE, "..", "rtl")
    epf = sys.argv[3] if len(sys.argv) > 3 else os.path.join(HERE, "..", "..", "..", "results", "test1c", "engine_params.json")
    ep = json.load(open(epf))
    if circ == CIRC and len(sys.argv) <= 3:
        P = problem()
    else:
        from dem_tools import decoder_problem
        P = decoder_problem(circ, ep.get("check_type", "Z"))
    L = labels(P, ep); H = P["H"].tocsr(); Hc = H.tocsc()
    be = ep["base_edge_table"] if "base_edge_table" in ep else ep["base_edge_table_round5"]; tn = L["tnames"]; NT = len(tn); NBASE = len(be)
    types = {t["type"]: t for t in ep["error_types"]}
    DV = max(t["weight"] for t in ep["error_types"])
    slot = {}
    for t in ep["error_types"]:
        for j, e in enumerate(t["edges"]): slot[(tn.index(t["type"]), e["round_offset"], e["shift_a"], e["shift_b"])] = j
    kslot = [slot[(tn.index(e["error_type"]), e["round_offset"], e["shift_a"], e["shift_b"])] for e in be]
    R = int(L["row_r"].max()); ORD = order_of(R); pos = {r: i for i, r in enumerate(ORD)}
    passof = lambda r: 0 if r % 2 == 0 else 1
    rounds_of = [sorted(set(int(L["row_r"][i]) for i in Hc.indices[Hc.indptr[j]:Hc.indptr[j + 1]])) for j in range(H.shape[1])]

    # ---- CNU gating, per (pass, base edge), from every edge of H
    cg = {}; ncg = [0, 0]
    for i in range(H.shape[0]):
        c = int(L["row_r"][i])
        for j in H.indices[H.indptr[i]:H.indptr[i + 1]]:
            k = L["edge_base"](i, int(j)); gate = all(pos[r2] >= pos[c] for r2 in rounds_of[j])
            key = (passof(c), k)
            assert cg.setdefault(key, gate) == gate, f"CNU gating of base edge {k} differs within pass {key[0]}"
            ncg[passof(c)] += 1
    # ---- VNU gating, per (pass, group d = c - home, type, slot)
    vg = {}
    for c in range(R + 1):
        for j in range(H.shape[1]):
            if c not in rounds_of[j]: continue
            h = int(L["col_h"][j]); d = c - h; t = int(L["col_t"][j])
            for i in Hc.indices[Hc.indptr[j]:Hc.indptr[j + 1]]:
                c2 = int(L["row_r"][i]); s = kslot[L["edge_base"](int(i), j)]
                gate = pos[c2] > pos[c]; key = (passof(c), d, t, s)
                assert vg.setdefault(key, gate) == gate, f"VNU gating differs within {key}"
    # ---- dependency distance (cyclic slots) between steps that touch a common error
    NS = len(ORD); dmin = NS; pairs = set()
    for j in range(H.shape[1]):
        ps = sorted({pos[r] for r in rounds_of[j]})
        for a in ps:
            for b in ps:
                if a < b: pairs.add((a, b))
                if a == b: continue
                dmin = min(dmin, (b - a) % NS)
    consecutive = [(ORD[s_], ORD[(s_ + 1) % NS]) for s_ in range(NS)
                   if any((ORD[s_] in rr and ORD[(s_ + 1) % NS] in rr) for rr in rounds_of)]
    dmin = min(dmin, NS)         # self distance (same step, next iteration) = NS
    stall = min_period(NS, sorted(pairs), MIN_DIST)

    # ---- CNU groups
    NG = (NBASE + GSZ - 1) // GSZ
    gof = [k // GSZ for k in range(NBASE)]; lof = [k % GSZ for k in range(NBASE)]
    gsize = [sum(1 for k in range(NBASE) if gof[k] == g) for g in range(NG)]

    hdr = f"// GENERATED by hw/rb/gen/gen_rb_pkg.py from H ({os.path.basename(circ)[:60]}...) — do not edit by hand.\n"
    bits = lambda v: "'{" + ", ".join(f"1'b{int(x)}" for x in v) + "}"
    arr = lambda v: "'{" + ", ".join(str(int(x)) for x in v) + "}"
    Pk = [hdr, "package rb_pkg;", "  import round_wiring_pkg::*;",
          f"  localparam int NSTEP = {NS};   // round steps per iteration",
          f"  localparam int ORDER [{NS}] = {arr(ORD)};  // red-black processing order (rb13)",
          f"  localparam int HAZ_DIST = {dmin};   // min issue-slot distance between two steps touching a common error",
          f"  localparam int NG = {NG};          // CNU stage-1 groups",
          f"  localparam int GSZ = {GSZ};",
          f"  localparam int GSIZE [{NG}] = {arr(gsize)};",
          "  // leg-start gating by pass (0 = even rounds, 1 = odd rounds); rule in the generator header"]
    for p in (0, 1):
        Pk.append(f"  localparam bit CNU_GATE_P{p} [{NBASE}] = {bits(cg.get((p, k), False) for k in range(NBASE))};")
    for p in (0, 1):
        for d, nm in ((0, "CUR"), (1, "PREV")):
            rows = []
            for t in range(NT):
                rows.append(bits(vg.get((p, d, t, s), False) for s in range(DV)))
            Pk.append(f"  localparam bit VG_{nm}_P{p} [{NT}][{DV}] = '{{{', '.join(rows)}}};")
    Pk.append("endpackage")
    open(os.path.join(out, "rb_pkg.sv"), "w").write("\n".join(Pk) + "\n")

    # report
    rep = dict(order=ORD, hazard_distance=dmin, min_dependency_distance=dmin, required_distance=MIN_DIST,
               meets_pipeline=dmin >= MIN_DIST, stall_cycles_per_iteration=stall["stall_cycles"],
               cycles_per_iteration=stall["cycles_per_iteration"], issue_cycles=stall["issue_cycles"],
               consecutive_steps_sharing_an_error=consecutive, cnu_groups=gsize,
               cnu_gated={p: [k for k in range(NBASE) if cg.get((p, k))] for p in (0, 1)},
               cnu_not_gated={p: [k for k in range(NBASE) if (p, k) in cg and not cg[(p, k)]] for p in (0, 1)},
               cnu_edges_enumerated=ncg,
               vnu_gated={f"pass{p}_{'cur' if d == 0 else 'prev'}": [f"{tn[t]}.{s}" for t in range(NT) for s in range(DV) if vg.get((p, d, t, s))]
                          for p in (0, 1) for d in (0, 1)})
    json.dump(rep, open(os.path.join(out, "rb_pkg_report.json"), "w"), indent=1)
    print(json.dumps(rep, indent=1))
    for k in range(NBASE):
        print(f"  k {k:2d} {be[k]['error_type']} off {be[k]['round_offset']}  gate even {int(cg.get((0, k), 0))} odd {int(cg.get((1, k), 0))}")


if __name__ == "__main__":
    main()
