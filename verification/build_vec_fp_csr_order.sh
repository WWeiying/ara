#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
out=$(realpath -m -- "${1:?usage: build_vec_fp_csr_order.sh NEW_OUTPUT_DIR}")
test ! -e "$out"
cc="$root/install/riscv-llvm/bin/clang"
objdump="$root/install/riscv-llvm/bin/llvm-objdump"
spike=${SPIKE:-/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike}
mkdir -p "$out/inputs/common" "$out/inputs/spike" "$out/logs"
cp -p "$root/apps/riscv-tests/isa/rv64uv/vec_fp_csr_order.c" "$out/inputs/"
for name in vfp_vstart_edges vfredosum vfwmacc; do
  cp -p "$root/apps/riscv-tests/isa/rv64uv/$name.c" "$out/inputs/"
done
cp -p "${BASH_SOURCE[0]}" "$out/inputs/"
cp -a "$root/apps/riscv-tests/isa/macros" "$out/inputs/"
for name in crt0.S printf.c printf.h string.c serial.c util.c util.h print_trap_cause.c encoding.h link_sim_2m.ld; do
  cp -p "$root/apps/common/$name" "$out/inputs/common/"
done
for name in crt.S syscalls.c util.h test.ld; do
  cp -p "$root/apps/riscv-tests/benchmarks/common/$name" "$out/inputs/spike/"
done
cp -p "$root/apps/riscv-tests/env/encoding.h" "$out/inputs/spike/"
run() {
  printf '%q ' "$@" >> "$out/commands.log"
  printf '\n' >> "$out/commands.log"
  "$@"
}
flags=(-march=rv64gcv_zfh_zvfh -mabi=lp64d -mno-relax -mcmodel=medany
  -O3 -ffast-math -fno-common -fno-builtin-printf -fno-vectorize
  -mllvm -scalable-vectorization=off -mllvm -riscv-v-vector-bits-min=0
  -mno-implicit-float -std=gnu99 -DVLEN=1024 -DNR_LANES=4
  -Wall -Wextra -Wno-unused-command-line-argument
  "-I$out/inputs/macros/scalar" "-I$out/inputs/macros/vector")
src="$out/inputs/vec_fp_csr_order.c"
s="$out/inputs/spike"
a="$out/inputs/common"
run "$cc" -fuse-ld=lld "${flags[@]}" "-I$s" -DPREALLOCATE=1 \
  -D__FLOAT_SUPPORT__ -D__SPIKE__=1 -static -nostdlib -nostartfiles \
  -T "$s/test.ld" -o "$out/inputs/vec_fp_csr_order.spike.elf" \
  "$src" "$s/crt.S" "$s/syscalls.c" > "$out/logs/compile.spike.log" 2>&1
run timeout 60s "$spike" -l --isa=rv64gcv_zfh_zvfh_zvl1024b \
  "$out/inputs/vec_fp_csr_order.spike.elf" \
  > "$out/logs/spike.stdout" 2> "$out/logs/spike.trace"
rg '^vec_fp_csr_order: 21 cases, 762 checks, traps=2$' "$out/logs/spike.stdout"
rg '^PASSED:' "$out/logs/spike.stdout"
if rg 'FAIL' "$out/logs/spike.stdout"; then exit 1; fi
run "$cc" -fuse-ld=lld "${flags[@]}" "-I$a" -ffunction-sections -fdata-sections \
  -static -nostartfiles -Wl,--gc-sections -T "$a/link_sim_2m.ld" \
  -o "$out/inputs/vec_fp_csr_order.elf" "$src" "$a/crt0.S" "$a/printf.c" \
  "$a/string.c" "$a/serial.c" "$a/util.c" "$a/print_trap_cause.c" \
  -lm "-L$root/install/riscv-llvm/lib/generic" -lclang_rt.builtins-riscv64 \
  > "$out/logs/compile.ara.log" 2>&1
