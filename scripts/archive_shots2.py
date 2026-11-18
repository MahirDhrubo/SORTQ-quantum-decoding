"""Archive part 2: the other shot sources of the paper, regenerated with the exact sampler calls and saved bit-packed
to archive/shots/ (same format as archive_shots.py), the 36-round / 72-code circuits to archive/circuits/,
and the closed-loop / dump shot lists to archive/shots/lists/; then verified by re-decoding.

A set is a list of segments (seed, [call sizes]); each segment is a fresh sampler:
  sampler = circuit.compile_detector_sampler(seed=seed); for n in calls: sampler.sample(n, separate_observables=True)
Sets:
  1d_p0.003_36r      36-round circuit, p = 0.003: 6 chunks x 5,000, chunk k = fresh sampler seed 1000 + k, one call
  1d_p0.002_36r      36-round circuit, p = 0.002: 20 chunks x 25,000, seed 2000 + k        (test1d_window.py chunked)
  2a_golden_seed20261113   12-round p = 0.003: one call of 2,000 (hw/golden/golden.py sample 2000 20261113)
  3f_72_p0.003_seed20261111   [[72,12,6]] memory_Z, d = 6, 6 rounds, p = 0.003: 25 calls of 4,000 (8 x 500,
                              test1f_layers.py run, seed 20261111)
Verification:
  1d     first 2,000 shots of chunk 0, all 4 settings (Windowed): per-window iterations, window_converged,
         logical_fail vs results/test1d/p{p}_{setting}.npz (merged in chunk order)
  2a     syn (z_rows) bit-equal to hw/golden/syndromes.npz; all 2,000 decoded with int4.2.8 sweep and rb13:
         iterations, success, decoding vs hw/golden/ref_int4.2.8_sweep.npz and hw/rb/golden/rb_relayvenv.npz
  lists  every 3d / 2f closed-loop shot decoded from the archived Test 1b sets: iterations vs the pick files'
         trace_iterations (3d: int4.2.8 sweep; 2f: rb13) and vs the traces
  72     first 2,000 shots, k1 and flood (test1f_layers.make): iterations, success, logical_fail vs acc72 traces
Usage: python archive_shots2.py make|verify [set ...]
"""
import sys, os, json, time, shutil
import numpy as np
from archive_shots import sha256, OUT, IDEAS

ROOT = os.path.join(IDEAS, "..")
C12 = IDEAS + "/circuits/bb_ibm/circuit=bicycle_bivariate_144_12_12_memory_Z,distance=12,rounds=12," \
             "error_rate={p},noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim"
C36 = IDEAS + "/circuits/bb_ibm_rounds/circuit=bicycle_bivariate_144_12_12_memory_Z,distance=12,rounds=36," \
              "error_rate={p},noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim"
C72 = IDEAS + "/circuits/bb_ibm/circuit=bicycle_bivariate_72_12_6_memory_Z,distance=6,rounds=6," \
             "error_rate={p},noise_model=uniform_circuit,basis=CX,A=x^3+y+y^2,B=y^3+x+x^2.stim"
SETS = {
    "1d_p0.003_36r": (C36.format(p="0.003"), [(1000 + k, [5000]) for k in range(6)]),
    "1d_p0.002_36r": (C36.format(p="0.002"), [(2000 + k, [25000]) for k in range(20)]),
    "2a_golden_seed20261113": (C12.format(p="0.003"), [(20261113, [2000])]),
    "3f_72_p0.003_seed20261111": (C72.format(p="0.003"), [(20261111, [4000] * 25)]),
}
LISTS = {"3d_picks_seed20261114.json": "hw/sim3d/picks.json", "3d_picks2_seed20261115.json": "hw/sim3d/picks2.json",
         "3d_shots_initial.txt": "hw/sim3d/shots.txt", "3d_shots_extended.txt": "hw/sim3d/shots2.txt",
         "3d_shots_no_backdoor.txt": "hw/sim3d/shots_init.txt", "2f_picks_rb_seed20261116.json": "hw/rb/sim/picks_rb.json",
         "2a_golden_picks.json": "hw/golden/picks.json"}
NV = 2000


def problem(path):
    from dem_tools import xdecoder_problem
    return xdecoder_problem(path)


def make(name):
    import stim
    path, segs = SETS[name]
    P = problem(path); c = P["circuit"]
    D, K = c.num_detectors, c.num_observables
    dp, op, t0 = [], [], time.time()
    for seed, calls in segs:
        s = c.compile_detector_sampler(seed=seed)
        for n in calls:
            det, obs = s.sample(n, separate_observables=True)
            dp.append(np.packbits(det.astype(np.uint8), axis=1, bitorder="little"))
            op.append(np.packbits(obs.astype(np.uint8), axis=1, bitorder="little"))
    shots = sum(sum(c_) for _, c_ in segs)
    meta = dict(set=name, shots=shots, segments=[dict(seed=s, calls=len(c_), call_size=c_[0]) for s, c_ in segs],
                circuit=os.path.relpath(path, ROOT), circuit_sha256=sha256(path), stim_version=stim.__version__,
                num_detectors=D, num_observables=K, bitorder="little", seconds=round(time.time() - t0, 1))
    np.savez_compressed(os.path.join(OUT, f"{name}.npz"), det_packed=np.concatenate(dp), obs_packed=np.concatenate(op),
                        num_detectors=D, num_observables=K, z_rows=np.asarray(P["z_rows"]), meta=json.dumps(meta))
    meta["file_sha256"] = sha256(os.path.join(OUT, f"{name}.npz"))
    json.dump(meta, open(os.path.join(OUT, f"{name}.json"), "w"), indent=1)
    cdir = os.path.join(IDEAS, "archive", "circuits"); os.makedirs(cdir, exist_ok=True)
    shutil.copy2(path, cdir)
    print(json.dumps(meta), flush=True)


