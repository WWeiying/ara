#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
platform=/home/wangwy/llama/platforms/cva6-qemu
sdk=/home/wangwy/openproject/cva6/cva6-sdk
build_dir=${platform}/build/llama-q4km-extract
test_build_dir=/home/wangwy/llama/llama.cpp/build-rv64-cva6-rvv
rootfs=${sdk}/rootfs

test -x "${build_dir}/bin/llama-completion"
test -x "${build_dir}/bin/llama-q4km-replay"
test -x "${test_build_dir}/bin/test-ara-q4k-repack"

install -d "${rootfs}/opt/ara-q4km" "${rootfs}/etc/init.d"
install -m 0755 "${build_dir}/bin/llama-completion" \
  "${rootfs}/opt/ara-q4km/llama-completion-rvv"
install -m 0755 "${build_dir}/bin/llama-q4km-replay" \
  "${rootfs}/opt/ara-q4km/llama-q4km-replay-rvv"
install -m 0755 "${test_build_dir}/bin/test-ara-q4k-repack" \
  "${rootfs}/opt/ara-q4km/test-ara-q4k-repack-rvv"
install -m 0755 \
  "${repo_root}/hardware/scripts/llama_q4km_extract/guest-capture.sh" \
  "${rootfs}/etc/init.d/S99ara-q4km-capture"

"${platform}/build-image.sh"
