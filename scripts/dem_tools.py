"""Shared helpers for the Idea 1 tests: detector labels from the circuit, DEM columns, X-decoder projection.

The labelling and projection are the same as in idea1_symmetry.py (Test 1), copied here so the Test 2 environment
does not need pynauty.
"""
from collections import Counter, defaultdict
import numpy as np
import scipy.sparse as sp
import stim


def label_detectors(circ):
    flat = circ.flattened()
    meas, det_recs = [], []
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
    final = {i for i, (_, _, noisy) in enumerate(meas) if not noisy}
    final_qubits = {meas[i][0] for i in final}
    occ, cnt = {}, Counter()
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
        labels.append(dict(anc=q, typ=meas[last][1], rnd=occ[last] + (1 if uses_final else 0)))
    return labels


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


def xdecoder_problem(circuit_path):
    """X decoder (Z-type detectors), unchanged behaviour: decoder_problem(circuit_path, "Z")."""
    return decoder_problem(circuit_path, "Z")


def decoder_problem(circuit_path, det_type="Z"):
    """Decoder projection onto the detectors of one type (Test 2e generalisation of the Test 1 X-decoder projection:
    det_type "Z" = X decoder (memory_Z circuits), det_type "X" = Z decoder (memory_X circuits)).
    X-decoder projection (user-approved definition, Test 1):
    Z-type detectors only; errors flipping none dropped; identical detector sets merged, p combined as parity of
    independent events. Asserts merged groups agree on observables.
    Returns dict with H (csr, rows = Z detectors in original order), priors, O (n_obs x cols), z_rows (original
    detector ids), layers (round per row), circuit."""
    circ = stim.Circuit.from_file(circuit_path)
    lab = label_detectors(circ)
    cols = dem_columns(circ.detector_error_model(decompose_errors=False))
    z_rows = [d for d in range(len(lab)) if lab[d]["typ"] == det_type]
    pos = {d: i for i, d in enumerate(z_rows)}
    groups = defaultdict(list)
    for dets, p, obs in cols:
        s = tuple(pos[d] for d in dets if d in pos)
        if s:
            groups[s].append((p, obs))
    sups = sorted(groups)
    priors = np.empty(len(sups))
    obsv = np.empty(len(sups), dtype=np.int64)
    for j, s in enumerate(sups):
        p = 0.0
        for q, _ in groups[s]:
            p = p * (1 - q) + q * (1 - p)
        ob = {o for _, o in groups[s]}
        assert len(ob) == 1, "merged columns disagree on observables"
        priors[j] = p
        obsv[j] = ob.pop()
    r, c = [], []
    for j, s in enumerate(sups):
        r += list(s); c += [j] * len(s)
    H = sp.csr_matrix((np.ones(len(r), dtype=np.uint8), (r, c)), shape=(len(z_rows), len(sups)))
    nobs = circ.num_observables
    O = np.array([[(o >> k) & 1 for o in obsv] for k in range(nobs)], dtype=np.uint8)
    layers = np.array([lab[d]["rnd"] for d in z_rows], dtype=np.int64)
    return dict(H=H, priors=priors, O=O, z_rows=np.array(z_rows), layers=layers, circuit=circ)