def make_lists():
    d = os.path.join(OUT, "lists"); os.makedirs(d, exist_ok=True)
    for dst, src in LISTS.items():
        shutil.copy2(os.path.join(IDEAS, src), os.path.join(d, dst))
    # Test 3d p = 0.002 g8-check dump shot (prep_3d.dump2 rule) and the 2f rb golden picks (prep_rb.GOLDEN)
    PRE, LEG = 80, 60
    e = np.load(IDEAS + "/results/test1b/p0.002_int4.2.8_sweep.npz"); it, ok = e["iterations"], e["success"]
    i2 = int(np.flatnonzero(ok[:40000] & (it[:40000] > PRE) & (it[:40000] <= PRE + LEG))[0])
    extra = dict(
        test2a_dumps=dict(set="2a_golden_seed20261113", shots=[96, 106, 53],
                          files={"dump_p0.003_shot{0,1,2}": [96, 106, 53], "dump_legs10_shot0": 53}),
        test2f_dumps=dict(set="2a_golden_seed20261113",
                          files={"dump_rb_shot{0,1,2}": [96, 106, 53], "dump_rb_legs10_shot0": 53,
                                 "dump_rbx_shot{0,1}": [5, 141], "dump_rb_legs10b_shot0": 1855},
                          closed_loop_golden=[96, 106, 53, 5, 141, 1855]),
        test3d_dump2=dict(set="p0.002_seed20261111", shot=i2,
                          rule="first of the first 40,000 Test 1b p = 0.002 shots converging in leg 1 (int4.2.8 sweep)"),
        test3d=dict(sets=["p0.003_seed20261111", "p0.002_seed20261111"],
                    picks={"3d_picks_seed20261114.json": "initial 45 leg-0 + 5 legs-1-3 per p (numpy seed 20261114)",
                           "3d_picks2_seed20261115.json": "extended 450 + 50 per p (numpy seed 20261115, excluding the initial)"},
                    runs={"3d_shots_initial.txt": "first run (with backdoor), 103 shots",
                          "3d_shots_extended.txt": "extended run, 1,000 shots",
                          "3d_shots_no_backdoor.txt": "re-run without backdoor, 203 shots (3 golden + 200)"}),
        test2f=dict(sets=["p0.003_seed20261111", "p0.002_seed20261111"],
                    picks={"2f_picks_rb_seed20261116.json": "225 leg-0 + 25 legs-1-3 per p from the first 40,000 "
                                                           "Test 1g rb13 shots (numpy seed 20261116)"}))
    json.dump(extra, open(os.path.join(d, "index.json"), "w"), indent=1)
    print("lists written:", sorted(os.listdir(d)), "3d dump2 shot", i2)


def load(name, n=None):
    z = np.load(os.path.join(OUT, f"{name}.npz"))
    D, K = int(z["num_detectors"]), int(z["num_observables"])
    sl = slice(None) if n is None else (n if isinstance(n, (list, np.ndarray)) else slice(0, n))
    det = np.unpackbits(z["det_packed"][sl], axis=1, count=D, bitorder="little")
    obs = np.unpackbits(z["obs_packed"][sl], axis=1, count=K, bitorder="little")
    return det, obs, z["z_rows"]


def cmp(a, b, keys):
    return {k: int(np.sum(np.asarray(a[k]) != np.asarray(b[k]))) for k in keys}


def v1d(name, p):
    import test1d_window as T
    P = problem(SETS[name][0]); det, obs, z = load(name, NV)
    syn = det[:, z].astype(np.uint8)
    out = {}
    for s, (W, C) in T.SETTINGS.items():
        w = T.Windowed(P, W, C); E, it, ok = w.decode(syn)
        fail = T.logical_fail(E, w.O, obs.astype(np.int64))
        e = np.load(IDEAS + f"/results/test1d/p{p}_{s}.npz")
        out[s] = cmp(dict(iterations=it, window_converged=ok, logical_fail=fail),
                     dict(iterations=e["iterations"][:NV], window_converged=e["window_converged"][:NV],
                          logical_fail=e["logical_fail"][:NV]), ("iterations", "window_converged", "logical_fail"))
        out[s]["failures"] = int(fail.sum()); out[s]["windows"] = int(it.shape[1])
        print(name, s, out[s], flush=True)
    return out


