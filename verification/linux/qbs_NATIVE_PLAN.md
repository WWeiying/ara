# Linux QBS Native Prerequisite

Scope: single-process, single-hart Linux QEMU compute only. No AKV emulator,
RTL/FPGA proof, ZCC, synthesis, board run, full model, or OS context signoff.
OS_CUSTOM_CONTEXT=NOT_VALIDATED remains mandatory in every result.

## Fixed experiment

- Reuse the arch-v3 QEMU identified in CUSTOM_RUNTIME_READINESS.md, existing
  QEMU-virt OpenSBI and Linux Image, and the trusted base initramfs.
- Replay Qwen2.5-1.5B Q4_K decode blk.0.attn_q.weight, M=1 N=32 K=1536:
  first 32 weight rows (27648 bytes), one activation (6144 bytes), first 32
  frozen GGML output values (128 bytes). No recapture or model execution.
- Pin full source capture hashes and validate JSON type/shape/stride/size.
  Freeze the cropped inputs and independent captured output before execution.
  Compare all finite outputs using atol=0.002, rtol=0.002, fixed in advance.
- Compile the unchanged shared QBS runtime/native executor plus existing
  standalone RVV quantization/dot helpers, without any privileged app runtime.
  A separately implemented host Q8_K quantizer freezes quantized bytes for
  a byte-exact guest quantizer check; it is not the output oracle.
- Allocate aligned ordinary Linux virtual buffers; check input/output guards,
  input immutability, descriptor ABI, actual native capability/profile query,
  a one-command DIRECT plan, and pre-execution capacity/alignment rejection.
- Three boots, each bounded to 180 seconds (inner debugger bound 150 seconds):
  native required; forced RVV fallback; extension disabled (auto fallback and
  required-native exit 77). No transparent fallback after native entry.
- QEMU has CONFIG_PLUGIN disabled. Host GDB helper breakpoints count executed
  helper entries, not translated TBs. A native PASS requires exactly one exec
  entry, guest callback success, changed output, guards, and frozen comparison.
  Entry counts alone do not prove retirement. No timing/performance claims.

## Discriminating evidence

| Hypothesis | Observation required |
| --- | --- |
| arch-v3 native compute works in Linux U mode | native query ABI accepts; one exec helper entry; callback returns; 32/32 outputs within frozen tolerance |
| software fallback masquerades as native | rejected by zero/missing exec trace or wrong guest path/callback count |
| extension unavailable | query SIGILL; zero helper entries; auto uses RVV; require exits 77, never native PASS |
| buffer/layout plumbing incorrect | exact quantization mismatch, reference mismatch, guard/input corruption, or descriptor/plan assertion |
| shared QEMU reference creates circular oracle | avoided: captured GGML output is pinned independently; qbs_ref.c is not linked into the payload |

No custom activation context FILL/REUSE/RELEASE, task isolation, migration,
signal/fault compute recovery, or multi-process state tests are attempted.
Trap recovery is restricted to capability probing. ABI and QEMU source hashes
are checked against the readiness fingerprints; source equality does not prove
a reproducible binary build. The exact executed ELF/QEMU/kernel/firmware and
all build inputs are hashed in new artifacts.

## Commands

Run from /home/wangwy/openproject/ara_dsa_verification:

```sh
python3 -B verification/linux/qbs_build.py
python3 -B -m unittest discover -s verification/tests -p 'test_linux_qbs*.py' -v
python3 -B verification/linux/qbs_run.py
```

All output and temporary files are restricted to the new
verification/out/linux-qbs-native-20260922 tree. Existing files are read-only.

## Execution Record

The initial boot stopped before qbexec because the harness mistook the planner's
command-size limits for emitted command dimensions. The shared planner sets
limits M=4/K-blocks=256 and qbs_plan_next clips these to M=1/K-blocks=6.
The corrected harness checks the emitted command and end-of-cursor explicitly;
qbs_plan_check.c is a host regression for this distinction. No shared code,
numeric tolerance, input shape, QEMU parameter, or timeout was changed.

The original failed payload/logs and pre-fix source snapshots remain at the
output root. The corrected three-case run is in attempt-02, created with:

```sh
python3 -B verification/linux/qbs_build.py --attempt attempt-02
python3 -B verification/linux/qbs_run.py --attempt attempt-02
```

All three cases passed in approximately nine seconds each. See
verification/out/linux-qbs-native-20260922/REPORT.md and
attempt-02/summary.json under that output directory for exact evidence.
Existing output directories are never overwritten; a future execution needs
a new attempt-N name. Re-running is not necessary to inspect these artifacts.
