"""Make R-round versions of the Relay-BP data-set circuit bicycle_bivariate_144_12_12_memory_Z (bb_ibm, d = 12,
uniform_circuit, basis CX) from its 12-round file, without changing anything except the number of rounds.

The 12-round file is unrolled (no REPEAT). Gate section: [prefix up to round 0's Z-ancilla measurement]
[round block] x 11 [tail: last X-ancilla and final data measurements]. Round blocks 1-10 are identical text;
block 11 (the last round) is kept as the last block. Detector section (all DETECTOR lines are at the end, with
rec[-k] offsets): each line is re-expressed as (coordinate, targets as (qubit, measurement kind, occurrence or
final)) and grouped by its round (largest ancilla occurrence). The script checks that rounds 1..10 have the same
pattern up to a constant shift of occurrence and coordinate, then writes R rounds as:
  prefix + block x (R - 2) + last block + tail + [round 0 detectors] + [bulk pattern for rounds 1..R-2]
  + [last-round detectors, shifted] + [final detectors, shifted] + [observables], with rec offsets recomputed for the new measurement count.
Validation: R = 12 must reproduce the original file byte for byte (asserted).

Usage: python make_bb_ibm_rounds.py <src_12round.stim> <outdir> <R> [<R> ...]
"""
import sys, os, re
from collections import Counter

MEAS = ("M", "MX", "MR", "MRX")


def measurements(lines):
    meas = []
    for l in lines:
        head = l.split(" ")[0]
        if head.split("(")[0] in MEAS:
            noisy = "(" in head
            meas += [(int(q), head.split("(")[0], noisy) for q in l.split(" ")[1:]]
    occ, out = Counter(), []
    for q, name, noisy in meas:
        out.append((q, name, occ[q] if noisy else "F"))
        if noisy:
            occ[q] += 1
    return out


def parse_detectors(sec, mo):
    N = len(mo)
    items = []
    for l in sec:
        head = l.split(" ")[0]
        kind = head.split("(")[0]
        if kind == "TICK":
            items.append(("TICK",)); continue
        args = re.findall(r"\((.*?)\)", head)
        tg = [mo[N + int(r)] for r in re.findall(r"rec\[(-\d+)\]", l)]
        items.append((kind, args[0] if args else None, tuple(tg)))
    return items


def round_of(item):
    occs = [t[2] for t in item[2] if t[2] != "F"]
    return max(occs) if occs else None


def split_rounds(items):
    """Group items into segments by round; TICK lines attach to the preceding segment. Observables separate."""
    segs, cur, cur_r = [], [], None
    for it in items:
        if it[0] == "OBSERVABLE_INCLUDE":
            break
        if it[0] == "DETECTOR":
            r = ("final", round_of(it)) if any(t[2] == "F" for t in it[2]) else round_of(it)
            if cur and r != cur_r:
                segs.append((cur_r, cur)); cur = []
            cur_r = r
        cur.append(it)
    segs.append((cur_r, cur))
    obs = [it for it in items if it[0] == "OBSERVABLE_INCLUDE"]
    return segs, obs


def shift(seg, dr, dc):
    out = []
    for it in seg:
        if it[0] == "TICK":
            out.append(it); continue
        tg = tuple((q, n, o if o == "F" else o + dr) for q, n, o in it[2])
        out.append((it[0], str(int(it[1]) + dc), tg))
    return out


def render(items, mo_new):
    pos = {m: i for i, m in enumerate(mo_new)}
    N = len(mo_new)
    lines = []
    for it in items:
        if it[0] == "TICK":
            lines.append("TICK"); continue
        recs = " ".join(f"rec[{pos[t] - N}]" for t in it[2])
        lines.append(f"{it[0]}({it[1]}) {recs}" if it[1] is not None else f"{it[0]} {recs}")
    return lines


def build(src_lines, R):
    L = src_lines
    mz = [i for i, l in enumerate(L) if l.startswith("M(")]
    R0 = len(mz)
    assert R0 == 12, f"expected a 12-round source, found {R0} Z-ancilla measurement lines"
    blocks = [L[mz[r - 1] + 1:mz[r] + 1] for r in range(1, R0)]
    assert all(b == blocks[0] for b in blocks[:R0 - 2]), "bulk round blocks 1..10 are not identical"
    d0 = next(i for i, l in enumerate(L) if l.startswith("DETECTOR"))
    prefix, last, tail = L[:mz[0] + 1], blocks[-1], L[mz[-1] + 1:d0]
    mo = measurements(L[:d0])
    items = parse_detectors(L[d0:], mo)
    segs, obs = split_rounds(items)
    keys = [k for k, _ in segs]
    assert keys == [0] + list(range(1, R0)) + [("final", R0 - 1)], f"unexpected segment order {keys}"
    seg = dict(segs)
    c0 = lambda s: int(next(it for it in s if it[0] == "DETECTOR")[1])
    dc = c0(seg[2]) - c0(seg[1])
    for r in range(1, R0 - 1):                # rounds 1..10 must equal round 1 shifted (detectors and TICKs)
        assert shift(seg[1], r - 1, (r - 1) * dc) == seg[r], f"round {r} detectors do not follow the round-1 pattern"
    # last round: same detectors as round 1 shifted; only the TICK separators before the final detectors differ
    dets = lambda s: [it for it in s if it[0] == "DETECTOR"]
    assert dets(shift(seg[1], R0 - 2, (R0 - 2) * dc)) == dets(seg[R0 - 1]), "last-round detectors differ from pattern"
    # new circuit
    gates = prefix + blocks[0] * (R - 2) + last + tail
    mo_new = measurements(gates)
    det = list(seg[0])
    for r in range(1, R - 1):
        det += shift(seg[1], r - 1, (r - 1) * dc)
    det += shift(seg[R0 - 1], R - R0, (R - R0) * dc)          # last round keeps its own TICK separators
    det += shift(seg[("final", R0 - 1)], R - R0, (R - R0) * dc)
    det += obs
    return gates + render(det, mo_new), dict(round_block_lines=len(blocks[0]), coord_step_per_round=dc,
                                             detector_lines_per_bulk_round=sum(1 for it in seg[1] if it[0] == "DETECTOR"))


if __name__ == "__main__":
    src, outdir, Rs = sys.argv[1], sys.argv[2], [int(x) for x in sys.argv[3:]]
    os.makedirs(outdir, exist_ok=True)
    text = open(src).read()
    L = text.splitlines()
    trailing = "\n" if text.endswith("\n") else ""
    new12, info = build(L, 12)
    same = "\n".join(new12) + trailing == text
    print(f"{os.path.basename(src)}: R = 12 rebuild byte-identical to the source: {same}; {info}", flush=True)
    assert same, "R = 12 rebuild differs from the source file"
    name = os.path.basename(src)
    for R in Rs:
        out, _ = build(L, R)
        fn = os.path.join(outdir, name.replace("rounds=12", f"rounds={R}"))
        open(fn, "w").write("\n".join(out) + trailing)
        print(f"  wrote {fn}", flush=True)
