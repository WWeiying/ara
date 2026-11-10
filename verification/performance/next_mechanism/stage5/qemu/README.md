# Stage5 Native AKV QEMU Successor

Status: implementation for source review. No QEMU build or guest execution has
been performed for this adapter. No RTL, FPGA, cycle, or production-admission
claim follows from this architecture model.

## Ownership and Scope

- Bacon owns `akv_model.[ch]` and its host tests: per-hart lifecycle, descriptor
  validation, RAM snapshots, replay mapping, resident validation/order, exact
  NaN-preserving widening. Callback interface is defined in `akv_model.h`.
- Adapter owns `Xaraakv.decode`, `trans_xaraakv.c.inc`, `akv_helper.c`,
  `ara_stage4.[ch]`, `overlay.py`, `recipe.py`, and `test_adapter.py`.
- Finite native subset: F16 v1/v2, D64/96/128, up to eight resident query rows,
  v2 tiles up to 64 tokens, row/single-column/panel4 replay, resident QK/PV.
  GQA and prefill use the same query-row/lifecycle primitives, not a second
  attention executor. D256 capability remains absent; callers retain fallback.
- `xaraakv` and `xaraakv-resident` are distinct default-off QEMU controls.
  Both are required for resident instructions. INFO index 4 remains zero.
  The opt-in switches are not a platform permission or production capability.
- This successor is limited to little-endian-host TCG, VLEN1024 execution.
  Unsupported VLEN discovery returns zero. Migration/save/load is rejected
  when AKV is enabled. Acceptance runs use one hart and one owned context.

## Numerical and Fault Contract

QK `0x0605705b` has no vector source or old-destination dependency. The model
uses exact F16-to-F32 re-encoding, preserving signaling NaNs, then dimension-
ordered FP32 fused multiply-add from positive zero. PV `0x0485705b` reads the
prepared logical vector-register payload and uses token-ordered FP16 fused
multiply-add. PV_PREP remains real guest assembly and its flags remain separate.
All ordinary vector, scalar, reduction, conversion, and GNU libm instructions
remain QEMU guest execution; there is no host attention/libm replacement.

The callbacks clone the target SoftFloat status, set the resolved FRM0..4,
clear only the clone's exception flags, and return newly accrued architectural
flags. Guest sticky flags are ORed only at successful completion; FRM, VCSR,
VL and VTYPE are not changed. Only active heads/tokens/dimensions enter FP.
QK validates query-base against actual loaded rows. Source/destination register
legality and disjointness are enforced by the model. Four destination registers
are clobberable, but unrelated registers and external memory must be preserved.

RAM callbacks probe translated, side-effect-free RAM and reject ROM/MMIO; they
never use a device callback as a fallback. FULL/REFILL invalidate before any
possibly-throwing memory callback and publish ready state only after complete
payload copy. Replay/resident commands cannot re-read external Q/K/V memory.
Frontend illegal-instruction and backend validation tval must match the RTL
distinction; guest memory exceptions preserve QEMU translation fault semantics.

## Frozen Base and Recipe

Base is `OUT/qemu-context-20261023-01/qemu-10.2.0`, not the live SDK or another
QEMU tree. `OUT` means the sole signoff worktree's `verification/out`.
The archive is available at `verification/qbs/qemu/build/qemu-10.2.0.tar.xz`.

- Archive `qemu-10.2.0.tar.xz` SHA256:
  `9e30ad1b8b9f7b4463001582d1ab297f39cfccea5d08540c0ca6d6672785883a`.
- Accepted QBS manifest SHA256:
  `6c4dad29c87d518a59adbe3ba92a24be7e3e1203157f519324b91f2337a7e9f9`.
- Accepted QBS binary SHA256:
  `37e3b4c100c3e8fbb7a248f3a0ab328797285dfe59e285fcf8540a14bd5b8e4c`.

`recipe.py identity` is read-only. After peer review, `prepare --archive PATH
--reviewed-inputs-sha256 SHA --output OUT/stage5_qemu_prepare_ID` verifies the
archive, manifest, binary, and inherited source pins. It extracts a fresh tree,
overlays only manifest-verified frozen sources, applies exact-anchor integration
edits, adds these new files, emits `xaraakv.patch`, and checks unchanged QBS
implementation bytes. No pinned tree is modified. No automatic download occurs.
Preparation also binds Bacon's frozen host02 receipt, source pins, and logs;
that evidence covers callbacks/layout, not SoftFloat or native execution.

