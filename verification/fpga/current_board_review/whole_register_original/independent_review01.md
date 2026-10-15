# Independent Review 01

Scope: `prepare.py` and existing `prepared01/`, reviewed 2026-10-11.
Read worktree AGENTS.md. Read-only source/hash/JSON/disassembly checks only;
no builds, host executions, Spike reruns, simulations, DUT launch, or RTL edits.
Parent DUT runner and its 30-minute budget derivation are outside this review.

## Replay Addendum: Prelaunch Conditions

The subsequent request expands scope to `replay.py` and the completed
`vcs_candidate04_01` dry run. Still no DUT launch or simulation rerun.

- **P1 conditional launch blocker: outer deadline has no enforcement here.**
  `replay.py:97` records 30000 seconds, but `execute()`/`work()` never consume it
  (`:108-142`). Per-case 5400-second bounds apply only inside simulator
  monitoring, not image checks, input-lock waits, or trace validation. Before
  launch, require a directly owning service with a 30000-second runtime limit
  and process-group/cgroup cleanup. No such launcher is in the reviewed files.
  This can be satisfied externally without editing the sealed replay helper.
- **P2 conditional admission limit:** `replay.py:126` inventories resources once,
  not per dispatch, and acquires no shared reservation lock. The named external
  reservations total 18; plus own6 gives exactly24 even when those campaigns are
  between jobs. This is sufficient under the parent's stated exclusive campaign
  roster, but not against later unreserved launches. Hold that roster fixed or
  use coordinated admission; a one-time pgrep is not a global concurrency lock.
- Full-sequence acceptance remains excluded: the explicit terminal status is
  `PASS_1134_IN_20_PARTITIONS`, appropriately narrower than original whole-run
  DUT PASS. This is not a blocker for the newly stated partition-only scope.

Replay checks: plan SHA256
`4026384e0a1bb8f3163c8f4604bfa08a95350b3d12e49f2bbafdbe5696a84269`
matches preflight; all927 pins match; every prepared file is included. Thus the
preparation-only generated-source sealing gap below is closed for this plan.
Exactly20 unique op partitions sum to1134 cases/366 skips; all dry-run results
are DRY_RUN; no launch.json existed at review. All cases have5400-second bounds,
six workers, commit traces, +NO_FSDB and the candidate04 frozen image.

Inherited checker/runner inspection confirms non-PASS and exceptions set the
cancellation event, queued cases cancel, and live private process groups are
stopped. Acceptance requires simulator rc0, zero-tohost success, $finish,
original count/case/replay markers, trace validation and unchanged identities.
Read-only in-memory fixtures passed: positive console, seven contradictory
failure markers, missing $finish, nonzero tohost and each missing oracle marker.
Markers use substring matching, not a structured exact-line count parser; the
current sealed programs emit the exact reviewed lines. No current false PASS
was demonstrated. This review did not execute the runner's simulation path.

Budget arithmetic only, using the parent's supplied measurements:
0x1ff20dd=33497309 instructions; 46.15s/23113 implies66884s serial,11147s
(3.10h) at ideal six-worker scaling, and3344s per average partition. Uniform
5400s timeouts allow21600s for four scheduling waves before other overhead.
The30000s envelope is plausible but neither a measured throughput guarantee nor
evidence every partition finishes within5400s under concurrent campaigns.
Preserve the full oracle and all20 partitions; do not retune after a timeout
without examining its evidence. Commit-trace I/O/validation also has a cost.

Reviewed replay.py SHA256:
`2914f54c1a2847e5318a462a543a81daee45cbdcd3e1fbe019800686e0ff909e`.

## Blocking Findings And Scope

- **Acceptance blocker: partitions alone are not the original execution history.**
  `prepare.py:148-151` proves tuple multiset equality, not state/ordering equality.
  The full loop is seed/op/mode/start; separate programs reset between ops and
  run all seeds of one op consecutively. `original/whole.S:612-614` preloads
  registers before establishing the requested vtype. For example, op16 in each
  full-run seed inherits op15's VILL; later seeds of isolated op16 inherit
  op16's e64/m1 mode3 instead. Input/output, v8-v15, v24-v31 and target vstart/
  vtype are reinitialized, so architectural expected results remain valid, but
  predecessor configuration and microarchitectural history are not preserved.
  Retain a separate full-run result for full-sequence acceptance. Neither the
  full port nor partitions establish original Linux/OS fault-restart acceptance.
