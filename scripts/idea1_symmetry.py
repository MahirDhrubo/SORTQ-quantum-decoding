"""Idea 1, test 1: space (shift-group) and time (round-shift) symmetry of a circuit-level DEM.

Nothing about the qubit layout is assumed. Every detector is labelled from the circuit itself:
  - check identity = the single ancilla qubit among its measurement records
  - check type     = basis of that ancilla's measurement (M -> Z check, MX -> X check)
  - round          = occurrence number of that ancilla measurement (0-based); +1 if the detector also uses the
                     final data-qubit measurements (the closing boundary detectors)
The script asserts these labels are well defined and stops otherwise.

Matrices: 'full' = the DEM as Stim gives it (decompose_errors=False);
          'xdec' = X-decoder projection: Z-type detectors only, errors that flip none dropped, errors with identical
                   remaining detector sets merged (p combined as the parity of independent events; observables XORed
                   is NOT done: the number of merged groups with differing observables is reported instead).
Levels:   L1 = H only; L2 = H + priors; L3 = H + priors + observables.
Columns with identical H support are collapsed to one vertex whose colour is the multiset of their labels at the
level (L1: multiplicity), so nauty cannot report swaps of duplicate columns as symmetries.

Usage: python idea1_symmetry.py <circuit.stim> <out.json> [--compare-structure other_p.stim]
"""
import sys, json, time, itertools
from collections import Counter, defaultdict
import numpy as np
import stim
import pynauty


# ---------------------------------------------------------------- labelling from the circuit
def label_detectors(circ):
    flat = circ.flattened()
    meas = []                                  # per measurement: (qubit, basis, noisy?)
    det_recs = []
    for inst in flat:
        name = inst.name
        if name in ("M", "MX", "MY", "MR", "MRX", "MRY"):
            basis = {"M": "Z", "MR": "Z", "MX": "X", "MRX": "X", "MY": "Y", "MRY": "Y"}[name]
            noisy = len(inst.gate_args_copy()) > 0
            for t in inst.targets_copy():
                meas.append((t.value, basis, noisy))
        elif name == "DETECTOR":
            n = len(meas)
            det_recs.append([n + t.value for t in inst.targets_copy()])
    assert len(det_recs) == circ.num_detectors
    # final data measurement = the last measurement instruction without noise argument
    final = {i for i, (_, _, noisy) in enumerate(meas) if not noisy}
    final_qubits = {meas[i][0] for i in final}
    occ = {}
    cnt = Counter()
    for i, (q, b, noisy) in enumerate(meas):
        if i not in final:
            occ[i] = cnt[q]; cnt[q] += 1
    labels = []
    for d, recs in enumerate(det_recs):
        anc = [i for i in recs if i not in final]
        anc_q = {meas[i][0] for i in anc}
        assert len(anc_q) == 1, f"detector {d}: ancillas {anc_q}"
        q = anc_q.pop()
        assert q not in final_qubits
        last = max(anc)
        uses_final = any(i in final for i in recs)
        labels.append(dict(anc=q, typ=meas[last][1], rnd=occ[last] + (1 if uses_final else 0),
                           boundary_final=uses_final))
    return labels


# ---------------------------------------------------------------- DEM -> columns
def dem_columns(dem):
    cols = []
    for inst in dem.flattened():
        if inst.type != "error":
            continue
        p = inst.args_copy()[0]
        dets, obs = [], 0
        for t in inst.targets_copy():
            if t.is_relative_detector_id():
                dets.append(t.val)
            elif t.is_logical_observable_id():
                obs ^= 1 << t.val
        cols.append((tuple(sorted(dets)), p, obs))
    return cols


def project(cols, keep_rows):
    keep = set(keep_rows)
    groups = defaultdict(list)
    for dets, p, obs in cols:
        s = tuple(d for d in dets if d in keep)
        if s:
            groups[s].append((p, obs))
    out, conflict = [], 0
    for s, lst in groups.items():
        p = 0.0
        for q, _ in lst:
            p = p * (1 - q) + q * (1 - p)
        obs = {o for _, o in lst}
        if len(obs) > 1:
            conflict += 1
        out.append((s, p, lst[0][1] if len(obs) == 1 else -1))
    return out, conflict, len(groups)


