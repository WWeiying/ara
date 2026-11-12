#!/usr/bin/env bash
set -euo pipefail
ROOT=$(git rev-parse --show-toplevel)
PORT="$ROOT/software/llama/platform/linux/sdk"
TEST="$ROOT/verification/performance/resident_deployment/kernel_compute"
SIGNOFF=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out
OUT=${1:?provide a unique resident_deployment_kernel_compute_* output directory}
case "$OUT" in
    "$SIGNOFF"/resident_deployment_kernel_compute_*) ;;
    *) printf '%s\n' 'OUT must be an agent-owned signoff directory' >&2; exit 2 ;;
esac
test ! -e "$OUT"
mkdir -p "$OUT/sdk" "$OUT/module/sdk" "$OUT/reference"
git -C "$ROOT" archive 870cadb9f32c79df8d30ab845e4dd2e463a00540 software/akv |
    tar -x -C "$OUT/sdk"
CAP_SOURCE=${ARA_CAP_SOURCE:-/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_deployment_discovery_20261112_020612/inputs/software/akv}
for file in include/akv/akv.h include/akv/akv_abi.h src/akv_runtime.c; do
    cp "$CAP_SOURCE/$file" "$OUT/sdk/software/akv/$file"
done
cp "$ROOT/software/akv/src/akv_v2_native_riscv.c" "$OUT/sdk/software/akv/src/akv_v2_native_riscv.c"
cp -a "$PORT/." "$OUT/module/sdk/"
cp "$ROOT/software/llama/platform/linux/ara_resident_broker.c" \
    "$ROOT/software/llama/platform/linux/ara_resident_uapi.h" \
    "$ROOT/software/llama/platform/linux/job_layout.h" "$OUT/module/"
