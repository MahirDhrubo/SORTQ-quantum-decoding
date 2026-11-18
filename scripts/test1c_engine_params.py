"""Idea 1, Test 1c: engine parameters and boundary embedding for the symmetry-folded round engine.

Matrix: X-decoder projection "xdec" of the IBM gross-code circuit (as in Test 1 / dem_tools.xdecoder_problem),
H only (level L1, no priors). Row labels from the circuit: check = ancilla qubit, round = occurrence of that
ancilla's measurement (+1 for detectors that use the final data measurement).

Group action: nauty on the Tanner graph with rows coloured by round (Test 1 "type+round" mode). The script
asserts: order 72, abelian, every element keeps rounds, induces the same ancilla permutation in every round,
acts consistently on columns, and is free on ancillas.

Coordinates (convention, stated in the output):
  anc0 = smallest ancilla id. g1 = order-12 element whose image of anc0 has the smallest ancilla id;
  g2 = order-6 element with <g1> ∩ <g2> = {e} whose image of anc0 has the smallest ancilla id.
  The ancilla g1^a g2^b (anc0) has coordinate x = (a, b) in Z12 x Z6.
  Check (x, r) = ancilla with coordinate x, round r.
Error columns:
  home round h = round of the earliest detector.
  For a column at position t (in Z12 x Z6), each edge to check (x, r) has round offset o = r - h and
  shift s = t - x. The column's type is its set {(o, s)}; t is chosen so that this set is lexicographically
  smallest (unique because the action is free). So the edge (check (x, r), error) is the image under
  g = x of the base edge (check (0, r), error type at position s): the rotator reads the error at x + s.

Test 2e generalisation (sortq build): any circuit of the family, either decoder basis. The group must act freely and
transitively on the N ancillas of a round (order N); it is written as Z_NA x Z_NB with g1 of maximal order NA and g2
of order NB = N / NA meeting <g1> trivially (NB = 1: cyclic). The bulk reference round is BULK_REF = R // 2 - 1
(= 5 for the gross code, 13 detector rounds). Output keys added: basis, group.structure, bulk_ref_round,
base_edge_table (same as base_edge_table_round<BULK_REF>). For the gross-code X decoder the result is unchanged.

Usage: python test1c_engine_params.py <circuit.stim> <outdir> [X|Z]   (decoder basis, default X)
"""
import sys, os, json, math, time
from collections import Counter, defaultdict
import numpy as np
from dem_tools import decoder_problem, label_detectors
from idea1_symmetry import automorphisms, close_group, perm_order

NA, NB = 12, 6                       # set in main() from the group (gross code: Z12 x Z6)
ALL = [(a, b) for a in range(NA) for b in range(NB)]
BRAM_BITS = 36 * 1024
BULK_REF = 5


def add(u, v): return ((u[0] + v[0]) % NA, (u[1] + v[1]) % NB)
def sub(u, v): return ((u[0] - v[0]) % NA, (u[1] - v[1]) % NB)


def check(cond, msg):
    if not cond:
        print("FAIL:", msg, flush=True)
        raise SystemExit(1)


