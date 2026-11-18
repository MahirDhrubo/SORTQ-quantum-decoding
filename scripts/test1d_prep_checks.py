"""Test 1d prep, Steps 1-2: circuit counts and the Test 1c template on 12/24/36-round circuits.

Step 1: detectors, DEM errors, Z-detector count == 72 (R + 1), noiseless circuit gives all-zero detectors and
observables (200 shots), DEM builds (stim checks determinism).
Step 2: xdec built with dem_tools.xdecoder_problem (Test 1c pipeline). H is rebuilt from the Test 1c template
(engine_params.json: coordinates, 10 error types as (offset, shift) sets) with per-round type masks
  round 0: T00-T08 (no T09); rounds 1..R-1: all 10; round R (final): T01, T03, T09
and compared with xdec column by column. Also the measured type set per home round.

Usage: python test1d_prep_checks.py <engine_params.json> <out.json> <circuit> [<circuit> ...]
"""
import sys, json
from collections import defaultdict
import numpy as np
import stim
from dem_tools import xdecoder_problem, label_detectors

NA, NB = 12, 6
ALL = [(a, b) for a in range(NA) for b in range(NB)]
sub = lambda u, v: ((u[0] - v[0]) % NA, (u[1] - v[1]) % NB)


def main(tpl_path, out_path, circuits):
    T = json.load(open(tpl_path))
    anc_at = {tuple(int(x) for x in k.split(",")): v for k, v in T["convention"]["ancilla_of_coordinate"].items()}
    coord = {v: k for k, v in anc_at.items()}
    sig = {t["type"]: tuple(sorted((e["round_offset"], e["shift_a"], e["shift_b"]) for e in t["edges"]))
           for t in T["error_types"]}
    sig2type = {s: k for k, s in sig.items()}
    res = {}
    for path in circuits:
        circ = stim.Circuit.from_file(path)
        lab = label_detectors(circ)
        R = max(l["rnd"] for l in lab)          # final (data-measurement) round index
        nz = sum(1 for l in lab if l["typ"] == "Z")
        dem = circ.detector_error_model(decompose_errors=False)
        n_err = sum(1 for i in dem.flattened() if i.type == "error")
        det, obs = circ.without_noise().compile_detector_sampler().sample(200, separate_observables=True)
        r = dict(rounds_in_name=int(path.split("rounds=")[1].split(",")[0]), detectors=circ.num_detectors,
                 observables=circ.num_observables, dem_errors=n_err, z_detectors=nz, final_round_index=R,
                 z_detectors_eq_72_R_plus_1=nz == 72 * (R + 1),
                 noiseless_all_zero=bool(not det.any() and not obs.any()))
        # Step 2
        P = xdecoder_problem(path)
        H = P["H"].tocsc(); m, n = H.shape
        anc = np.array([lab[d]["anc"] for d in P["z_rows"]]); rnd = np.asarray(P["layers"])
        row_of = {(int(anc[i]), int(rnd[i])): i for i in range(m)}
        cols = {tuple(sorted(H.indices[H.indptr[j]:H.indptr[j + 1]].tolist())) for j in range(n)}
        mask = {0: [f"T{k:02d}" for k in range(9)], R: ["T01", "T03", "T09"]}
        rec, bad = set(), 0
        for h in range(R + 1):
            for ty in mask.get(h, [f"T{k:02d}" for k in range(10)]):
                for t in ALL:
                    sup = []
                    for (o, a, b) in sig[ty]:
                        key = (anc_at[sub(t, (a, b))], h + o)
                        if key not in row_of:
                            bad += 1; sup = None; break
                        sup.append(row_of[key])
                    if sup is not None:
                        rec.add(tuple(sorted(sup)))
        mism = len(rec ^ cols)
        # measured type per column (independent of the masks)
        per_round = defaultdict(set); unknown = 0
        for c in cols:
            h = min(int(rnd[i]) for i in c)
            xs = [coord[int(anc[i])] for i in c]
            best = min(tuple(sorted((int(rnd[i]) - h,) + sub(t, x) for i, x in zip(c, xs))) for t in ALL)
            if best in sig2type:
                per_round[h].add(sig2type[best])
            else:
                unknown += 1
        bulk = [h for h in range(R + 1) if per_round[h] == set(sig)]
        r.update(xdec_shape=[m, n], xdec_nnz=int(H.nnz), reconstruction="exact" if mism == 0 and bad == 0 else
                 f"MISMATCH: {mism} columns differ, {bad} edges out of range",
                 columns_of_unknown_type=unknown, bulk_rounds=f"{min(bulk)}..{max(bulk)}" if bulk else "none",
                 bulk_rounds_contiguous=bulk == list(range(min(bulk), max(bulk) + 1)) if bulk else False,
                 round0_types=sorted(per_round[0]), final_round_types=sorted(per_round[R]))
        res[path.split("/")[-1]] = r
        print(json.dumps(r), flush=True)
    json.dump(res, open(out_path, "w"), indent=1)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], sys.argv[3:])
