#!/usr/bin/env bash
# Build only in a fresh output directory; no make, VCS, Spike or shared artifacts.
# Parent runs this entire script under timeout180s; compiler subprocesses timeout30s.
set -euo pipefail
root=/home/wangwy/openproject/ara_dsa_signoff_integration
test "$#" -eq 3
review=$1
seal=$2
out=$3
/usr/bin/python3 -B - "$review" "$seal" "$out" <<'PY'
import hashlib,json,sys
from pathlib import Path
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as s:
        for b in iter(lambda:s.read(1048576),b''):h.update(b)
    return h.hexdigest()
p=Path(sys.argv[1]).resolve();out=Path(sys.argv[3]).absolute()
assert sha(p)==sys.argv[2]
r=json.loads(p.read_bytes())
assert r['relative_admission_population']==727 and not r['VCS_approved']
assert out.parent==p.parents[1] and not out.exists() and out.resolve()==out
for path,digest in r['pins'].items():assert sha(path)==digest, 'Pin drift: '+path
PY
mkdir "$out"
llvm="$root/install/riscv-llvm"
cc="$llvm/bin/clang"
common="$root/apps/common"
app="$root/apps/fence_t_u_padding_successor"
flags=(-march=rv64gcv_zfh_zvfh -mabi=lp64d --target=riscv64-unknown-elf
       -mcmodel=medany -mno-relax -O2 -std=gnu99 -fno-vectorize
       -fno-slp-vectorize -mno-implicit-float -fno-common -fno-builtin-printf
       -DNR_LANES=4 -DVLEN=1024)
includes=()
for dir in apps/include apps/common apps/riscv-tests/isa/macros/scalar
do includes+=("-I$root/$dir"); done
for dir in apps/riscv-tests/isa/macros/vector apps/riscv-tests/env apps/riscv-tests/benchmarks/common
do includes+=("-I$root/$dir"); done
objects=()
for src in "$common/crt0.S" "$common/printf.c" "$common/string.c" "$common/serial.c" \
           "$common/util.c" "$common/print_trap_cause.c" "$app/probe.S" "$app/main.c"
do
    name=${src##*/}
    warnings=()
    if [[ $src == "$app/"* ]]; then warnings=(-Wall -Wextra -Werror); fi
    timeout --kill-after=5s 30s "$cc" "${flags[@]}" "${includes[@]}" "${warnings[@]}" \
        -c "$src" -o "$out/$name.o" >"$out/$name.build.log" 2>&1
    objects+=("$out/$name.o")
done
elf="$out/input.elf"
timeout --kill-after=5s 30s "$cc" "${flags[@]}" -fuse-ld=lld -static -nostartfiles \
    "-T$common/link.ld" "${objects[@]}" -lm "-L$(readlink -f "$llvm")/lib/generic" \
    -lclang_rt.builtins-riscv64 -o "$elf" >"$out/link.log" 2>&1
timeout --kill-after=5s 15s "$llvm/bin/llvm-objdump" -d "$elf" >"$out/input.dis"
timeout --kill-after=5s 15s "$llvm/bin/llvm-readelf" -lWs "$elf" >"$out/input.readelf"
timeout --kill-after=5s 15s "$llvm/bin/llvm-readobj" --elf-output-style=JSON \
    --sections --symbols --program-headers "$elf" >"$out/elf_metadata.json"
sha256sum "$elf" >"$out/input.sha256"
printf '%s\n' 'BUILD_ONLY_COMPLETE_PENDING_ELF_AUDIT_NO_SPIKE_NO_VCS'