def main(path, outdir, basis="X"):
    global NA, NB, ALL
    os.makedirs(outdir, exist_ok=True)
    t0 = time.time()
    CT = {"X": "Z", "Z": "X"}[basis]          # check (detector) type of the decoder
    P = decoder_problem(path, CT)
    H = P["H"].tocsr(); m, n = H.shape
    Hc = H.tocsc()
    lab = label_detectors(P["circuit"])
    anc = np.array([lab[d]["anc"] for d in P["z_rows"]])
    rnd = np.asarray(P["layers"])
    R = int(rnd.max()) + 1
    BULK_REF = R // 2 - 1
    print(f"{basis}-decoder matrix: {m} x {n}, nnz {H.nnz}, rounds {R}, bulk reference round {BULK_REF}", flush=True)
    row_of = {(int(anc[i]), int(rnd[i])): i for i in range(m)}
    check(len(row_of) == m, "two rows share (ancilla, round)")
    ancs = sorted(set(anc.tolist()))
    NANC = len(ancs)
    for r in range(R):
        check(sorted(anc[rnd == r].tolist()) == ancs, f"round {r} does not hold the same {NANC} ancillas")
    cols = [tuple(sorted(Hc.indices[Hc.indptr[j]:Hc.indptr[j + 1]].tolist())) for j in range(n)]
    check(len(set(cols)) == n, "duplicate columns")

    # ------------------------------------------------------------ group action (nauty, L1, rows coloured by round)
    A = automorphisms(list(range(m)), {i: (CT, int(rnd[i])) for i in range(m)}, {c: (0,) for c in cols})
    check([tuple(s) for s in A["sups"]] == cols, "nauty column order differs")
    G = close_group(A["gens"], m + n)
    check(G is not None and len(G) == NANC, f"group order {A['order']} != {NANC} ancillas per round")
    check(all(np.array_equal(g[h], h[g]) for g in A["gens"] for h in A["gens"]), "group not abelian")
    pis = []
    for g in G:
        pi = {}
        for i in range(m):
            j = int(g[i])
            check(rnd[j] == rnd[i], "group element changes a round")
            check(pi.setdefault(int(anc[i]), int(anc[j])) == int(anc[j]), "ancilla permutation differs between rounds")
        for jc in range(n):
            check(tuple(sorted(int(g[i]) for i in cols[jc])) == cols[int(g[m + jc]) - m], "column action inconsistent")
        pis.append(pi)
    for a in ancs:
        check(len({pi[a] for pi in pis}) == NANC, "action on ancillas not free/transitive")
    print(f"group: order {NANC}, abelian, round-preserving, same ancilla permutation in all rounds, free "
          f"(nauty {A['seconds']} s)", flush=True)

    orders = [perm_order(g) for g in G]
    ident = np.arange(m + n)
    a0 = ancs[0]

    def cyc(k):
        out, p = set(), ident.copy()
        for _ in range(orders[k]):
            out.add(p.tobytes()); p = G[k][p]
        return out

    NA = max(orders); NB = NANC // NA
    ALL = [(a, b) for a in range(NA) for b in range(NB)]
    g1 = min((k for k in range(NANC) if orders[k] == NA), key=lambda k: pis[k][a0])
    C1 = cyc(g1)
    c2 = [k for k in range(NANC) if orders[k] == NB and cyc(k) & C1 == {ident.tobytes()}]
    check(NA * NB == NANC and c2, f"group of order {NANC} is not Z_{NA} x Z_{NB}")
    g2 = min(c2, key=lambda k: pis[k][a0])
    print(f"group structure: Z{NA} x Z{NB}", flush=True)
    elem = {}
    for a in range(NA):
        for b in range(NB):
            p = ident.copy()
            for _ in range(a): p = G[g1][p]
            for _ in range(b): p = G[g2][p]
            elem[(a, b)] = p
    check(len({p.tobytes() for p in elem.values()}) == NANC, f"g1, g2 do not generate Z{NA} x Z{NB}")
    row0 = row_of[(a0, 0)]
    anc_at = {u: int(anc[elem[u][row0]]) for u in ALL}
    coord = {v: u for u, v in anc_at.items()}
    check(len(coord) == NANC, "coordinates not one-to-one")
    for u in ALL:                      # additive action: g(u) maps coordinate x to x + u, in every round
        for x in ALL:
            for r in range(R):
                i = row_of[(anc_at[x], r)]
                check(int(elem[u][i]) == row_of[(anc_at[add(x, u)], r)], "action is not translation in coordinates")
    convention = dict(
        anc0=a0, g1_image_of_anc0=anc_at[(1, 0)], g2_image_of_anc0=anc_at[(0, 1)],
        coordinate=f"ancilla g1^a g2^b (anc0) has coordinate (a, b) in Z{NA} x Z{NB}",
        shift="edge (check at x, round r) -- (error at position t, home h): offset = r - h, shift = t - x",
        base_edge="edge = image under g = x of base edge (check (0,0), round r) -- (error type placed at position = shift)",
        error_position="t chosen so the column's set {(offset, shift)} is lexicographically smallest",
        ancilla_of_coordinate={f"{a},{b}": anc_at[(a, b)] for (a, b) in ALL})

    # ------------------------------------------------------------ error types
    xr = [coord[int(anc[i])] for i in range(m)]
    col_home, col_pos, col_sig = [], [], []
    for c in cols:
        h = int(min(rnd[i] for i in c))
        cands = [(tuple(sorted((int(rnd[i]) - h,) + sub(t, xr[i]) for i in c)), t) for t in ALL]
        best = min(cands)
        check(sum(1 for s, _ in cands if s == best[0]) == 1, "column stabilised by a translation (not free)")
        col_home.append(h); col_pos.append(best[1]); col_sig.append(best[0])
    sigs = sorted(set(col_sig), key=lambda s: (s[0][0], len(s), s))
    tid = {s: k for k, s in enumerate(sigs)}
    col_type = [tid[s] for s in col_sig]
    tname = lambda k: f"T{k:02d}"
    by_round = defaultdict(Counter)
    for j in range(n):
        by_round[col_home[j]][col_type[j]] += 1
    for r in by_round:
        for k, c in by_round[r].items():
            check(c == NANC, f"type {tname(k)} has {c} columns at home round {r} (expected {NANC})")
    types_r = {r: sorted(by_round[r]) for r in range(R)}
    bulk = set(types_r[BULK_REF])
    bulk_rounds = [r for r in range(R) if set(types_r[r]) == bulk]
    print("error types per home round:", {r: len(types_r[r]) for r in range(R)}, f"| rounds with the round-{BULK_REF} type set:",
          bulk_rounds, flush=True)

    # ------------------------------------------------------------ 1. base-edge tables (check-centric)
    def check_table(i):
        x = xr[i]; r = int(rnd[i])
        return tuple(sorted((col_type[j], r - col_home[j]) + sub(col_pos[j], x) for j in H.indices[H.indptr[i]:H.indptr[i + 1]]))
    tables = [check_table(i) for i in range(m)]
    rep_table = {r: tables[row_of[(anc_at[(0, 0)], r)]] for r in range(R)}
    same_within = {r: all(tables[i] == rep_table[r] for i in range(m) if rnd[i] == r) for r in range(R)}
    same_as_bulk = {r: rep_table[r] == rep_table[BULK_REF] for r in range(R)}
    check(all(same_within.values()), "checks of one round have different tables (symmetry broken)")
    base_table = [dict(check_type=CT, error_type=tname(t), round_offset=o, shift_a=a, shift_b=b)
                  for (t, o, a, b) in rep_table[BULK_REF]]
    print(f"[1] base-edge table, round {BULK_REF}: {len(base_table)} edges; all {NANC} checks of each round share their "
          f"round's table: {all(same_within.values())}; rounds equal to round {BULK_REF}: "
          f"{[r for r in range(R) if same_as_bulk[r]]}", flush=True)

    # ------------------------------------------------------------ 2. check degree
    deg = np.diff(H.indptr)
    deg_by_round = {}
    for r in range(R):
        offs = Counter(o for (_, o, _, _) in rep_table[r])
        deg_by_round[r] = dict(degree=len(rep_table[r]), by_offset={int(o): c for o, c in sorted(offs.items())})
    deg_hist = {int(k): int(v) for k, v in sorted(Counter(deg.tolist()).items())}
    print(f"[2] check degree: max {int(deg.max())}, histogram over {m} checks {deg_hist}", flush=True)

    # ------------------------------------------------------------ 3. error types
    type_info = []
    for k, s in enumerate(sigs):
        type_info.append(dict(type=tname(k), weight=len(s), round_offsets=sorted({o for o, _, _ in s}),
                              edges=[dict(round_offset=o, shift_a=a, shift_b=b) for (o, a, b) in s],
                              home_rounds={int(r): by_round[r][k] for r in range(R) if by_round[r][k]},
                              in_bulk_template=k in bulk))
    print(f"[3] {len(sigs)} distinct error types; bulk template (round {BULK_REF}): {len(bulk)} types, weights "
          f"{sorted(len(sigs[k]) for k in bulk)}", flush=True)

    # ------------------------------------------------------------ 4. rotator settings
    shifts_bulk = sorted({(a, b) for (_, _, a, b) in rep_table[BULK_REF]})
    shifts_all = sorted({(a, b) for r in range(R) for (_, _, a, b) in rep_table[r]})
    print(f"[4] distinct shifts: bulk table {len(shifts_bulk)}, whole matrix {len(shifts_all)}", flush=True)

    # ------------------------------------------------------------ 5. boundary embedding
    bulk_sig = {k: set(sigs[k]) for k in bulk}
    occupied = {}                        # slot (host type, position, engine round) -> column
    def slots_free(host, u, h_eng, cols_):
        return all((host, add(col_pos[j], u), h_eng) not in occupied for j in cols_)
    cols_of = defaultdict(list)
    for j in range(n):
        cols_of[(col_home[j], col_type[j])].append(j)
    for r in range(R):                   # class (a) columns occupy their own slots first
        for k in types_r[r]:
            if k in bulk:
                for j in cols_of[(r, k)]:
                    occupied[(k, col_pos[j], r)] = j
    classes, embed = {}, {}
    for r in range(R):
        cl = []
        for k in types_r[r]:
            if k in bulk:
                cl.append(dict(type=tname(k), cls="a")); continue
            cands = []
            for B in sorted(bulk):
                for tau in range(-R, R + 1):
                    if not 0 <= r - tau < R:
                        continue
                    for u in ALL:
                        img = {(o + tau,) + add((a, b), u) for (o, a, b) in sigs[k]}
                        if img <= bulk_sig[B]:
                            cands.append((abs(tau), -tau, B, u, img))
            cands.sort(key=lambda c: (c[0], c[1], c[2], c[3]))
            chosen = None
            for (_, mtau, B, u, img) in cands:
                if slots_free(B, u, r + mtau, cols_of[(r, k)]):
                    chosen = (B, u, -mtau, img); break
            if cands and chosen is None:
                chosen = (cands[0][2], cands[0][3], -cands[0][1], cands[0][4])
                conflict = True
            else:
                conflict = False
            if chosen:
                B, u, tau, img = chosen
                for j in cols_of[(r, k)]:
                    occupied.setdefault((B, add(col_pos[j], u), r - tau), j)
                embed[(r, k)] = chosen
                cl.append(dict(type=tname(k), cls="b", host=tname(B), translation_u=list(u), time_shift_tau=tau,
                               engine_home_round=r - tau, masked_edges=len(sigs[B]) - len(img),
                               n_candidate_embeddings=len(cands), slot_conflict=conflict))
            else:
                cl.append(dict(type=tname(k), cls="c",
                               edges=[dict(round_offset=o, shift_a=a, shift_b=b) for (o, a, b) in sigs[k]]))
        classes[r] = cl
        print(f"[5] round {r}: {len(cl)} types: a={sum(c['cls']=='a' for c in cl)} b={sum(c['cls']=='b' for c in cl)} "
              f"c={sum(c['cls']=='c' for c in cl)}", flush=True)
    n_conflicts = sum(1 for r in classes for c in classes[r] if c.get("slot_conflict"))
    slots_used = Counter(h for (_, _, h) in occupied)
    engine_slots = {r: dict(used=slots_used[r] // NANC if slots_used[r] % NANC == 0 else slots_used[r] / NANC,
                            of=len(bulk)) for r in range(R)}

    # ------------------------------------------------------------ reconstruction
    rec = set()
    bad = 0
    def emit(sig_edges, t, h):
        nonlocal bad
        sup = []
        for (o, a, b) in sig_edges:
            key = (anc_at[sub(t, (a, b))], h + o)
            if key not in row_of:
                bad += 1; return
            sup.append(row_of[key])
        rec.add(tuple(sorted(sup)))
    for r in range(R):
        for k in (sorted(bulk) if r in bulk_rounds else types_r[r]):
            if k in bulk:
                for t in ALL: emit(sigs[k], t, r)
            elif (r, k) in embed:            # class b: host slot with masked edges
                B, u, tau, img = embed[(r, k)]
                for t in ALL: emit(sorted(img), add(t, u), r - tau)
            else:                            # class c: own edges
                for t in ALL: emit(sigs[k], t, r)
    sym = rec.symmetric_difference(set(cols))
    exact = (len(sym) == 0 and bad == 0)
    nnz_rec = sum(len(c) for c in rec)
    recon = dict(exact=exact, columns_rec=len(rec), columns_xdec=n, nnz_rec=nnz_rec, nnz_xdec=int(H.nnz),
                 mismatched_columns=len(sym), out_of_range_edges=bad)
    print("reconstruction:", "exact" if exact else f"MISMATCH {recon}", flush=True)
    check(exact, f"reconstruction mismatch: {recon}")

    # ------------------------------------------------------------ 6. memory
    mem = {}
    for w in (4, 6):
        mw = w + 3
        for prior_w, pname in ((w, "prior=w"), (mw, "prior=w+3")):
            per = {}
            for r in range(R):
                nt = len(types_r[r]); e = NANC * deg_by_round[r]["degree"]
                es = NANC * nt * (prior_w + 2 * mw); ms = e * w
                per[r] = dict(error_types=nt, edges=e, error_state_bits=es, message_bits=ms,
                              error_state_bram=math.ceil(es / BRAM_BITS), message_bram=math.ceil(ms / BRAM_BITS))
            tot_es = sum(p["error_state_bits"] for p in per.values()); tot_ms = sum(p["message_bits"] for p in per.values())
            nb = len(bulk); eb = NANC * deg_by_round[BULK_REF]["degree"]
            mem[f"w{w}_{pname}"] = dict(
                message_bits=w, marginal_bits=mw, prior_bits=prior_w, per_round=per,
                all_rounds=dict(error_state_bits=tot_es, message_bits=tot_ms,
                                error_state_bram=math.ceil(tot_es / BRAM_BITS), message_bram=math.ceil(tot_ms / BRAM_BITS)),
                bulk_round=dict(error_types=nb, edges=eb, error_state_bits=NANC * nb * (prior_w + 2 * mw), message_bits=eb * w))
    check(sum(NANC * deg_by_round[r]["degree"] for r in range(R)) == H.nnz, "edge count per round does not sum to nnz")

    res = dict(circuit=path, matrix=dict(rows=m, cols=n, nnz=int(H.nnz), rounds=R), convention=convention,
               group=dict(order=NANC, generators_nauty=len(A["gens"]), orders_g1_g2=[orders[g1], orders[g2]],
                          structure=[NA, NB], abelian=True, free_transitive_on_ancillas=True),
               basis=basis, check_type=CT, bulk_ref_round=BULK_REF, base_edge_table=base_table,
               error_types_per_home_round={r: [tname(k) for k in types_r[r]] for r in range(R)},
               bulk_rounds_same_type_set=bulk_rounds,
               **{f"base_edge_table_round{BULK_REF}": base_table,
                  f"check_tables_equal_round{BULK_REF}": {r: same_as_bulk[r] for r in range(R)}},
               check_tables_by_round={r: [dict(error_type=tname(t), round_offset=o, shift_a=a, shift_b=b)
                                          for (t, o, a, b) in rep_table[r]] for r in range(R) if not same_as_bulk[r]},
               check_degree=dict(max=int(deg.max()), **{f"histogram_all_{m}": deg_hist}, by_round=deg_by_round),
               error_types=type_info,
               rotator=dict(n_shifts_bulk=len(shifts_bulk), shifts_bulk=[list(s) for s in shifts_bulk],
                            n_shifts_all=len(shifts_all), shifts_all=[list(s) for s in shifts_all]),
               boundary=dict(classes={r: classes[r] for r in range(R)}, slot_conflicts=n_conflicts,
                             engine_slots_used_per_round=engine_slots),
               reconstruction=recon, memory=mem, seconds=round(time.time() - t0, 1))
    json.dump(res, open(os.path.join(outdir, "engine_params.json"), "w"), indent=1, default=int)
    print(f"DONE in {res['seconds']} s", flush=True)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "X")