After preparation review, `build --prepared PREPARED
--reviewed-prepare-sha256 SHA --service stage5-qemu-build-ID.service
--output OUT/stage5_qemu_build_ID` uses the reviewed
recipe and source inventory. Configure is bounded to 900 seconds and Ninja to
1800 seconds with four jobs. Commands, PID, cwd, timeouts, logs and exit status
are retained, including failures. Success says only `BUILT_NOT_EXECUTED`.
Exact source/input membership, including directories and symlink targets, is
checked before and after build; added files are not silently accepted. Compiler
commands receive an explicit minimal environment with fixed system PATH, an
empty private HOME/TMPDIR, and no inherited compiler, include, Python or pkg-config
overrides. No source-generation exception is currently granted.
No guest launch is implemented in this recipe. Source-only adapter tests use
`python3 -B test_adapter.py`; they are not numeric/native-execution evidence.

The build must be the direct MainPID of the named user systemd service. The
worker verifies its invocation/cgroup/MainPID before work and once at completion.
It stays alive waiting for each compiler command; process groups only support
bounded cleanup, not escape from the service control group. Parent launches
after source and preparation review, for example:

```
systemd-run --user --unit=stage5-qemu-build-ID --collect \
  --property=KillMode=control-group --property=RuntimeMaxSec=3000 \
  --property=StandardOutput=append:OUT/stage5_qemu_build_ID.service.log \
  --property=StandardError=inherit \
  /usr/bin/python3 -B PREPARED/inputs/recipe.py build \
  --prepared PREPARED --reviewed-prepare-sha256 SHA \
  --service stage5-qemu-build-ID.service --output OUT/stage5_qemu_build_ID
```

Expand the absolute paths before launching. Confirm the real compiler once,
then inspect terminal evidence after completion, without repeated polling.

## Unchanged Stage4 ELF Transport

The optional `virt,x-ara-stage4=on` machine property adds only fake UART byte
writes at `0xc0000000` and Ara control registers at `0xd0000000`: raw EOC value
0 means pass, any nonzero value fails; DRAM start/end are offsets 8/16.
The opt-in reset ROM sets unlocked PMP0 NAPOT/R/W/X, then jumps to the unchanged
ELF at `0x80000000`. This is necessary because frozen crt0 writes pmpaddr0 but
not pmpcfg0 before entering U mode. It does not grant AKV RAM eligibility.
ELF bytes, linker layout, libm, inputs, and result records remain unchanged.

Proposed bounded-run arguments, not authorization to launch:

```
-M virt,x-ara-stage4=on -accel tcg
-cpu rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true,xaraakv=true,xaraakv-resident=true
-smp 1 -m 16M -bios none -kernel SEALED_ELF
-display none -monitor none -serial none -chardev stdio,id=ara-stage4
-trace enable=akv_arch_* -D FRESH_TRACE
```

Use an independent bounded runner with explicit expected exit/terminal records.
Frozen crt0's mtvec is unsuitable for recovering unexpected exceptions; fail on
unexpected CPU traps and preserve the first failure rather than retrying.
Directed negative firmware must install its own real trap handler.

## Required Gates Before GGML/Model Runs

1. Directed native lifecycle/fault/flags tests: v1/v2 FULL, REFILL retaining Q,
   RELEASE/reset, descriptor and RAM faults, frontend versus backend rejection,
   recovery, row/panel replay, T1/2/3/17/64, H1/2, D64/96/128, valid/invalid query
   bases, inactive exceptional values, FRM0..4, incoming sticky flags, vstart,
   register overlap, extension disabled, capability4 zero, D256 rejected.
2. Exact perf02 ELF SHA256
   `a87b62b49d9f2a6bb5b4234306549b7c7ae06066b391be47542f025e0b3ef4bf`:
   four ABBA calls, 1024 output words, 482 legacy and 12 resident commands.
3. Exact functional01 ELF SHA256
   `67ff3a891db35b1689f1436d2be483fd0ca86375c0738860227fcc411ed33a74`:
   18 calls, 2816 words, 713 legacy and 30 resident commands, including H1/GQA
   tails and non-RNE same-policy fallback. Both builds live under
   `OUT/stage4_features_full_call_build_{perf_20261110_02,functional_20261110_01}`.
   Reuse frozen `check.py` numerical/guard/CSR checks and target02 oracle without
   modification. Discard QEMU-derived timing fields; never label them RTL cycles.
   Cross-check architectural begin/end/read events with expected actual opcodes,
   PC ranges, control words, lifecycle ordering, memory bytes and local flags.
   Do not synthesize missing RTL lease/barrier events from these atomic helpers.
4. Native QBS smoke on the **new executable**, including DIRECT/FILL/REUSE/RELEASE,
   profiles, tails, invalid-domain rejection and flags. Unchanged source bytes
   alone do not establish successor QBS binary acceptance.
5. Only then actual GGML graphs and real model data with emulation disabled,
   explicit trusted platform admission and observed resident instructions. These
   require their own build/library identity and are not proved by SDK ELFs.
