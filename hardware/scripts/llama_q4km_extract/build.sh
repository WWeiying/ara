#!/usr/bin/env bash
set -euo pipefail

platform=/home/wangwy/llama/platforms/cva6-qemu
source_dir=/home/wangwy/llama/llama-q4km-extract
build_dir=${platform}/build/llama-q4km-extract

source "${platform}/env.sh"
"${platform}/setup.sh" >/dev/null

cmake -S "${source_dir}" -B "${build_dir}" \
  -DCMAKE_TOOLCHAIN_FILE="${platform}/toolchain-rvv.cmake" \
  -DCMAKE_BUILD_TYPE=Release \
  -DGGML_NATIVE=OFF \
  -DGGML_RVV=ON \
  -DGGML_RV_ZFH=OFF \
  -DGGML_RV_ZVFH=OFF \
  -DGGML_RV_ZICBOP=OFF \
  -DGGML_RV_ZIHINTPAUSE=OFF \
  -DGGML_OPENMP=OFF \
  -DGGML_BACKEND_DL=OFF \
  -DGGML_LLAMAFILE=OFF \
  -DLLAMA_OPENSSL=OFF \
  -DGGML_CUDA=OFF \
  -DGGML_VULKAN=OFF \
  -DBUILD_SHARED_LIBS=OFF

cmake --build "${build_dir}" --target llama-completion llama-q4km-replay -j"$(nproc)"
file "${build_dir}/bin/llama-completion"
file "${build_dir}/bin/llama-q4km-replay"