- **P2: generated build inputs are not sealed by source_pins.json.**
  `prepare.py:119-143,174-184,204-206` pins external originals/runtime files,
  not their consumed copies, `case.c`, generated wrappers or debugger commands.
  Changing a prepared source after preparation leaves all recorded source pins
  valid, while existing ELF hashes still pass. Seal consumed inputs and execution
  metadata in a successor provenance record before treating sources as frozen.
  Current copies match; this is a provenance gap, not observed source corruption.
- **P2: archive identity is recorded, not independently anchored on rerun.**
  `prepare.py:116-125` accepts the current manifest hash and obtains both source
  and ELF expectations from it (`cases[0]`, without name validation).
  `operations.h` is hashed without checking its generator-derived content.
  Anchor the reviewed manifest digest and case name; validate the generated
  header. Current header and manifest pass independent checks below.

No demonstrated false PASS in the reviewed host/Spike snapshot. Its status
explicitly says NOT_DUT; promoting it to DUT PASS would be unsupported.

## Verified Evidence

- All 15 source pins match current files. Manifest SHA256:
  `4f7b897338c4ec18777e304e9790857a6a406b17ee021b3d5436fa1c3ff06091`.
  Both archived Linux ELF copies match manifest SHA256:
  `f6ca381157fa767ab774017136af26d139e5c4776a1e7771f062251bbb7a2ecc`.
  Copied oracle/generator/assembly/header/runtime/startup/linker files match.
- Generator assembly and operations header reproduce their archived copies
  exactly. Every op_0 through op_19 instruction-byte sequence occurs once in
  the original Linux ELF and is identical in all 42 prepared SoC/Spike ELFs.
  Real whole loads, stores and moves are present, not host emulation stubs.
- `wrapper.diff` contains only entry/I/O/exit/startup adaptation, a scope comment,
  and operation-loop bounds. Original 1024-byte input formula, three seeds,
  1088-byte output initialization/comparison, output+32 pointer, active-byte
  predicate, prestart/tail/guard checks and both vstart status halves survive.
- Independent enumeration exactly matches every `tuples.json` row: 1500 total,
  1134 executed, 366 excluded; the 20 partitions are disjoint and their union
  equals the full matrix. Executed counts in op order:
  `[60,60,60,60,60,60,60,60,60,60,60,60,45,60,60,60,48,48,48,45]`.
  Excluded counts:
  `[15,15,15,15,15,15,15,15,15,15,15,15,30,15,15,15,27,27,27,30]`.
  These retain the original exclusions, including all move/VILL combinations,
  start>EVL and start>=8*vlenb. They are not coverage of excluded behavior.
- Host metadata records 23 positives with rc=0 (VLENB 32/64/128 full runs plus
  20 VLENB128 partitions), and six negatives with rc=1. Logs agree. Negatives
  corrupt prestart byte32, active byte34, post-active byte160, prefix byte31,
  post-vstart or pre-vstart readback. Each reports exactly three errors across
  three seeds. These test the oracle, not instructions or DUT exit plumbing;
  host logs/binaries themselves are not hashed in the completion record.
- All 42 ELF hashes match both programs.json and complete.json. All 21 Spike
  reference ELF/log hashes match; each log contains exactly one expected oracle
  count line, case PASS and replay PASS, one `0x0000000000000000`, no FAIL/TRAP.
  Debugger commands bind to the matching ELF's replay_exit and replay_log.
  Startup reaches replay_exit with raw a0; Spike then encodes HTIF success as 1.
  `command()` requires process rc=0, though rc/argv are not separately persisted
  per reference. No dynamic instruction trace/count is stored: real instruction
  presence and normal source call paths are verified, not retired-op counts.

Reviewed prepare.py SHA256:
`9d68d255b61ae8658e6f6e378c7ca2ab05fefc50777bdadadcda9506fcdd61de`.
Only this review file was written by this reviewer.
