# Private GGML Portability Adapter

`llama-cpp-portability.patch` is based on private llama.cpp commit
`f896237df65c8f5d5101d65acfc500e194127a14`. It adds opt-in Decode features and
large-GQA traversal, plus process-local serialization of the native AKV context.
It is not a patch for unmodified upstream llama.cpp, which lacks this private
AKV backend.

In a checkout of that baseline, inspect and apply the patch:

```sh
git apply --check /path/to/ara_dsa/software/akv/integrations/llama-cpp-portability.patch
git apply /path/to/ara_dsa/software/akv/integrations/llama-cpp-portability.patch
```

Build the private backend against this repository's runtime. For the local
RVV Linux cross toolchain, the operator regression used:

```sh
cmake -S /home/wangwy/llama/llama.cpp -B /tmp/qbs-akv-portable-ggml \
  -DCMAKE_TOOLCHAIN_FILE=/home/wangwy/llama/platforms/cva6-qemu/toolchain-rvv.cmake \
  -DCMAKE_BUILD_TYPE=Release -DBUILD_SHARED_LIBS=OFF \
  -DGGML_NATIVE=OFF -DGGML_RVV=ON -DGGML_RV_ZFH=ON -DGGML_RV_ZVFH=ON \
  -DGGML_RV_ZICBOP=OFF -DGGML_RV_ZIHINTPAUSE=OFF \
  -DGGML_OPENMP=OFF -DGGML_BACKEND_DL=OFF -DGGML_LLAMAFILE=OFF \
  -DGGML_RISCV_QBS=ON -DGGML_RISCV_QBS_RUNTIME_DIR=$PWD/software/qbs \
  -DGGML_RISCV_AKV=ON -DGGML_RISCV_AKV_RUNTIME_DIR=$PWD/software/akv \
  -DLLAMA_OPENSSL=OFF -DLLAMA_BUILD_TESTS=OFF -DLLAMA_BUILD_EXAMPLES=OFF \
  -DLLAMA_BUILD_TOOLS=OFF -DLLAMA_BUILD_SERVER=OFF
cmake --build /tmp/qbs-akv-portable-ggml --target ggml -j8
AKV_GGML_BUILD=/tmp/qbs-akv-portable-ggml \
  bash verification/akv/run_ggml_portability_test.sh
```

Run these commands from the hardware repository root, or replace `$PWD` with
its absolute path. The test uses standard RVV QEMU and an AKV F32 oracle,
not native AKV instructions. Native instruction validation is a separate VCS
test. `GGML_RISCV_AKV_PORTABLE=1` enables the new adapter selection only when
the AKV backend itself is enabled and capable; default selection is retained.

No commits or pushes are performed by these scripts. Maintain the external
repository separately; update this patch if the adapter changes.