cp "$TEST/Kbuild.module" "$OUT/module/Makefile"
sha256sum "$ROOT/AGENTS.md" "$PORT"/*.[chS] "$PORT/Kbuild" "$PORT/COPYING.LIB" "$PORT/README.md" "$PORT"/shim/*.h \
    "$CAP_SOURCE"/include/akv/{akv,akv_abi}.h "$CAP_SOURCE/src/akv_runtime.c" \
    "$ROOT/software/akv/src/akv_v2_native_riscv.c" > "$OUT/source-pins.sha256"
find "$TEST" -type f -print0 | sort -z | xargs -0 sha256sum >> "$OUT/source-pins.sha256"
git -C "$ROOT" diff 870cadb9f32c79df8d30ab845e4dd2e463a00540 -- \
    software/akv/src/akv_v2_attention_rvv.S > "$OUT/excluded-dirty-assembly.diff"
sha256sum "$OUT/sdk/software/akv/src/akv_v2_attention_rvv.S" > "$OUT/archived-assembly.sha256"

KERNEL=${KERNEL:-/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/linux-6.19.6}
CROSS=${CROSS:-/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-}
make -C "$KERNEL" ARCH=riscv CROSS_COMPILE="$CROSS" M="$OUT/module" \
    ARA_RESIDENT_SDK="$OUT/sdk" V=1 sdk/ara_resident_compute_core.o sdk/kernel_entry.o > "$OUT/core-kbuild.log" 2>&1
"${CROSS}nm" -u "$OUT/module/sdk/ara_resident_compute_core.o" > "$OUT/undefined.txt"
"${CROSS}readelf" -h -A "$OUT/module/sdk/ara_resident_compute_core.o" > "$OUT/elf.txt"
"${CROSS}objdump" -dr "$OUT/module/sdk/ara_resident_compute_core.o" "$OUT/module/sdk/kernel_entry.o" > "$OUT/disassembly.txt"
"${CROSS}objdump" -dr "$OUT/module/sdk/kernel_entry.o" > "$OUT/entry-disassembly.txt"
if rg -v '^ *U (memcpy|memset|memcmp)$|^$' "$OUT/undefined.txt"; then
    printf '%s\n' 'Unexpected undefined symbol in resident compute object' >&2
    exit 1
fi
rg 'Flags:.*soft-float ABI' "$OUT/elf.txt"
test "$(rg -c 'csrw.*fcsr|fscsr' "$OUT/disassembly.txt")" -ge 1
test "$(rg -c 'csrw.*vstart' "$OUT/disassembly.txt")" -ge 1
if rg '^[[:space:]]*[0-9a-f]+:[[:space:]]+[0-9a-f]{6}(57|d7|07|87|27|a7)[[:space:]]' "$OUT/entry-disassembly.txt"; then
    printf '%s\n' 'Vector or FP instruction in scalar entry' >&2
    exit 1
fi
awk '/fscsr|csrw.*fcsr/{f=NR} /csrw.*vcsr/{v=NR} /csrw.*vstart/{s=NR}
     /R_RISCV_CALL.*ara_resident_compute_owned/{c=NR}
     END {exit !(f && v && s && c && f < v && v < s && s < c)}' "$OUT/entry-disassembly.txt"
awk -F '\t' '$2 > 1024 {print; bad=1} END {exit bad}' "$OUT/module/sdk/"*.su

GLIBC=${GLIBC:-/home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/glibc-2.42-51-gcbf39c26b25801e9bc88499b4fd361ac172d4125}
cp "$GLIBC/sysdeps/ieee754/flt-32/e_expf.c" "$GLIBC/sysdeps/ieee754/flt-32/e_exp2f_data.c" "$OUT/reference/"
sha256sum "$OUT/reference"/*.c "$GLIBC/sysdeps/ieee754/flt-32/math_config.h" > "$OUT/math-source-pins.sha256"
CC=${HOST_CC:-gcc}
COMMON=(-O2 -std=gnu11 -Wall -Wextra -Werror -ffp-contract=off -fno-tree-vectorize)
"$CC" "${COMMON[@]}" -I"$TEST/glibc_shim" -D__expf=ara_glibc_reference_expf \
    -c "$OUT/reference/e_expf.c" -o "$OUT/reference/expf.o"
"$CC" "${COMMON[@]}" -I"$TEST/glibc_shim" -c "$OUT/reference/e_exp2f_data.c" -o "$OUT/reference/data.o"
"$CC" "${COMMON[@]}" "$PORT/kernel_expf.c" "$TEST/test_expf.c" \
    "$OUT/reference/expf.o" "$OUT/reference/data.o" -lm -o "$OUT/test_expf"
"$OUT/test_expf" > "$OUT/math-test.log"
"$CC" "${COMMON[@]}" -Wno-unused-function -Wno-unknown-pragmas \
    -ffunction-sections -fdata-sections -DAKV_EXPERIMENTAL_RESIDENT_ATTENTION=1 \
    -I"$OUT/sdk" -I"$OUT/sdk/software/akv/include" -I"$PORT" "$TEST/test_prepare.c" \
    "$PORT/kernel_entry.c" "$OUT/sdk/software/akv/src/akv_runtime.c" \
    -Wl,--gc-sections -lm -o "$OUT/test_prepare"
"$OUT/test_prepare" > "$OUT/prepare-test.log"
make -C "$KERNEL" ARCH=riscv CROSS_COMPILE="$CROSS" M="$OUT/module" \
    ARA_RESIDENT_SDK="$OUT/sdk" V=1 modules > "$OUT/kbuild.log" 2>&1
"${CROSS}nm" -u "$OUT/module/ara_resident.ko" > "$OUT/module-undefined.txt"
"${CROSS}readelf" -Ws -h -A "$OUT/module/ara_resident.ko" > "$OUT/module-symbols.txt"
rg 'Flags:.*soft-float ABI' "$OUT/module-symbols.txt"
sha256sum -c "$OUT/source-pins.sha256" > "$OUT/source-pins-check.log"
printf '%s\n' 'PASS: host checks, Linux Kbuild/modpost/full .ko link (no load or board execution)' > "$OUT/result.txt"
printf '%s\n' "$OUT"
