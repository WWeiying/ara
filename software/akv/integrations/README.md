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
its absolute path. The test uses standard RVV QEMU and the GGML F16-accumulator functional executor,
not native AKV instructions. Native instruction validation is a separate VCS
test. `GGML_RISCV_AKV_PORTABLE=1` enables the new adapter selection only when
the AKV backend itself is enabled and capable; default selection is retained.

No commits or pushes are performed by these scripts. Maintain the external
repository separately; update this patch if the adapter changes.

## Experimental D256 Decode

`llama-cpp-d256-admission.patch` is an alternative, complete patch against the
same `f896237df65c8f5d5101d65acfc500e194127a14` baseline. It includes the portability
changes above. Apply one of the two patches, not both. This records the external
adapter in the hardware repository without committing the user's llama.cpp worktree.

The original local adapter was at `8ed9403e3` plus uncommitted changes; its
`akv.cpp` SHA-256 before D256 admission was
`495dfe1e88a03974d64ed17780e4597f13bcd5ec13411810a435aeedfda53c61`.
Those changes are preserved in this patch and in the original worktree.

`GGML_RISCV_AKV_D256=1` enables only verified-contract D256 Decode candidates:
segmented v2 and panel4 capabilities, aligned F16 K/V, and an unmodified zero
mask prefix with optional trailing `-Inf`. Other features and D256 Prefill keep
their RVV fallback. The flag is off by default. The linked runtime and header
must come from this repository's token-order implementation; its software
contract is marked by `AKV_D256_ONLINE_FP16` (not an ISA capability).

```sh
AKV_TEST_D256=1 AKV_LLAMA_SRC=/path/to/patched/llama.cpp \
  AKV_GGML_BUILD=/path/to/static/ggml/build \
  AKV_PORTABLE_RUN=/path/to/new/test-output \
  bash verification/akv/run_ggml_portability_test.sh
```

Set `AKV_MODEL_D256=1` in `run-qemu-model-check.sh` to pass the option to the
guest's combined run. Its RVV and QBS-only variants explicitly clear the flag.
`verification/akv/run_d256_admission.py` runs the fixed real-model cohort with
per-case deadlines and preserves binaries, hashes, output and selection evidence.
