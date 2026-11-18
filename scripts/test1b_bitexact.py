"""Test 1b: bit-exactness of quant=none. 'save' writes reference outputs from the current build; 'compare' decodes
the same shots with the rebuilt package (quant=None / 'none') and reports any difference.
F32 and F64, flooding (no layers) and sweep (13 layers), Test 2b parameters, p = 0.003, seed 20261111.
Usage: python test1b_bitexact.py save|compare <circuit> <npz> <nshots>"""
import sys, numpy as np, relay_bp
from dem_tools import xdecoder_problem
mode, path, npz, N = sys.argv[1], sys.argv[2], sys.argv[3], int(sys.argv[4])
P = xdecoder_problem(path)
H, pri, layers = P["H"], P["priors"], P["layers"]
det, _ = P["circuit"].compile_detector_sampler(seed=20261111).sample(N, separate_observables=True)
syn = det[:, P["z_rows"]].astype(np.uint8)
args = dict(alpha=None, gamma0=0.125, pre_iter=80, num_sets=300, set_max_iter=60,
            gamma_dist_interval=(-0.22628432386414646, 0.6216020925981884), stop_nconv=1, seed=0)
out = {}
for cls in ("F32", "F64"):
    for sched in ("flood", "sweep"):
        kw = dict(args)
        if sched == "sweep": kw["check_layers"] = [int(x) for x in layers]
        if mode == "compare": kw["quant"] = "none"
        dec = getattr(relay_bp, f"RelayDecoder{cls}")(H, error_priors=pri, **kw)
        res = dec.decode_detailed_batch(syn)
        k = f"{cls}_{sched}"
        out[k + "_post"] = np.array([r.posterior_ratios for r in res])
        out[k + "_dec"] = np.array([r.decoding for r in res])
        out[k + "_it"] = np.array([r.iterations for r in res])
if mode == "save":
    np.savez_compressed(npz, **out); print("saved", npz, list(out)[:3], "...")
else:
    ref = np.load(npz); ok = True
    for k in out:
        same = np.array_equal(out[k], ref[k]); ok &= same
        print(f"{k}: bit-identical {same}")
    print("ALL BIT-IDENTICAL" if ok else "DIFFERENCES FOUND")