run "$objdump" -d "$out/inputs/vec_fp_csr_order.elf" > "$out/logs/ara.dump"
run "$objdump" -d "$out/inputs/vec_fp_csr_order.spike.elf" > "$out/logs/spike.dump"
for name in vfp_vstart_edges vfredosum vfwmacc; do
  run "$cc" -fuse-ld=lld "${flags[@]}" "-I$a" -ffunction-sections -fdata-sections \
    -static -nostartfiles -Wl,--gc-sections -T "$a/link_sim_2m.ld" \
    -o "$out/inputs/$name.elf" "$out/inputs/$name.c" "$a/crt0.S" "$a/printf.c" \
    "$a/string.c" "$a/serial.c" "$a/util.c" "$a/print_trap_cause.c" \
    -lm "-L$root/install/riscv-llvm/lib/generic" -lclang_rt.builtins-riscv64 \
    > "$out/logs/compile.$name.ara.log" 2>&1
  run "$cc" -fuse-ld=lld "${flags[@]}" "-I$s" -DPREALLOCATE=1 \
    -D__FLOAT_SUPPORT__ -D__SPIKE__=1 -static -nostdlib -nostartfiles \
    -T "$s/test.ld" -o "$out/inputs/$name.spike.elf" \
    "$out/inputs/$name.c" "$s/crt.S" "$s/syscalls.c" \
    > "$out/logs/compile.$name.spike.log" 2>&1
  run timeout 60s "$spike" --isa=rv64gcv_zfh_zvfh_zvl1024b \
    "$out/inputs/$name.spike.elf" > "$out/logs/$name.spike.stdout" \
    2> "$out/logs/$name.spike.stderr"
  rg '^PASSED:' "$out/logs/$name.spike.stdout"
  if rg 'FAIL|ERROR' "$out/logs/$name.spike.stdout"; then exit 1; fi
done
python3 - "$out" "$cc" "$spike" "$root" <<'PY'
import hashlib
import json
from pathlib import Path
import re
import sys

out, cc, spike, root = map(Path, sys.argv[1:])
def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()

trace = (out / 'logs/spike.trace').read_text().splitlines()
pcs = [line for line in trace if re.match(r'^core +0: 0x[0-9a-f]+ \(0x[0-9a-f]+\)', line)]
assert sum('exception trap_illegal_instruction' in line for line in trace) == 2
assert sum('exception ' in line for line in trace) == 2
assert sum('vfcvt.x.f.v' in line or 'vfdiv.vv' in line for line in pcs) == 30
adjacency = {}
for kind in ('ara', 'spike'):
    instructions = []
    for line in (out / f'logs/{kind}.dump').read_text().splitlines():
        match = re.match(r'\s*([0-9a-f]+):\s+[0-9a-f]+\s+(.+)', line)
        if match:
            instructions.append((match[1], match[2]))
    pairs = []
    consecutive_pairs = 0
    for i, (pc, insn) in enumerate(instructions):
        if insn.startswith(('vfcvt.x.f.v', 'vfdiv.vv')):
            next_pc, following = instructions[i + 1]
            if following.startswith('vfcvt.x.f.v'):
                consecutive_pairs += 1
                assert insn.startswith('vfcvt.x.f.v')
                assert instructions[i + 2][1].split()[0] in {'frflags', 'csrr'}
            else:
                assert following.split()[0] in {
                'frflags', 'fsflags', 'fsflagsi', 'frrm', 'fsrm', 'frcsr', 'fscsr',
                'csrr', 'csrw', 'csrrw', 'csrrs', 'csrrc', 'csrrwi', 'csrrsi', 'csrrci',
                    'csrwi', 'csrsi', 'csrci'}, (pc, insn, following)
            pairs.append(dict(pc=pc, instruction=insn, next_pc=next_pc, next_instruction=following))
    assert len(pairs) == 22 and consecutive_pairs == 1, (kind, len(pairs), consecutive_pairs)
    adjacency[kind] = pairs
hashes = {str(p.relative_to(out)): sha(p) for p in sorted((out / 'inputs').rglob('*')) if p.is_file()}
adjacent = {}
for name in ('vfp_vstart_edges', 'vfredosum', 'vfwmacc'):
    digest = hashes[f'inputs/{name}.c']
    assert sha(root / f'apps/riscv-tests/isa/rv64uv/{name}.c') == digest
    adjacent[name] = dict(source=f'inputs/{name}.c', source_sha256=digest,
                          elf=f'inputs/{name}.elf', sha256=hashes[f'inputs/{name}.elf'],
                          spike_elf=f'inputs/{name}.spike.elf', spike_status='PASS',
                          source_unchanged=True)
manifest = dict(status='PASS', cases=21, checks=762, expected_traps=2,
                vlen=1024, nr_lanes=4, spike_trace_instruction_records=len(pcs),
                instruction_count_scope='Emitted -l records, including harness/HTIF; terminal repeats may be suppressed; not DUT cycles.',
                critical_adjacency=adjacency, adjacent=adjacent, input_sha256=hashes,
                compiler=dict(path=str(cc.resolve()), sha256=sha(cc)),
                spike=dict(path=str(spike.resolve()), sha256=sha(spike)), vcs_run=False)
(out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
(out / 'SHA256SUMS').write_text(''.join(f'{digest}  {path}\n' for path, digest in hashes.items()))
for path in (out / 'inputs').rglob('*'):
    if path.is_file():
        path.chmod(path.stat().st_mode & ~0o222)
print(f'PASS: 21 cases / 762 checks / 2 traps; {len(pcs)} Spike -l records; inputs frozen')
PY