def v2a(name):
    sys.path.insert(0, IDEAS + "/hw/golden")
    import test1b_quant as Q, test1h
    P = problem(SETS[name][0]); det, obs, z = load(name)
    syn = det[:, z].astype(np.uint8)
    out = dict(syn_bits_differ_vs_golden_syndromes=int(np.sum(syn != np.load(IDEAS + "/hw/golden/syndromes.npz")["syn"])))
    for lab, dec, ref in (("int4.2.8 sweep", Q.make(P["H"], P["priors"], P["layers"], "int4.2.8", "sweep"),
                           "/hw/golden/ref_int4.2.8_sweep.npz"),
                          ("rb13 int4.2.8", test1h.make(P["H"], P["priors"], P["layers"], "rb13_int4"),
                           "/hw/rb/golden/rb_relayvenv.npz")):
        r = dec.decode_detailed_batch(syn); e = np.load(IDEAS + ref)
        a = dict(iterations=[x.iterations for x in r], success=[x.success for x in r],
                 decoding=np.array([x.decoding for x in r], dtype=np.uint8))
        out[lab] = cmp(a, e, ("iterations", "success", "decoding")); out[lab]["reference"] = ref.lstrip("/")
        g = [96, 106, 53, 5, 141, 1855]
        out[lab]["iterations_of_golden_shots"] = {i: int(a["iterations"][i]) for i in g}
        print(name, lab, out[lab], flush=True)
    return out


def vlists():
    import test1b_quant as Q, test1h
    from archive_shots import CIRC
    out = {}
    jobs = [("3d_picks_seed20261114.json", "sweep"), ("3d_picks2_seed20261115.json", "sweep"),
            ("2f_picks_rb_seed20261116.json", "rb13")]
    for f, kind in jobs:
        J = json.load(open(os.path.join(OUT, "lists", f)))
        for p, r in J.items():
            idx = sorted(int(i) for i in r["trace_iterations"])
            P = problem(CIRC.format(p=p)); det, obs, z = load(f"p{p}_seed20261111", np.array(idx))
            syn = det[:, z].astype(np.uint8)
            dec = Q.make(P["H"], P["priors"], P["layers"], "int4.2.8", "sweep") if kind == "sweep" else \
                test1h.make(P["H"], P["priors"], P["layers"], "rb13_int4")
            it = np.array([x.iterations for x in dec.decode_detailed_batch(syn)])
            want = np.array([r["trace_iterations"][str(i)] for i in idx])
            tr = np.load(IDEAS + (f"/results/test1b/p{p}_int4.2.8_sweep.npz" if kind == "sweep"
                                  else f"/results/test1g/p{p}_rb13.npz"))["iterations"][idx]
            out[f"{f} p{p}"] = dict(shots=len(idx), iterations_differ_vs_pick_file=int(np.sum(it != want)),
                                    iterations_differ_vs_trace=int(np.sum(it != tr)))
            print(f, p, out[f"{f} p{p}"], flush=True)
    return out


def v72(name):
    import test1f_layers as F
    P = problem(SETS[name][0]); det, obs, z = load(name, NV)
    syn = det[:, z].astype(np.uint8); O = P["O"].astype(np.int64)
    out = {}
    for s in ("k1", "flood"):
        r = F.make(P["H"], P["priors"], P["layers"], s).decode_detailed_batch(syn)
        dec = np.array([x.decoding for x in r], dtype=np.int64)
        a = dict(iterations=[x.iterations for x in r], success=[x.success for x in r],
                 logical_fail=np.any((dec @ O.T) % 2 != obs, axis=1))
        e = np.load(IDEAS + f"/results/test3f/acc72/p0.003_{s}.npz")
        out[s] = cmp(a, {k: e[k][:NV] for k in a}, tuple(a)); out[s]["failures"] = int(a["logical_fail"].sum())
        print(name, s, out[s], flush=True)
    return out


if __name__ == "__main__":
    mode, names = sys.argv[1], sys.argv[2:]
    if mode == "make":
        for n in (names or list(SETS)):
            make(n)
        make_lists()
    elif mode == "verify":
        V = {}
        todo = names or ["1d_p0.003_36r", "1d_p0.002_36r", "2a_golden_seed20261113", "lists", "3f_72_p0.003_seed20261111"]
        for n in todo:
            V[n] = (v1d(n, n.split("_")[1][1:]) if n.startswith("1d") else v2a(n) if n.startswith("2a")
                    else vlists() if n == "lists" else v72(n))
        json.dump(V, open(os.path.join(OUT, "verify2.json"), "w"), indent=1)

        flat = []

        def walk(x, key=""):
            if isinstance(x, dict):
                for k, v in x.items():
                    if k in ("failures", "windows", "shots", "reference", "iterations_of_golden_shots"):
                        continue
                    walk(v, k)
            else:
                flat.append((key, x))
        walk(V)
        print("ALL MATCH" if all(v == 0 for _, v in flat) else "MISMATCH", len(flat), "comparisons")
