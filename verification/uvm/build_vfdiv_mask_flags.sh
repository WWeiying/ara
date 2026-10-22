#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)
out=$(realpath -m -- "${1:?usage: build_vfdiv_mask_flags.sh NEW_OUTPUT_DIR}")
test ! -e "$out"
cc="$root/install/riscv-llvm/bin/clang"
objdump="$root/install/riscv-llvm/bin/llvm-objdump"
spike=${SPIKE:-/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike}
isa=rv64gcv_zvfh_zvl1024b
"$cc" --version | rg '^clang version 22\.'
mkdir -p "$out/inputs/common" "$out/inputs/spike" "$out/logs"
cp -p "$root/apps/riscv-tests/isa/rv64uv/vfdiv_mask_flags.c" "$out/inputs/"
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
flags=(-march=rv64gcv_zvfh -mabi=lp64d -mno-relax -mcmodel=medany
  -O3 -fno-common -fno-builtin-printf -fno-vectorize -fno-slp-vectorize
  -mllvm -scalable-vectorization=off -mllvm -riscv-v-vector-bits-min=0
  -mno-implicit-float -std=gnu99 -DVLEN=1024 -DNR_LANES=4
  -Wall -Wextra -Wno-unused-command-line-argument
  "-I$out/inputs/macros/scalar" "-I$out/inputs/macros/vector")
src="$out/inputs/vfdiv_mask_flags.c"
s="$out/inputs/spike"
a="$out/inputs/common"
run timeout 120s "$cc" -fuse-ld=lld "${flags[@]}" "-I$s" -DPREALLOCATE=1 \
  -D__FLOAT_SUPPORT__ -D__SPIKE__=1 -static -nostdlib -nostartfiles \
  -T "$s/test.ld" -o "$out/inputs/vfdiv_mask_flags.spike.elf" \
  "$src" "$s/crt.S" "$s/syscalls.c" > "$out/logs/compile.spike.log" 2>&1
run timeout 60s "$spike" -l "--isa=$isa" "$out/inputs/vfdiv_mask_flags.spike.elf" \
  > "$out/logs/spike.stdout" 2> "$out/logs/spike.trace"
rg '^vfdiv_mask_flags: 52 cases, 1612 checks,' "$out/logs/spike.stdout"
rg '^PASSED:' "$out/logs/spike.stdout"
if rg 'FAIL|ERROR' "$out/logs/spike.stdout"; then exit 1; fi
test "$(rg -c 'vfdiv\.vv' "$out/logs/spike.trace")" = 52
if rg 'exception trap_' "$out/logs/spike.trace"; then exit 1; fi
run timeout 120s "$cc" -fuse-ld=lld "${flags[@]}" "-I$a" -ffunction-sections -fdata-sections \
  -static -nostartfiles -Wl,--gc-sections -T "$a/link_sim_2m.ld" \
  -o "$out/inputs/vfdiv_mask_flags.elf" "$src" "$a/crt0.S" "$a/printf.c" \
  "$a/string.c" "$a/serial.c" "$a/util.c" "$a/print_trap_cause.c" \
  -lm "-L$root/install/riscv-llvm/lib/generic" -lclang_rt.builtins-riscv64 \
  > "$out/logs/compile.ara.log" 2>&1
run "$objdump" -d "$out/inputs/vfdiv_mask_flags.elf" > "$out/logs/ara.dump"
run "$objdump" -d "$out/inputs/vfdiv_mask_flags.spike.elf" > "$out/logs/spike.dump"
cmp "$src" "$root/apps/riscv-tests/isa/rv64uv/vfdiv_mask_flags.c"
"$cc" --version > "$out/logs/compiler.version"
sha256sum "$cc" "$spike" > "$out/TOOL_SHA256SUMS"
cd "$out"
rg --files inputs | LC_ALL=C sort | xargs -d '\n' sha256sum > SHA256SUMS
sha256sum --check SHA256SUMS > logs/source_check.log
elf_sha=$(sha256sum inputs/vfdiv_mask_flags.elf)
gold_sha=$(sha256sum inputs/vfdiv_mask_flags.spike.elf)
jq -n --arg isa "$isa" --arg compiler "$(realpath "$cc")" \
  --arg spike "$(realpath "$spike")" --arg elf_sha "${elf_sha%% *}" \
  --arg gold_sha "${gold_sha%% *}" \
  --arg summary "$(rg '^vfdiv_mask_flags:' logs/spike.stdout)" \
  '{status:"PASS", golden:"Spike", isa:$isa, cases:52, checks:1612,
    dynamic_vfdiv_instructions:52, vlen:1024, nr_lanes:4, summary:$summary,
    compiler:$compiler, spike:$spike, processor_simulation_run:false,
    elf:"inputs/vfdiv_mask_flags.elf", elf_sha256:$elf_sha,
    golden_elf:"inputs/vfdiv_mask_flags.spike.elf", golden_sha256:$gold_sha,
    checksum_file:"SHA256SUMS", tool_checksum_file:"TOOL_SHA256SUMS"}' > manifest.json
rg --files inputs -0 | xargs -0 chmod a-w
printf 'PASS frozen %s\n' "$out/inputs/vfdiv_mask_flags.elf"
