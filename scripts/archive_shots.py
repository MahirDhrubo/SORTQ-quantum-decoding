"""Archive the shot sets of the paper: regenerate the samples with the exact sampler calls of the runs and save
detector + observable bits, bit-packed, to archive/shots/<set>.npz; then verify by decoding the first 2,000
shots of each saved set and comparing iterations / success / logical failure with the existing traces.

Sampler calls (as in test1b_quant.py / test1f_layers.py / test1g_order.py / test1h.py run):
  sampler = circuit.compile_detector_sampler(seed=SEED)
  repeat: det, obs = sampler.sample(min(batch * workers, shots - done), separate_observables=True)
stim's output depends on the call sizes, so batch x workers is part of the shot set's definition.

Saved arrays (npz, compressed): det_packed [shots, ceil(D/8)] uint8 and obs_packed [shots, ceil(K/8)] uint8
(np.packbits(axis=1, bitorder="little"): bit j of a row = detector / observable j), num_detectors, num_observables,
z_rows (the detector indices the X decoder reads, dem_tools.xdecoder_problem), plus metadata (seed, shots, batch,
workers, calls, circuit file + sha256, stim version).
Usage: python archive_shots.py make|verify [set ...]
"""
import sys, os, json, hashlib, time
import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
IDEAS = os.path.join(HERE, "..")
OUT = os.path.join(IDEAS, "archive", "shots")
CIRC = os.path.join(IDEAS, "circuits", "bb_ibm",
                    "circuit=bicycle_bivariate_144_12_12_memory_Z,distance=12,rounds=12,error_rate={p},"
                    "noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim")
R = os.path.join(IDEAS, "results")
# set name -> (p, seed, shots, batch, workers, traces to verify against: (decoder config, trace file))
SETS = {
    "p0.003_seed20261111": ("0.003", 20261111, 168000, 500, 8, [
        ("1b float flood", R + "/test1b/p0.003_float_flood.npz"),
        ("1b int4.2.8 sweep", R + "/test1b/p0.003_int4.2.8_sweep.npz"),
        ("1h rb13_int4", R + "/test1g/p0.003_rb13.npz")]),
    "p0.002_seed20261111": ("0.002", 20261111, 600000, 1000, 8, [
        ("1b float flood", R + "/test1b/p0.002_float_flood.npz"),
        ("1b int4.2.8 sweep", R + "/test1b/p0.002_int4.2.8_sweep.npz"),
        ("1h rb13_int4", R + "/test1g/p0.002_rb13.npz")]),
    "p0.001_seed20261111": ("0.001", 20261111, 600000, 1000, 8, [
        ("1b float flood", R + "/test1b/p0.001_float_flood.npz"),
        ("1b int4.2.8 sweep", R + "/test1b/p0.001_int4.2.8_sweep.npz"),
        ("1h rb13_int4", R + "/test1g/p001/p0.001_rb13.npz")]),
    "p0.003_seed20261120": ("0.003", 20261120, 168000, 500, 8, [
        ("1h flood_float", R + "/test1h/step2/p0.003_flood_float.npz"),
        ("1h rb13_int4", R + "/test1h/step2/p0.003_rb13_int4.npz")]),
}
NVERIFY = 2000


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def make(name):
    import stim
    from dem_tools import xdecoder_problem
    p, seed, shots, batch, workers, _ = SETS[name]
    path = CIRC.format(p=p)
    P = xdecoder_problem(path)
    c = P["circuit"]
    sampler = c.compile_detector_sampler(seed=seed)
    D, K = c.num_detectors, c.num_observables
    dp, op, calls, done, t0 = [], [], [], 0, time.time()
    while done < shots:
        n = min(batch * workers, shots - done)
        det, obs = sampler.sample(n, separate_observables=True)
        dp.append(np.packbits(det.astype(np.uint8), axis=1, bitorder="little"))
        op.append(np.packbits(obs.astype(np.uint8), axis=1, bitorder="little"))
        calls.append(n); done += n
    os.makedirs(OUT, exist_ok=True)
    meta = dict(set=name, p=p, seed=seed, shots=shots, batch=batch, workers=workers, sample_call_size=batch * workers,
                calls=len(calls), last_call=calls[-1], circuit=os.path.relpath(path, os.path.join(IDEAS, "..")),
                circuit_sha256=sha256(path), stim_version=stim.__version__, num_detectors=D, num_observables=K,
                bitorder="little", seconds=round(time.time() - t0, 1))
    np.savez_compressed(os.path.join(OUT, f"{name}.npz"), det_packed=np.concatenate(dp), obs_packed=np.concatenate(op),
                        num_detectors=D, num_observables=K, z_rows=np.asarray(P["z_rows"]), meta=json.dumps(meta))
    meta["file_sha256"] = sha256(os.path.join(OUT, f"{name}.npz"))
    json.dump(meta, open(os.path.join(OUT, f"{name}.json"), "w"), indent=1)
    print(json.dumps(meta), flush=True)


def load(name, n=None):
    z = np.load(os.path.join(OUT, f"{name}.npz"))
    D, K = int(z["num_detectors"]), int(z["num_observables"])
    det = np.unpackbits(z["det_packed"][:n], axis=1, count=D, bitorder="little")
    obs = np.unpackbits(z["obs_packed"][:n], axis=1, count=K, bitorder="little")
    return det, obs, z["z_rows"]


def decoder(label, H, pri, layers):
    if label.startswith("1b "):
        import test1b_quant as Q
        fmt, sched = label[3:].rsplit(" ", 1)
        return Q.make(H, pri, layers, fmt, sched)
    import test1h
    return test1h.make(H, pri, layers, label[3:])


def verify(name):
    from dem_tools import xdecoder_problem
    p, seed, shots, batch, workers, refs = SETS[name]
    P = xdecoder_problem(CIRC.format(p=p))
    det, obs, z = load(name, NVERIFY)
    assert np.array_equal(z, np.asarray(P["z_rows"]))
    syn = det[:, z].astype(np.uint8); O = P["O"].astype(np.int64)
    res = {}
    for label, f in refs:
        r = decoder(label, P["H"], P["priors"], P["layers"]).decode_detailed_batch(syn)
        it = np.array([x.iterations for x in r]); ok = np.array([x.success for x in r])
        dec = np.array([x.decoding for x in r], dtype=np.int64)
        fail = np.any((dec @ O.T) % 2 != obs, axis=1)
        e = np.load(f)
        res[label] = dict(trace=os.path.relpath(f, IDEAS), shots=NVERIFY,
                          iterations_differ=int(np.sum(it != e["iterations"][:NVERIFY])),
                          success_differ=int(np.sum(ok != e["success"][:NVERIFY])),
                          logical_fail_differ=int(np.sum(fail != e["logical_fail"][:NVERIFY])),
                          failures=int(fail.sum()), trace_failures=int(e["logical_fail"][:NVERIFY].sum()))
        print(name, label, res[label], flush=True)
    return res


if __name__ == "__main__":
    mode, names = sys.argv[1], (sys.argv[2:] or list(SETS))
    if mode == "make":
        for n in names:
            make(n)
    elif mode == "verify":
        out = {n: verify(n) for n in names}
        json.dump(out, open(os.path.join(OUT, "verify.json"), "w"), indent=1)
        print("ALL MATCH" if all(x[k] == 0 for r in out.values() for x in r.values()
                                 for k in ("iterations_differ", "success_differ", "logical_fail_differ"))
              else "MISMATCH")
