# Resident Kernel Compute Port

This is a compute implementation, not an OS admission provider. The broker owns
all allocations, copy-in/copy-out, memory eligibility, exclusive hardware access,
FP/vector state saving, preemption and IRQ lifetime, and terminal fault handling.
The two public functions and their scalar-only buffer contract are in
`kernel_compute.h`. Scratch size is queried, never hardcoded; currently 6848 bytes
at 64-byte alignment. Output is a separate, private kernel scratch allocation.

The supported domain is one F16 Decode group, 1..8 heads, D64/D96/D128, 1..256
tokens, finite Q/K/V, finite mask or negative infinity with at least one finite
entry, and finite `0 < scale <= 1`. Unsupported domains return `-EOPNOTSUPP`
before execution. Buffer/shape errors return `-EINVAL`. `started` is never reset;
after it becomes one, no fallback/retry is allowed. Success replaces input scope
flags with accrued RISC-V fflags and sets `resident_used=1`.

`kernel_entry.c` uses ordinary scalar kernel compiler flags. It validates the
scope assertions and clears fcsr/vcsr/vstart before calling the vector core.
This separation also protects against compiler-generated RVV stack initialization.
The core queries real indices 0..4 and checks composed Resident QK+PV, four lanes,
VLEN1024 and native v2 capabilities. Software scope assertions never replace
discovery. The broker still performs its idle CSR/fence before releasing memory.

## Source Inputs

Extract `software/akv` from commit
`870cadb9f32c79df8d30ab845e4dd2e463a00540` with `git archive`. Overlay only the
approved capability `akv.h`, `akv_abi.h`, `akv_runtime.c`, and the approved
`akv_v2_native_riscv.c`. Rebuild every SDK object and consumer together; the
capability struct layout changed. The verification runner defaults to capability
files from the frozen `resident_deployment_discovery_20261112_020612` snapshot.

The compute core includes the real SDK C source and calls its workspace init,
softmax, normalization and FULL/REFILL/RELEASE helpers plus the archived tracked
`qk.S` and `pv.S`/`pv_prepare.S`. The ordinary attention assembly, including the
dirty `akv_v2_attention_rvv.S`, is not linked. Whole-program compilation followed
by section GC removes the unused native, prefill, feature, tanhf and fmaf paths.
Only kernel memcpy/memset are unresolved in the final compute object.

## Kbuild Integration

The parent `linux/Makefile` contains:

```make
obj-m += ara_resident.o
ara_resident-y := ara_resident_broker.o
include $(src)/sdk/Kbuild_norelax
```

The fragment appends only `sdk/ara_resident_compute_core.o`, which contains both
the scalar entry and the GC-linked numerical core. Do not append the core a
second time. All FP/vector compilation stays in the
numerical closure with `-march=rv64gcv_zfh_zvfh -mabi=lp64`; the broker and entry
keep ordinary scalar kernel flags. No libc headers or lp64d objects are used.

Use the successor `Kbuild_norelax` for loadable modules. It includes the original,
sealed `Kbuild` and explicitly applies the kernel's module C/assembly flags plus
`-mno-relax` to every partial-core input, including the scalar entry. Custom
partial-link dependencies are not expanded into Kbuild's `real-obj-m`; the old
build therefore missed the automatic module relaxation policy. GCC-generated
function alignment left `R_RISCV_ALIGN` in the old core, and Linux 6.19.6 rejects
that relocation with `-EINVAL`. The successor's six input objects and final core
have zero `R_RISCV_ALIGN` and zero `R_RISCV_RELAX`. Do not strip relocation records
from an old object as a substitute for rebuilding with the correct policy.

For a frozen module source directory and prepared SDK extraction:

```sh
make -C /home/wangwy/openproject/cva6/cva6-sdk/buildroot/output/build/linux-6.19.6 \
  ARCH=riscv \
  CROSS_COMPILE=/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux- \
  M="$OUT/module" ARA_RESIDENT_SDK="$OUT/sdk" modules
```

The sealed `verification/performance/resident_deployment/kernel_compute/run.sh`
records the historical source/host checks using the original Kbuild. It is not
the norelax rebuild recipe or evidence of module loadability; do not rerun it to
recreate the current delivery. Use the parent Makefile above with a fresh frozen
module source directory, or link the exact frozen successor core for identity-
checked module/smoke consumers. Neither method builds the kernel, changes its
configuration, loads the module or modifies DTS. Compilation and host checks are
not board or whole-model acceptance.

## Norelax Receipt

The frozen successor output is
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_deployment_kernel_compute_norelax_20261112_01`.
Its `receipt.json` records the object/header/build-fragment hashes, immutable
source-pin manifest hashes, relocation audit and opcode comparison. The delivered
object is `module/sdk/ara_resident_compute_core.o`, SHA256
`8a665b9dee914ef2cc03ac25f16275cd912335e75fd019100ddaff4cece00b28`.

The norelax successor changes build policy only: no computation source, attention
algorithm, exponential implementation or user-mode SDK algorithm changed. All 235
extracted 32-bit FP/vector/custom instruction encodings are identical and in the
same order in the old and successor cores. Their common sequence SHA256 is
`0f8ada106d1be2a96bca79b397d6df8a7a610d619f0cbc2e1e0c15e5c4f39d89`;
`fp-vector-custom-diff.txt` is empty. This static comparison is not a new numerical
or runtime acceptance. The previous 3.9M-input math checks were not rerun.

The parent's `resident_deployment_module_20261112_03/result.json` records successful
full Linux 6.19.6 Kbuild linkage with this exact core. Its module SHA256 is
`8c276508542875b0d7b107947399a3eae4386f73659fbc71366aaa946aa444b4`.
Linux boot and VCS successor outcomes are separate parent-owned evidence; this
receipt does not claim either passed or establish board acceptance. Original
Kbuild, old core, snapshots and reports remain unchanged. This README update is
documentation-only and is not a pinned input of those successor consumers.

## Scalar Exponential Provenance

`kernel_expf.c` is LGPL-2.1-or-later, adapted from local GNU libc 2.42
`sysdeps/ieee754/flt-32/e_expf.c` and `e_exp2f_data.c`, with the license in
`COPYING.LIB`. The source distribution is
`glibc-2.42-51-gcbf39c26b25801e9bc88499b4fd361ac172d4125` under the supplied
Buildroot tree. It retains the generic `TOINT_INTRINSICS=0` 32-entry table,
double-precision range reduction and cubic polynomial, F32 final rounding and
underflow flags, with no errno/TLS. Both reference and port use FP contraction
off. Only the nonpositive rescale domain is defined, not general-purpose expf.

The SDK's existing RVV exponential polynomial is unchanged. Host validation
compiles the original local glibc source/data with standalone alias/config shims
and compares more than 3.9 million nonpositive inputs bitwise and by FP exception
flags. Separate tests enumerate all 65536 F16 data/mask bit patterns and all 6144
supported shape preparations. These are not target vector execution tests.
