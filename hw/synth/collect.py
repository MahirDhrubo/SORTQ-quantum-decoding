"""Test 2c: collect post-route results of all runs (runs/<run>/result.txt, util_route*.rpt) -> results.json + tables.

Per run: resources of the `dut` instance (post-route hierarchical utilization), % of the device (available counts
from util_route.rpt), WNS, fmax = 1 / (period - WNS), critical path (start, end, logic levels, % routing delay).
engine_top: also the resources of every sub-instance one level below dut (per memory field, round_step, ctrl ...).
Usage: python collect.py [runs_dir] [out.json]
"""
import os, sys, re, json

COLS = {"Total LUTs": "lut", "LUTRAMs": "lutram", "SRLs": "srl", "FFs": "ff", "RAMB36": "ramb36",
        "RAMB18": "ramb18", "URAM": "uram", "DSP Blocks": "dsp"}


def hier(path):
    """rows of a hierarchical utilization report: list of (depth, instance, {col: value})."""
    rows, head = [], None
    for line in open(path):
        if not line.startswith("|"):
            continue
        cells = [c for c in line.rstrip("\n").split("|")[1:-1]]
        names = [c.strip() for c in cells]
        if names and names[0] == "Instance":
            head = names; continue
        if head is None or len(cells) != len(head):
            continue
        inst = cells[0]; depth = (len(inst) - len(inst.lstrip(" "))) // 2
        vals = {}
        for h, c in zip(head, names):
            if h in COLS:
                try: vals[COLS[h]] = float(c)
                except ValueError: pass
        rows.append((depth, names[0], names[1] if len(names) > 1 else "", vals))
    return rows


def available(path):
    """device totals from the flat utilization report."""
    av = {}
    want = {"CLB LUTs": "lut", "LUT as Memory": "lutram", "CLB Registers": "ff", "Block RAM Tile": "bram",
            "URAM": "uram", "DSPs": "dsp"}
    for line in open(path):
        if not line.startswith("|"): continue
        c = [x.strip() for x in line.split("|")[1:-1]]
        if len(c) >= 5 and c[0] in want and want[c[0]] not in av:
            try: av[want[c[0]]] = float(c[-2])
            except ValueError: pass
    return av


def result(path):
    r = {}
    for line in open(path):
        k, _, v = line.strip().partition(" ")
        r[k] = v
    return r


def main():
    runs = sys.argv[1] if len(sys.argv) > 1 else "runs"
    out = sys.argv[2] if len(sys.argv) > 2 else "results.json"
    res = {}
    for run in sorted(os.listdir(runs)):
        d = os.path.join(runs, run)
        if not os.path.exists(os.path.join(d, "result.txt")):
            res[run] = {"status": open(os.path.join(d, "status")).read().strip() if os.path.exists(os.path.join(d, "status")) else "?"}
            continue
        r = result(os.path.join(d, "result.txt"))
        per, wns = float(r["period"]), float(r["wns"])
        rows = hier(os.path.join(d, "util_route_hier.rpt"))
        av = available(os.path.join(d, "util_route.rpt"))
        dut = [x for x in rows if x[1] == "dut"]
        assert dut, f"{run}: no dut row"
        ddepth = dut[0][0]; i0 = rows.index(dut[0])
        sub = []
        for x in rows[i0 + 1:]:
            if x[0] <= ddepth: break
            if x[0] == ddepth + 1: sub.append({"inst": x[1], "module": x[2], **x[3]})
        u = dict(dut[0][3]); u["bram36_equiv"] = u.get("ramb36", 0) + u.get("ramb18", 0) / 2
        pct = {k: 100 * u[k2] / av[k] for k, k2 in (("lut", "lut"), ("ff", "ff"), ("lutram", "lutram"),
                                                       ("bram", "bram36_equiv"), ("dsp", "dsp")) if k in av and av[k]}
        dp, nd = float(r["datapath_delay"]), float(r["net_delay"])
        res[run] = dict(status="done", period=per, wns=wns, fmax_mhz=1000.0 / (per - wns), util=u, pct=pct,
                        available=av, start=r["start"], end=r["end"], logic_levels=int(r["logic_levels"]),
                        datapath_ns=dp, route_pct=100 * nd / dp if dp else 0.0, unrouted=int(r["route_status"]),
                        t_synth_s=int(r["t_synth_s"]), t_place_s=int(r["t_opt_place_s"]), t_route_s=int(r["t_route_s"]),
                        sub=sub)
    json.dump(res, open(out, "w"), indent=1)
    for run, x in res.items():
        if x["status"] != "done":
            print(f"{run:24s} {x['status']}"); continue
        u = x["util"]
        print(f"{run:24s} LUT {u.get('lut', 0):9.0f} FF {u.get('ff', 0):9.0f} LUTRAM {u.get('lutram', 0):7.0f} "
              f"BRAM36 {u['bram36_equiv']:6.1f} DSP {u.get('dsp', 0):3.0f}  WNS {x['wns']:7.3f} fmax {x['fmax_mhz']:6.1f} MHz "
              f"LL {x['logic_levels']:2d} route {x['route_pct']:4.1f}%")


if __name__ == "__main__":
    main()