def collapse(cols, level):
    """support -> colour (multiset of labels at the level)."""
    g = defaultdict(list)
    for dets, p, obs in cols:
        if level == 1:
            g[dets].append(0)
        elif level == 2:
            g[dets].append(f"{p:.9g}")
        else:
            g[dets].append((f"{p:.9g}", obs))
    return {s: tuple(sorted(v, key=str)) for s, v in g.items() if len(s) > 0}


# ---------------------------------------------------------------- nauty
def automorphisms(rows, row_colour, sup2col):
    """rows: list of detector ids; sup2col: support -> colour."""
    ridx = {d: i for i, d in enumerate(rows)}
    m = len(rows)
    sups = list(sup2col)
    adj = defaultdict(list)
    for j, s in enumerate(sups):
        for d in s:
            adj[ridx[d]].append(m + j)
    parts = defaultdict(set)
    for i, d in enumerate(rows):
        parts[("r", row_colour[d])].add(i)
    for j, s in enumerate(sups):
        parts[("c", str(sup2col[s]))].add(m + j)
    keys = sorted(parts, key=str)
    g = pynauty.Graph(m + len(sups), directed=False, adjacency_dict=dict(adj),
                      vertex_coloring=[parts[k] for k in keys])
    t0 = time.time()
    gens, s1, s2, orbits, norb = pynauty.autgrp(g)
    order = round(s1 * 10 ** s2)
    return dict(gens=[np.array(x, dtype=np.int64) for x in gens], order=order, orbits=np.array(orbits),
                n_vertices=m + len(sups), m=m, sups=sups, seconds=round(time.time() - t0, 1))


def close_group(gens, n, limit=5000):
    ident = np.arange(n)
    elems = {ident.tobytes(): ident}
    frontier = [ident]
    while frontier:
        nxt = []
        for e in frontier:
            for g in gens:
                h = g[e]
                k = h.tobytes()
                if k not in elems:
                    elems[k] = h; nxt.append(h)
                    if len(elems) > limit:
                        return None
        frontier = nxt
    return list(elems.values())


def perm_order(p):
    ident = np.arange(len(p)); q = p.copy(); k = 1
    while not np.array_equal(q, ident):
        q = p[q]; k += 1
    return k


