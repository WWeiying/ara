#!/usr/bin/env bash
set -euo pipefail

ara_root=$(cd -- "$(dirname -- "$0")/../../.." && pwd)
llama_src=${AKV_LLAMA_SRC:-/home/wangwy/llama/llama.cpp}
build_dir=${AKV_LLAMA_BUILD_DIR:-${llama_src}/build-rv64-cva6-akv-static}
toolchain=${AKV_LLAMA_TOOLCHAIN:-/home/wangwy/llama/toolchains/riscv64-cva6-rvv.cmake}
qbs_runtime=${QBS_RUNTIME_DIR:-${ara_root}/software/qbs}
jobs=${AKV_BUILD_JOBS:-$(nproc)}

cmake -S "${llama_src}" -B "${build_dir}" \
  -DCMAKE_TOOLCHAIN_FILE="${toolchain}" \
  -DCMAKE_BUILD_TYPE=Release \
  -DCMAKE_EXE_LINKER_FLAGS=-static \
  -DGGML_NATIVE=OFF \
  -DGGML_RVV=ON \
  -DGGML_RV_ZFH=ON \
  -DGGML_RV_ZVFH=ON \
  -DGGML_RV_ZICBOP=OFF \
  -DGGML_RV_ZIHINTPAUSE=OFF \
  -DGGML_OPENMP=OFF \
  -DGGML_BACKEND_DL=OFF \
  -DGGML_LLAMAFILE=OFF \
  -DGGML_RISCV_QBS=ON \
  -DGGML_RISCV_QBS_RUNTIME_DIR="${qbs_runtime}" \
  -DGGML_RISCV_AKV=ON \
  -DGGML_RISCV_AKV_RUNTIME_DIR="${ara_root}/software/akv" \
  -DLLAMA_OPENSSL=OFF \
  -DLLAMA_BUILD_TESTS=OFF \
  -DLLAMA_BUILD_EXAMPLES=ON \
  -DLLAMA_BUILD_TOOLS=OFF \
  -DLLAMA_BUILD_SERVER=OFF \
  -DBUILD_SHARED_LIBS=OFF

cmake --build "${build_dir}" --target llama-simple -j"${jobs}"
file "${build_dir}/bin/llama-simple"
