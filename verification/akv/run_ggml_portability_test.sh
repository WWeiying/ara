#!/usr/bin/env bash
set -euo pipefail
root=$(cd -- "$(dirname -- "$0")/../.." && pwd)
llama=${AKV_LLAMA_SRC:-/home/wangwy/llama/llama.cpp}
platform=${AKV_QEMU_PLATFORM:-/home/wangwy/llama/platforms/cva6-qemu}
build=${AKV_GGML_BUILD:?set AKV_GGML_BUILD to the cross-compiled static GGML build}
run=${AKV_PORTABLE_RUN:-${root}/software/akv/build/ggml-portability}
d256=${AKV_TEST_D256:-0}
[[ ${d256} == 0 || ${d256} == 1 ]] || exit 2
mkdir -p "${run}"
cc=${platform}/tools/bin/riscv64-linux-g++
"${cc}" -std=c++17 -O2 -march=rv64gcv_zfh_zvfh -mabi=lp64d -static -pthread \
  "-DAKV_TEST_D256=${d256}" \
  -I"${llama}/ggml/include" -I"${llama}/ggml/src" -I"${llama}/ggml/src/ggml-cpu" \
  "${root}/verification/akv/ggml_portability_test.cpp" \
  -Wl,--start-group "${build}/ggml/src/libggml.a" \
  "${build}/ggml/src/libggml-cpu.a" "${build}/ggml/src/libggml-base.a" \
  -Wl,--end-group -lm -o "${run}/test"
gen=${AKV_GEN_INIT_CPIO:-}
if [[ -z ${gen} ]]; then
  gen=$(find "${platform}/sdk/buildroot/output/build" -path '*/usr/gen_init_cpio' -type f -print -quit)
fi
test -x "${gen}"
printf '%s\n' 'dir /dev 755 0 0' 'nod /dev/console 600 0 0 c 5 1' \
  'dir /proc 755 0 0' 'dir /sys 755 0 0' \
  "file /init ${run}/test 755 0 0" > "${run}/init.list"
"${gen}" "${run}/init.list" > "${run}/init.cpio"
sha256sum "${run}/test" "${build}/ggml/src/libggml-cpu.a" > "${run}/binaries.sha256"
timeout --foreground "${AKV_PORTABLE_TIMEOUT:-180}" \
  "${platform}/tools/bin/qemu-system-riscv64" \
  -M virt -cpu rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true \
  -smp 2 -m 512M -nographic -monitor none \
  -bios "${platform}/images/fw_dynamic.bin" -kernel "${platform}/images/Image" \
  -initrd "${run}/init.cpio" -append 'console=ttyS0 rdinit=/init' \
  > "${run}/qemu.log" 2>&1
grep -F 'AKV GGML portability: PASS cases=18 concurrent_graphs=2 fallbacks=2 legacy=1' "${run}/qemu.log"
if [[ ${d256} == 1 ]]; then
  grep -F 'AKV GGML D256: PASS cases=16 default_fallbacks=16 feature_fallbacks=5 layout=1 v1=1 gqa=1 optout=1 legacy_dims=2 guards=1' "${run}/qemu.log"
fi