def order_profile_cyclic_product(ns):
    from math import gcd
    def lcm(a, b): return a * b // gcd(a, b)
    c = Counter()
    for t in itertools.product(*[range(n) for n in ns]):
        o = 1
        for x, n in zip(t, ns):
            o = lcm(o, n // gcd(n, x))
        c[o] += 1
    return dict(sorted(c.items()))


def group_report(A):
    n = A["n_vertices"]
    G = close_group(A["gens"], n)
    rep = dict(order=A["order"], n_generators=len(A["gens"]), nauty_seconds=A["seconds"])
    if G is None:
        rep["note"] = "group larger than 5000, not enumerated"
        return rep, None
    abelian = all(np.array_equal(g[h], h[g]) for g in A["gens"] for h in A["gens"])
    prof = dict(sorted(Counter(perm_order(g) for g in G).items()))
    rep.update(abelian=abelian, element_orders=prof)
    if len(G) == 72:
        rep["matches_Z12xZ6"] = prof == order_profile_cyclic_product([12, 6])
    # freeness: every orbit has size |G|
    orb = Counter(A["orbits"])
    sizes = Counter(orb[o] for o in A["orbits"])
    rep["orbit_size_histogram_vertices"] = {int(k): int(v) for k, v in sizes.items()}
    m = A["m"]
    rep["row_orbits"] = len(set(A["orbits"][:m])); rep["col_orbits"] = len(set(A["orbits"][m:]))
    rep["free"] = set(sizes) == {len(G)}
    return rep, G


# ---------------------------------------------------------------- time shift
def time_test(rows, lab, sup2col):
    key = {d: (lab[d]["anc"], lab[d]["rnd"]) for d in rows}
    inv = {v: d for d, v in key.items()}
    R = max(lab[d]["rnd"] for d in rows)
    by_start = defaultdict(list)
    for s in sup2col:
        by_start[min(lab[d]["rnd"] for d in s)].append(s)
    res = {}
    for r in range(R):
        ok = 0
        for s in by_start[r]:
            t = []
            for d in s:
                a, rr = key[d]
                if (a, rr + 1) not in inv:
                    t = None; break
                t.append(inv[(a, rr + 1)])
            if t is not None:
                t = tuple(sorted(t))
                if t in sup2col and sup2col[t] == sup2col[s]:
                    ok += 1
        res[r] = dict(cols_starting=len(by_start[r]), map_to_next=ok, next_count=len(by_start[r + 1]))
    res[R] = dict(cols_starting=len(by_start[R]))
    return res


def analyse(name, rows, lab, cols):
    out = {}
    for level in (1, 2, 3):
        s2c = collapse(cols, level)
        lv = dict(n_rows=len(rows), n_cols_raw=len(cols), n_distinct_supports=len(s2c))
        for mode in ("type", "type+round"):
            colour = {d: (lab[d]["typ"],) if mode == "type" else (lab[d]["typ"], lab[d]["rnd"]) for d in rows}
            A = automorphisms(rows, colour, s2c)
            rep, G = group_report(A)
            lv[f"space[{mode}]"] = rep
            print(name, f"L{level}", mode, json.dumps(rep), flush=True)
            if mode == "type+round" and G is not None and rep.get("free"):
                # base graph per round
                m = A["m"]
                orbit_rep_rows = {}
                for i in range(m):
                    orbit_rep_rows.setdefault(A["orbits"][i], i)
                rr = Counter(lab[rows[i]]["rnd"] for i in orbit_rep_rows.values())
                orbit_rep_cols = {}
                for j in range(len(A["sups"])):
                    orbit_rep_cols.setdefault(A["orbits"][m + j], j)
                cr = Counter(min(lab[d]["rnd"] for d in A["sups"][j]) for j in orbit_rep_cols.values())
                lv["base_graph_per_round"] = {int(r): dict(row_orbits=rr.get(r, 0), col_orbits=cr.get(r, 0))
                                              for r in sorted(set(rr) | set(cr))}
        lv["time"] = time_test(rows, lab, s2c)
        print(name, f"L{level}", "time", json.dumps(lv["time"]), flush=True)
        out[f"L{level}"] = lv
    return out


if __name__ == "__main__":
    path, outp = sys.argv[1], sys.argv[2]
    circ = stim.Circuit.from_file(path)
    lab = label_detectors(circ)
    dem = circ.detector_error_model(decompose_errors=False)
    cols = dem_columns(dem)
    res = dict(circuit=path, detectors=len(lab), errors=len(cols),
               detectors_by_type_round={f"{t}{r}": c for (t, r), c in
                                        sorted(Counter((l["typ"], l["rnd"]) for l in lab).items())},
               empty_columns=sum(1 for c in cols if not c[0]))
    print(json.dumps({k: v for k, v in res.items()}), flush=True)
    if "--compare-structure" in sys.argv:
        other = stim.Circuit.from_file(sys.argv[sys.argv.index("--compare-structure") + 1])
        oc = dem_columns(other.detector_error_model(decompose_errors=False))
        res["same_H_and_obs_as_other_p"] = sorted((d, o) for d, _, o in cols) == sorted((d, o) for d, _, o in oc)
        print("same structure at other p:", res["same_H_and_obs_as_other_p"], flush=True)
    rows_all = list(range(len(lab)))
    res["full"] = analyse("full", rows_all, lab, cols)
    zrows = [d for d in rows_all if lab[d]["typ"] == "Z"]
    pcols, conflict, ngroups = project(cols, zrows)
    res["xdec_projection"] = dict(rows=len(zrows), cols_after_merge=len(pcols), merged_groups_with_differing_obs=conflict)
    print("xdec", json.dumps(res["xdec_projection"]), flush=True)
    res["xdec"] = analyse("xdec", zrows, lab, [(s, p, o) for s, p, o in pcols])
    json.dump(res, open(outp, "w"), indent=1, default=int)
    print("DONE", flush=True)
