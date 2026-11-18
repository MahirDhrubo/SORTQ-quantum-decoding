#!/bin/bash
# sortq build --order rb on the six Test 3f decoders + regressions + rb lint. nice 10, the SORTQ Python environment.
cd "$(dirname "$0")"
export SORTQ_REF_RUN=engine_top_pf2fix_p1_lutram_fmax          # as results/test3f/builds_refix
RX=$(cd ../circuits/relay_memory_X && pwd)      # memory_X circuits (Z decoders), as Test 3f
BI=$(cd ../circuits/bb_ibm && pwd)                         # memory_Z circuits (X decoders), as Test 3f
OUT=../results/test3f/builds_rb; CHK=../results/test3f/builds_sweepcheck; mkdir -p $OUT $CHK
c() { basename "$(ls $4/circuit=bicycle_bivariate_$1_memory_$2,distance=$3,rounds=$3,error_rate=0.003,noise_model=uniform_circuit,basis=CX,*.stim)"; }   # A, B differ per code
for spec in "72_12_6 6" "144_12_12 12" "288_12_18 18"; do set -- $spec
  for b in X Z; do
    if [ $b = X ]; then f=$BI/$(c $1 Z $2 $BI); n=${1}_memory_Z_Xdec; else f=$RX/$(c $1 X $2 $RX); n=${1}_memory_X_Zdec; fi
    t0=$(date +%s.%N)
    nice -n 10 ../sortq build "$f" --basis $b --order rb --out $OUT/bicycle_bivariate_$n > $OUT/bicycle_bivariate_$n.out 2>&1
    echo "BUILD bicycle_bivariate_$n rc=$? $(echo "$(date +%s.%N) - $t0" | bc) s"
    nice -n 10 ../sortq build "$f" --basis $b --order sweep --out $CHK/bicycle_bivariate_$n > /dev/null 2>&1
    nice -n 10 ./sortq_lint_rb.sh $OUT/bicycle_bivariate_$n $(( $2 + 1 ))
  done
done
# regressions
G=bicycle_bivariate_144_12_12_memory_Z_Xdec
echo "REG rb_pkg.sv (sortq build, gross X) vs hw/rb/rtl/rb_pkg.sv:"; diff $OUT/$G/rb_pkg.sv ../hw/rb/rtl/rb_pkg.sv && echo "  identical"
T=$(mktemp -d); (cd ../hw/rb/gen && nice -n 10 ${SORTQ_PYTHON:-python3} gen_rb_pkg.py "$BI/$(c 144_12_12 Z 12 $BI)" $T > $T/gen.out 2>&1)
echo "REG standalone generator (test1c engine_params) vs hw/rb/rtl/rb_pkg.sv:"; diff $T/rb_pkg.sv ../hw/rb/rtl/rb_pkg.sv && echo "  identical"
nice -n 10 ${SORTQ_PYTHON:-python3} - $OUT $CHK ../results/test3f/builds_refix <<'PY'
import sys, os, json, re
out, chk, ref = sys.argv[1:4]
def norm(path):
    t = open(path).read()
    if path.endswith(".json"):
        d = json.loads(t); d.pop("seconds", None); return json.dumps(d, sort_keys=True)
    return re.sub(r"written to \S+", "written to <out>", t)
for n in sorted(os.listdir(ref)):
    files = sorted(f for f in os.listdir(os.path.join(ref, n)) if f != "build.log")
    sw = [f for f in files if norm(os.path.join(chk, n, f)) != norm(os.path.join(ref, n, f))]
    rb = [f for f in files if f != "report.md" and norm(os.path.join(out, n, f)) != norm(os.path.join(ref, n, f))]
    extra = sorted(set(os.listdir(chk + "/" + n)) - set(os.listdir(os.path.join(ref, n))))
    print(f"REG {n}: sweep build vs builds_refix ({len(files)} files, runtime field and output path normalised): "
          f"{'identical' if not sw and not extra else 'DIFFERS ' + str(sw + extra)}; rb build, same files except report.md: "
          f"{'identical' if not rb else 'DIFFERS ' + str(rb)}")
PY
echo ALL DONE
