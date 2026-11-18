"""Test 2a helper: label the rows and columns of an xdec parity-check matrix in Test 1c engine coordinates.

rows:    (x, r)  check position x (index a * 6 + b, from engine_params 'convention.ancilla_of_coordinate'), round r
columns: (type, position p, home round h)  — Test 1c rule: h = earliest round; p = the position whose edge
         signature {(r_i - h, x_i' = position of check i minus p)} ... i.e. sorted((r_i - h, p - x_i)) is
         lexicographically smallest; type = the engine_params error type with that signature.
edge_base(row, col) -> base edge k (index in engine_params 'base_edge_table_round5').
Everything is asserted: every H edge maps to exactly one base edge, so H is reconstructed exactly.

Usage (writes the round-wiring expectations from H, independent of gen_round_wiring.py):
  python labels.py <circuit.stim> <engine_params.json> <out_expected.txt> [round]
"""
import sys, os
import numpy as np

NA, NB = 12, 6
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "..", "scripts"))


def sub(u, v): return ((u[0] - v[0]) % NA, (u[1] - v[1]) % NB)


def labels(P, ep):
    global NA, NB
    NA, NB = ep["group"].get("structure", [12, 6])          # Test 2e: sizes from engine_params
    from dem_tools import label_detectors
    H = P["H"].tocsr(); Hc = H.tocsc(); m, n = H.shape
    lab = label_detectors(P["circuit"])
    anc = [lab[d]["anc"] for d in P["z_rows"]]
    rnd = np.asarray(P["layers"]).astype(int)
    coord = {int(v): tuple(map(int, k.split(","))) for k, v in ep["convention"]["ancilla_of_coordinate"].items()}
    xr = [coord[int(a)] for a in anc]
    tsig = {tuple(sorted((e["round_offset"], e["shift_a"], e["shift_b"]) for e in t["edges"])): t["type"]
            for t in ep["error_types"]}
    tnames = sorted(t["type"] for t in ep["error_types"])
    ALL = [(a, b) for a in range(NA) for b in range(NB)]
    col_t, col_p, col_h = np.zeros(n, int), np.zeros(n, int), np.zeros(n, int)
    for j in range(n):
        rows = Hc.indices[Hc.indptr[j]:Hc.indptr[j + 1]]
        h = int(rnd[rows].min())
        best = min((tuple(sorted((int(rnd[i]) - h,) + sub(t, xr[i]) for i in rows)), t) for t in ALL)
        assert best[0] in tsig, f"column {j}: signature {best[0]} is not an engine_params type"
        col_t[j] = tnames.index(tsig[best[0]]); col_p[j] = best[1][0] * NB + best[1][1]; col_h[j] = h
    be = ep.get("base_edge_table", ep.get("base_edge_table_round5"))
    bidx = {(tnames.index(e["error_type"]), e["round_offset"], e["shift_a"], e["shift_b"]): k for k, e in enumerate(be)}
    row_x = np.array([a * NB + b for a, b in xr]); row_r = rnd
    def edge_base(i, j):
        p = (col_p[j] // NB, col_p[j] % NB)
        s = sub(p, xr[i])
        return bidx[(int(col_t[j]), int(row_r[i] - col_h[j]), s[0], s[1])]
    nnz = 0
    for i in range(m):
        ks = [edge_base(i, j) for j in H.indices[H.indptr[i]:H.indptr[i + 1]]]
        assert len(set(ks)) == len(ks), f"row {i}: two edges on one base edge"
        nnz += len(ks)
    assert nnz == H.nnz
    return dict(row_x=row_x, row_r=row_r, col_t=col_t, col_p=col_p, col_h=col_h, edge_base=edge_base, tnames=tnames)


def main():
    import json
    from dem_tools import xdecoder_problem
    circ, epf, out = sys.argv[1:4]
    r0 = int(sys.argv[4]) if len(sys.argv) > 4 else 5
    P = xdecoder_problem(circ); ep = json.load(open(epf)); L = labels(P, ep)
    be = ep.get("base_edge_table", ep.get("base_edge_table_round5"))
    idx = {}; c0 = c1 = 0
    for k, e in enumerate(be):
        if e["round_offset"] == 0: idx[k] = c0; c0 += 1
        else: idx[k] = c1; c1 += 1
    H = P["H"].tocsr(); lines = []
    for i in np.where(L["row_r"] == r0)[0]:
        for j in H.indices[H.indptr[i]:H.indptr[i + 1]]:
            k = L["edge_base"](i, j)
            lines.append((int(L["row_x"][i]), k, be[k]["round_offset"], idx[k], int(L["col_p"][j])))
    assert len(lines) == 72 * 35 and len({(a, b) for a, b, *_ in lines}) == 72 * 35
    open(out, "w").write("".join(f"{x} {k} {o} {i} {p}\n" for x, k, o, i, p in sorted(lines)))
    print(f"labels: H reconstructed exactly from the engine_params types ({H.nnz} edges); round {r0}: "
          f"{len(lines)} edges written to {out}")


if __name__ == "__main__":
    main()
