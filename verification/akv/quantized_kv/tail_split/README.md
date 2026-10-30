# Split-prefix tail closure (not a performance test)

Only this new directory is owned by this successor. Original C, helpers, RTL,
runtime, accepted image and failed worker evidence remain unchanged. No VCS run
is authorized by a build or host test result.

## Why split

Both `verification/out/akv-quantkv-tail-attention-{q4,q8}-20261024-01`
workers exhausted their explicit 7200-second simulator wall timeout. Both logs
contain five complete RESULTs with errors=0: visible5 ordinary/native/native,
then visible33 ordinary/native. Both begin visible33 trial2 and contain eleven
successful QBS records. Both end partway through the activation hex export of
`QUANT_TAIL_QK visible=33 trial=2 seq=11 m=4 n=1`. Command12, the sixth RESULT,
suite termination and final UVM acceptance are absent. These are TIMEOUTs, not
numerical PASS receipts and not evidence of an RTL deadlock.

Last logged CVXIF cycles are 7,581,674 (Q4) and 7,588,562 (Q8). Nearest preceding
CVXIF cycles at the first visible33 BEGIN are 2,747,308 and 2,758,101 respectively.
These are trace landmarks, NOT exact UART timestamps or measured trial cycles.
The traces demonstrate substantial completed work before the second prefix.
They do not establish the precise remaining wall time or rule out a later bug.

Diagnostic work is intentionally retained. Each prefix prints 18,432 output
hex characters (three times 768 FP32 values); QK activation and score hex adds
3,744 characters for visible5 and 9,696 for visible33, excluding record headers.
Per-byte/per-word printf and UART traffic are part of this correctness probe,
not Attention performance. Splitting removes the other complete prefix from
each simulator budget; it does not remove diagnostic evidence or widen the
default timeout. Completion within that budget remains to be measured.

## Exact scope

Four fresh ELFs: Q4_0/Q8_0 times visible5/33. Every ELF retains six real heads,
D128, physical capacity256, strided KV, RVV V decoder, production quantization,
ordinary trial0 and native trials1/2, guards, whole FCSR comparison, VCSR5,
independent host full-graph golden at the unchanged tolerance, all command QK
scores checked bit-exact against the pinned host oracle, and native repeat bits.
The host QBS reference is not linked into the target ELF. Command-level flags
and an independent query quantizer are still NOT established by this test.

`scope.render` permits precisely five source-line changes: single prefix list,
one prefix iteration, golden selection by visible value (essential for33), CAP
scope, and a distinct split suite marker. It keeps both gold blobs. Every build
saves the generated C and `scope.patch`; admission reconstructs and checks exact
source equality. Other predecessor objects are reused only with their existing
source/artifact pins. No FP compile flags or numerical algorithm changes.

Each ELF emits original BEGIN/QK/RESULT records, a CAP with `prefixes=5` or33,
and exactly:

```
QUANT_TAIL_SPLIT_SUITE_PASS visible=5 prefixes=1 trials=3 outputs=768 native_calls=2
```

For visible33 only the visible value changes. The checker consumes the actual
single-prefix log; it never manufactures the missing half of an old transcript.
Each format expects four commands for5 and eight for33, with N sequence
`5,5,5,5` or `32,32,1,1,32,32,1,1`. Complete scope is 12 trials, 24 commands,
eight native calls. Invalid/extra protocol lines, partial diagnostics, missing
UVM/core termination, changed Query, FCSR mismatch and repeat-bit mismatch fail.

## Build and check

From the worktree root (GNU toolchain is inherited and pinned):

```sh
python3 -B verification/akv/quantized_kv/tail_split/test_split.py
python3 -B verification/akv/quantized_kv/tail_split/build.py \
  --base verification/out/akv-quantkv-strided-attention-q4-build-20261024-01 \
  --gold verification/out/akv-quantkv-tail-gold-20261024-01 \
  --visible 5 --output verification/akv/quantized_kv/tail_split/out/build-q4-v5-02
```

Repeat with q4/q8 and5/33 using four distinct output directories. The accepted
16MiB image is reused only after source/image identity and ELF bounds checks.
`commands.json` records exact GCC, dependency, linker and objdump invocations.
The generated build state is `TAIL_SPLIT_BUILT_NOT_EXECUTED`, never PASS.

After parent review only, a direct-owned worker can invoke:

```sh
python3 -B verification/akv/quantized_kv/tail_split/run.py \
  --build verification/akv/quantized_kv/tail_split/out/build-q4-v5-02 \
  --prerequisite verification/out/akv-quantkv-model-strided-20261024-01-control \
  --output verification/akv/quantized_kv/tail_split/out/run-q4-v5-01 \
  --timeout 7200
```

`--preflight-only` checks build/model/image/manifest without starting simv and
produces only `PREFLIGHT_ONLY_NOT_EXECUTED`. Simulator timeout must be <=10800;
the default remains7200. Pre/post manifests and actual AXI/backend-write UVM
checks have separate bounded timeouts, so total worker wall time can exceed the
simulator bound. Do not start nested background children outside service ownership.

## Combined continuation prerequisite

`combine.py --runs <q4-v5> <q4-v33> <q8-v5> <q8-v33> --output <fresh-directory>`
requires four terminal PASS workers, rechecks each raw numerical/work transcript,
binds actual UVM/log/trace/ELF evidence, verifies all source/artifact pins, enforces
same accepted image/model prerequisite and Query bytes across prefixes/profiles.
It separately records the two old TIMEOUT receipts as prior-only. A completed
prefix of an old failed run cannot substitute for a fresh split acceptance.

Threeway continuation must require `combine.checked_combined(directory)` and
`acceptance=TAIL_SPLIT_COMBINED_PASS`, not any individual split PASS, old timeout,
or build/preflight status. The old threeway launcher is deliberately unchanged;
parent must wire this successor prerequisite before resuming it. No performance,
whole-model or clean-original-worker PASS is inferred.

Import the API as `verification.akv.quantized_kv.tail_split.combine` with the
worktree root on Python's path. Local modules use qualified names to avoid
collisions with inherited helpers named `check`/`run`. The initial four `-01`
ELFs built successfully, but standalone runner admission exposed such an import
collision; retain them as prior build evidence, not launch-ready pins. Fresh
`-02` builds and clean-process CLI tests cover the corrected successor.
