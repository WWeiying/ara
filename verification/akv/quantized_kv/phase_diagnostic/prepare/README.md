# Three-Call Q4 Phase Diagnostic Preparation

Owned preparation files only. No canonical, external llama, analyzer, old builder,
accepted ELF, or accepted six-call result is modified. No simulator entry point
is provided. The GNU build is a diagnostic static gate, not numerical execution.

The starting point is the accepted fixed-layout Q4 untimed verifier, admitted by
the unchanged `canonical_q4_hsb.run.checked_program()`. The source transform is
hash-locked and exactly invertible. It changes the trial bound from six to three,
the protocol prefix to `QUANT_DIAG_HSB_`, the reported trial count, and replaces
`repeats_exact=1` with `repeat_checks=0`. Only the first H/S/B entries in the
original order table execute. Its three unused mirror entries and dormant
repeat-check branch remain to minimize changes; they are not evidence of repeats.
All timed source, arithmetic order, callback implementations, real data/shape,
full golden tolerance, output/padding guards, FCSR/VCSR/work checks, and H/S
bit equality checks remain unchanged. There is one B call with eight native
commands, not sixteen; three full output records carry 2304 F32 words.

## Analyzer Interface

- CAP/BEGIN/RESULT use the original field order, with prefix `QUANT_DIAG_HSB_`.
- CAP reports `trials=3`; ordered BEGIN/RESULT pairs are `(0,0),(1,1),(2,2)`.
- Terminal marker is exactly
  `QUANT_DIAG_HSB_SUITE_PASS trials=3 outputs=768 rvv_exact=1 repeat_checks=0`.
- This is diagnostic-only. Never synthesize mirrored records to pass the old
  six-call checker. New checker/analyzer must require real three-call records,
  all output/gold/work/CSR checks, eight real QBS records, and actual UVM proof.
- The frozen primitive prefix retains unused predecessor protocol strings in
  rodata. They must never appear as executed records; their static presence is
  not a diagnostic repeat claim. The linked diagnostic namespace is checked
  independently, including its unique `repeat_checks=0` terminal string.
- `object-map.json` exports the new ELF's main instructions, both genuine rdcycle
  PCs, allocated sections, and preserved function boundaries. Use the actual
  retired PCs/call stack for phase attribution. A numerical PC interval between
  timer instructions is not a control-flow graph. No extra timer, instret read,
  UART call, or phase counter is inserted in the measured body.

## Build and Boundaries

Run from this directory:

```
python3 -B -m unittest -v test_prepare.py
python3 -B build.py --preflight-only --output "$PWD/out/preflight-02"
python3 -B build.py --output "$PWD/out/build-gnu-02"
Q4_PHASE_DIAG_ELF="$PWD/out/build-gnu-02/q4_hsb_phase_diagnostic.elf" \
  python3 -B -m unittest -v test_prepare.py
```

Only GNU dependency generation, main compilation, link, and objdump are executed;
each command is bounded to 120 seconds and its exit/argv/log is recorded. All
sixteen original nonmain objects are reused with exact hash checks. Main uses
the accepted `-ffp-contract=fast -fno-fast-math` policy; link retains its original
flags. No FP policy change or whole-program rebuild is hidden.

The fixed linker reserves the original finite main slot, rejecting overflow.
Data addresses/extents/payloads and all original nonmain function bytes/addresses
are checked against the accepted ELF. It does not promise identical main machine
code or cycles. A layout failure stops preparation and retains the failed build.
Dependency/source/tool/artifact pins are checked before and after GNU stages.
ELF allocated sections must leave 64 KiB stack reserve in the 16 MiB L2 image.

Timing still includes per-head query quantization, mapping/admission/K-copy on B,
online math, and final drain. Caller setup and output checking/UART remain outside.
This new three-call diagnostic has different warm state and compiler control flow
from the six-call experiment. It cannot replace accepted performance evidence or
claim repeat stability, pure-hardware speedup, whole-model timing, or PPA.
Image admission, trace selection, execution, and analyzer belong to later gates.

The retained first build compiled and linked correctly, then failed a too-broad
static string test that mistook an unused predecessor `repeats_exact=1` string
for the diagnostic terminal marker. The successor checks the complete diagnostic
namespace, with negative tests for wrong trial count, false repeats, old/extra
markers, data/primitive byte corruption, and missing timer sites. No program,
math, linker, or original artifact was changed to repair that checker mistake.
