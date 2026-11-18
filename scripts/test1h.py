"""Idea 1, Test 1h: accuracy of the red-black order at p = 0.003 (software only).

Decoder as Test 1g (relay_bp.RelayDecoderF32; alpha = 1, S = 1, pre_iter 80, 300 legs x 60, cap 18,080, gamma
generator seed 0, 1/8 gamma grid g8 = floor(8 gamma + 1/2) in int4.2.8), 12-round gross-code X decoder, except the
settings each config changes:
  config name           quant      order       gamma0   interval
  rb13_float            none       rb13        0.125    (-0.226, 0.622)    step 1
  rb13_int4             int4.2.8   rb13        0.125    (-0.226, 0.622)    = Test 1g rb13 (baseline / identity check)
  flood_float           none       flood       0.125    (-0.226, 0.622)    = Test 1b float flood (step 2 reference)
  rb13_int4_g0.0625     int4.2.8   rb13        0.0625   original
  rb13_int4_g0.25       int4.2.8   rb13        0.25     original
  rb13_int4_i0.15_0.5   int4.2.8   rb13        0.125    (-0.15, 0.5)
  rb13_int4_i0.3_0.7    int4.2.8   rb13        0.125    (-0.3, 0.7)
  odd13_int4            int4.2.8   odd-first   0.125    original           order 1, 3, ..., 11, 0, 2, ..., 12
Order = layer ids (relay_bp processes layers in increasing id): id of a round-r check = position of r in the order.
Modes:
  run <circuit> <tag> <shots> <workers> <batch> <seed> <outdir> <config,config,...>
      traces <outdir>/<tag>_<config>.npz (Test 1b format + dec_crc), <tag>.json
Shots: sampler seed <seed>, batch x workers as given (Test 1b shots = seed 20261111, 8 x 500 at p = 0.003,
8 x 1000 at p = 0.002).
"""
import sys, os, json, time, zlib
import numpy as np
from test1b_quant import PRE, LEG_IT, CAP, LEGS, INTERVAL, first_leg

ORDERS = {"rb13": [0, 2, 4, 6, 8, 10, 12, 1, 3, 5, 7, 9, 11], "odd13": [1, 3, 5, 7, 9, 11, 0, 2, 4, 6, 8, 10, 12]}
CONF = {
    "rb13_float": ("none", "rb13", 0.125, INTERVAL),
    "rb13_int4": ("int4.2.8", "rb13", 0.125, INTERVAL),
    "flood_float": ("none", "flood", 0.125, INTERVAL),
    "rb13_int4_g0.0625": ("int4.2.8", "rb13", 0.0625, INTERVAL),
    "rb13_int4_g0.25": ("int4.2.8", "rb13", 0.25, INTERVAL),
    "rb13_int4_i0.15_0.5": ("int4.2.8", "rb13", 0.125, (-0.15, 0.5)),
    "rb13_int4_i0.3_0.7": ("int4.2.8", "rb13", 0.125, (-0.3, 0.7)),
    "odd13_int4": ("int4.2.8", "odd13", 0.125, INTERVAL),
}
_G = {}


def make(H, pri, layers, name):
    import relay_bp
    quant, order, g0, iv = CONF[name]
    kw = dict(alpha=None, gamma0=g0, pre_iter=PRE, num_sets=LEGS, set_max_iter=LEG_IT, gamma_dist_interval=tuple(iv),
              stop_nconv=1, seed=0, quant=quant)
    if order != "flood":
        kw["check_layers"] = [ORDERS[order].index(int(r)) for r in layers]
    return relay_bp.RelayDecoderF32(H, error_priors=pri, **kw)


def init(H, pri, layers, names):
    for n in names:
        _G[n] = make(H, pri, layers, n)


def work(syn):
    out = {}
    for n, dec in _G.items():
        t0 = time.time()
        r = dec.decode_detailed_batch(syn)
        d = np.array([x.decoding for x in r], dtype=np.uint8)
        out[n] = dict(dec=d, it=np.array([x.iterations for x in r], dtype=np.int32),
                      ok=np.array([x.success for x in r]),
                      crc=np.array([zlib.crc32(np.packbits(row).tobytes()) for row in d], dtype=np.uint32),
                      sec=time.time() - t0)
    return out


def run(path, tag, shots, workers, batch, seed, outdir, names):
    from multiprocessing import Pool
    from dem_tools import xdecoder_problem
    os.makedirs(outdir, exist_ok=True)
    P = xdecoder_problem(path)
    H, pri, O, layers = P["H"], P["priors"], P["O"], P["layers"]
    sampler = P["circuit"].compile_detector_sampler(seed=seed)
    T = {n: dict(it=[], ok=[], fail=[], crc=[]) for n in names}
    SEC = {n: 0.0 for n in names}
    t_start, done, nb = time.time(), 0, 0

    def save():
        for n in names:
            it = np.concatenate(T[n]["it"]); ok = np.concatenate(T[n]["ok"])
            np.savez_compressed(os.path.join(outdir, f"{tag}_{n}.npz"), iterations=it, success=ok,
                                first_leg=first_leg(it, ok), hit_cap=(it >= CAP) & ~ok,
                                logical_fail=np.concatenate(T[n]["fail"]), dec_crc=np.concatenate(T[n]["crc"]))
        summ = dict(tag=tag, seed=seed, shots=done, workers=workers, batch=batch, wall_s=round(time.time() - t_start, 1),
                    configs={n: dict(zip(("quant", "order", "gamma0", "interval"), CONF[n])) for n in names},
                    fails={n: int(np.concatenate(T[n]["fail"]).sum()) for n in names},
                    cpu_s_per_shot={n: SEC[n] / max(done, 1) for n in names})
        json.dump(summ, open(os.path.join(outdir, f"{tag}.json"), "w"), indent=1)
        return summ

    with Pool(workers, initializer=init, initargs=(H, pri, layers, names)) as pool:
        while done < shots:
            n = min(batch * workers, shots - done)
            det, obs = sampler.sample(n, separate_observables=True)
            syn = det[:, P["z_rows"]].astype(np.uint8)
            parts = np.array_split(np.arange(n), workers)
            for res, idx in zip(pool.map(work, [syn[i] for i in parts]), parts):
                ob = obs[idx].astype(np.int64)
                for c in names:
                    r = res[c]
                    pred = (r["dec"].astype(np.int64) @ O.T.astype(np.int64)) % 2
                    T[c]["it"].append(r["it"]); T[c]["ok"].append(r["ok"]); T[c]["crc"].append(r["crc"])
                    T[c]["fail"].append(np.any(pred != ob, axis=1))
                    SEC[c] += r["sec"]
            done += n; nb += 1
            if nb % 5 == 0 or done >= shots:
                summ = save()
                print(json.dumps(dict(shots=done, wall_s=summ["wall_s"], fails=summ["fails"])), flush=True)
    print("DONE", tag, flush=True)


if __name__ == "__main__":
    a = sys.argv
    if a[1] == "run":
        run(a[2], a[3], int(a[4]), int(a[5]), int(a[6]), int(a[7]), a[8], a[9].split(","))
