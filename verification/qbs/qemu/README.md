# Xaraqbs QEMU Functional Model

This directory provides a QEMU 10.2.0 functional model for the `Xaraqbs`
custom extension. It is an architectural correctness model for software and
full-model integration, not a timing model.

The model implements `qbinfo` and `qbexec` on custom-2 opcode `0x5b`. The
extension is disabled by default and must be enabled explicitly with the CPU
property `xaraqbs=true`. The implementation consumes the canonical
`apps/common/qbs_abi.h` and `verification/qbs/qbs_ref.[ch]` files during the
build, so descriptor validation and numerical semantics remain aligned with
the RTL verification model.

## Build

```bash
cd verification/qbs/qemu
./build_qemu_xaraqbs.sh
```

The script verifies the official QEMU archive checksum, applies
`qemu-10.2.0-xaraqbs.patch`, copies the current QBS ABI/reference model, and
prints the resulting `QBS_QEMU` path. `QBS_QEMU_BUILD_ROOT` and
`QBS_QEMU_ARCHIVE` can override the build directory and source archive.

## Run

Use the binary as a normal system-mode QEMU and enable RVV plus QBS:

```bash
qemu-system-riscv64 \
  -M virt \
  -cpu rv64,v=true,vlen=1024,elen=64,xaraqbs=true \
  ...
```

With `xaraqbs=false` or with the property omitted, QBS opcodes remain illegal.
Enabling `xaraqbs` requires `Zve32f` (normally provided by `v=true`); QEMU
rejects an inconsistent CPU configuration during realization.
The model checks vector/FP state, `vstart`, destination-group alignment,
descriptor fields, supported profile/layout pairs, and guest-memory faults.
It reads all inputs before committing the destination vector group, preserves
the unused fourth destination register for `M=3`, zero-fills inactive output
elements, and accumulates command floating-point exception flags into `fflags`.

The nine supported profile pairs are:

- `Q2_K x Q8_K`
- `Q3_K x Q8_K`
- `Q4_K x Q8_K`
- `Q5_K x Q8_K`
- `Q6_K x Q8_K`
- `Q4_0 x Q8_0`
- `Q5_0 x Q8_0`
- `Q8_0 x Q8_0`
- `IQ4_NL x Q8_0`

## Full-model check

`run_qwen_native_check.sh` boots Linux under the QBS QEMU model and runs the
same Qwen2.5-1.5B-Instruct Q4_K_M prompt first with ordinary RVV and then with
native QBS opcodes. It requires byte-identical generated text and verifies
that both GEMV and GEMM dispatch execute Q4_K and Q6_K QBS commands. The
default environment is `${HOME}/llama/platforms/cva6-qemu`; override it with
`QBS_PLATFORM_DIR`. The llama binary, model disk, QEMU binary, work directory,
and log can be selected with `QBS_LLAMA_BINARY`, `QBS_MODEL_DISK`, `QBS_QEMU`,
`QBS_QWEN_WORK_DIR`, and `QBS_QWEN_LOG`.

Set `QBS_MODEL_FILE` to package a host GGUF into a private model image in the
selected work directory. In this mode the guest path is derived from the file
name, unless `QBS_MODEL_NAME` or `QBS_MODEL_PATH` overrides it. Set
`QBS_EXPECTED_PROFILES` to the profile names that must each execute at least
one GEMV and one GEMM. This makes the same check reusable for format closure
without modifying the guest program or an existing model image.
`QBS_FORMATS` passes a comma- or space-separated QBS format allowlist into the
native run. Formats outside the list use the ordinary RVV path, which is useful
for isolating one profile in a mixed-format GGUF. An unset value keeps the
normal all-format behavior.

The check takes tens of minutes under system-mode QEMU. Run it in the
background and inspect the final assertions after completion:

```bash
nohup verification/qbs/qemu/run_qwen_native_check.sh \
  > qwen-native-launch.log 2>&1 &
```

For example, a standalone `Q5_0` model check can use:

```bash
QBS_MODEL_FILE=/path/Qwen2.5-0.5B-Instruct-Q5_0-pure.gguf \
QBS_EXPECTED_PROFILES=Q5_0 \
QBS_QWEN_WORK_DIR=$PWD/verification/qbs/qemu/build/model-q5-0 \
verification/qbs/qemu/run_qwen_native_check.sh
```

The directed native regression additionally executes all nine profile pairs
with M1/M2/M3/M4 and an `N=35` tail. Its `MUL_MAT_ID` case runs a three-expert
`Q2_K` graph and checks expert routing and every result against an independent
dequantized scalar oracle. It also verifies that a three-dimensional weight
tensor with six rows per expert does not select the R4 QBS layout.
