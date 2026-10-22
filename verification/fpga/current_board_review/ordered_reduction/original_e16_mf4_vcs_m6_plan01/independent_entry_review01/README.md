# Independent M6 entry review — original e16/mf4 single

**NOT CLEARED: one P2 / medium checker-scope blocker.** The checker permits
extra reduction retirements from the interiors of the other two helpers while
reporting the exact-single scope as passing. This is a host protocol finding,
not a newly observed DUT failure. Review grants no launch authority.

Reviewed `../prepared01/plan.json` SHA256:
`a9a60cc30f3d88d4b15441ec3d2da2bd7367f9334c9cb36731b262bbade50d3e`.
All **733 pins** matched independent SHA256 computations before and after the
host review. No producer code, sealed input, RTL or reference evidence changed.
Only this review directory and its temporary host fixtures were written.
No DUT, compiler/build, Spike/reference execution, producer prepare/run,
service launch or live process/service/resource query was performed.

## F1 — P2, unexpected alternate-helper target retirements can pass

Locations: `../checker.py:99–106`, `:138–164`, `:180–188`.

The global PC/encoding check admits any instruction present in the actual
ELF. The explicit alternate-helper exclusion at line106 rejects only the
**entry PCs** `symbols['op_1']` and `symbols['op_2']`. The21-instruction
sequence/count check applies only to op_0's lookup. Consequently, a retirement
at an interior target PC in op_1 or op_2 is neither counted nor rejected.

Two independent synthetic mutations retain the entire positive fixture and
insert one matching CVX request/response/retirement after the144-byte original
oracle and before CTRL exit:

| Unexpected retirement | PC / encoding | Generic validator | Strict checker |
| --- | --- | --- | --- |
| op_1 `vfredmin.vs v24,v8,v16,v0.t` | `0x80000754` / `14881c57` | PASS | PASS |
| op_2 `vfredmax.vs v24,v8,v16,v0.t` | `0x800007a4` / `1c881c57` | PASS | PASS |
| op_1 entry, control negative | `0x80000728` / `008072d7` | PASS | REJECTED: Unexpected helper/trap |

The two accepted mutations still report `target_calls=1` and21 helper
instructions even though another reduction has retired. Row/order/cycle counts
match between the generic and strict validators. The full `checker.artifacts`
gate is also exercised with synthetic protocol logs/provenance and a private
copy of the exact pinned ELF; no ELF is executed. See
[extra_helper_evidence.json](extra_helper_evidence.json) for its outcome.

This does not assert that the unchanged program normally branches into those
interiors, nor that current RTL has that fault. It establishes that unexpected
architectural trace evidence outside the promised original-single scope can
be accepted. A post-oracle reduction need not invalidate the already-completed
scalar oracle or its PASS marker, so those checks do not close this hole.

Before exact-single acceptance, exclude all retired PCs in the nonselected
helper windows, or enforce explicit zero counts for every nonselected
reduction target plus an appropriate helper-range policy. Add these interior
target mutations to the successor's rejection tests. Preserve this sealed
plan; this reviewer made no implementation change.

## Reference, source and ELF identity

The entry binds the actual independently accepted files, not a nonexistent
audit filename:

- `original_e16_mf4_reference_audit01/REVIEW.md`:
  `d9ad719158b37c9a1c1788b1e44fab5f84f06bc0d50a601128d8322cee91dc4c`.
- Its `result.json`:
  `a0cfeb4214f5569092f6acf9cfd4c9539e275b5699e319aa2e36e0d567ba8678`.
- Reference READY:
  `f858249f61dc7b9c4e3507f78bb483543d0439ef74942e838fc1251931a661de`.
- Canonical sourceproof:
  `f6efe2b2b360e96d4caa69fef05764bf205040f6c7347033e01cbd19562185af`.

The actual `rv64gcv_zfh_zvfh_zvl1024b` profile and its extra explicit Zfh are
retained. The code requires `profiles_exact_equal is False` and accepts only
this concrete single-reference result, not an exact minimum-profile run or
DUT correctness. The independent reference review's zero scalar-FP consumers
and source-faithful oracle are read as existing evidence, not rerun here.

SoC ELF SHA256 is exactly
`eed20f08a98ac66766a66810b6f5f8fc829d0603477d37b3d59d48c32669f162`.
An independent ELF64 program-header reader checked all **648** instruction
encodings in the generated specification against bytes in that ELF. All
three21-instruction helper windows were also checked byte-for-byte against
the archived scenario ELF. No fixed Spike-to-SoC main-function offset is used.

The original C source and actual SoC disassembly retain the selector
scenario3/l4/mode3/rm0/op0/sticky0 and surrounding loops. With cap16, the source
counts are input128, seed512, mask215040, output initialization144, and3360
fixture rows/two fields each. The selected bank1 row1545 is flat row4905,
`0x7e00/NV16`; bank0 row1545 is a different `0x7c00/0` fixture.

## CSV and oracle review

The checker independently requires the ordered6720 fixture field reads,
exact bank/address/value/load widths; full selected input16/seed64/mask64/
output144 setup; a0..a7 argument pointers/values; and all21 op_0 instructions
consecutively. Setup is alternating +Inf/-Inf, +Inf seeds and mask0x24.
VL/capacity returns64/16/8/64, saved frm/fflags0, requested CSR operands0,
NV16, returned vstart0, packed flags16<<32, and zero-operand original CSR
restore retirements are checked. The actual target is SoC PC `0x80000704`,
encoding `0c881c57`.

All144 LBU reads occur after the completed helper, in exact address order:
output[8:10] is little-endian0x7e00, the126 remaining destination bytes and16
guard bytes are0x5b. CTRL exit at0xd0000000 must write full-width zero; only
the original no-effect park may retire afterward. The checker does not claim
direct vector payload visibility from this scalar architectural CSV.

Frozen producer references under
`/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen/sources/`:

- `hardware/tb/ara_commit_monitor.sv:88–89,247–286` emits decimal cycles/order,
  original instruction/PC, scalar masks/data and trap. Shared cycles across
  retirement ports are correctly permitted by the checker.
- `hardware/deps/cva6/core/cva6_rvfi.sv:178–179,288–295,319–350` records byte
  enables and unshifted scalar store data with the LSU address. The checker's
  byte-enable shift and low-byte extraction match this format. A completed
  historical M4 trace corroborated nonaligned SB and compressed park fields;
  no active trace was read.
- `hardware/src/ara_soc.sv:628` boots from DRAM; the SoC CSV starts at the ELF
  entry, unlike the five Spike boot records in the reference audit.

The frozen full-trace validator additionally checks request/response/uop
consistency, complete sequence/order and unknown events. The added artifact
gate rejects any CVX exception and cross-checks total rows, final cycle and
retirement count. F1 is the remaining scope hole; these checks do not reject
a balanced extra request/response at an otherwise valid alternate-helper PC.

## Raw failure, cancellation and launch gates

Both raw console and `work/run.vcs.log` must contain exact original/wrapper/
simulator completion, without failure/DETAIL, and private input/command/image
provenance must match. The actual partial `RVV_FP_REDSPECIAL_DETAIL` marker is
added to the frozen monitor's FAIL_RE; a host-only Python subprocess printing
that prefix was killed immediately by the real monitor, well before its
timeout. This test did not execute simv.

Strict-check exceptions set the shared abort event; late cancellation changes
PASS rows to CANCELLED. Final checks require COMPLETE/PASS:1, exact membership,
rc0, jobs1/timeout5400, matching summary and all required artifacts. The disk
plan is freshly hashed and reread at `replay.py:67–69,217`; all source/image/
helper/reference pins and parent-review hash are then checked again. Loaded
project-module paths matched the pin set, excluding this review harness.

The frozen executor joins workers before terminal publication. The inherited
publisher's last `sigpending()` snapshot (`gather_repair05/regression.py:276`)
is the effective final signal decision: independent real SIGINT and SIGTERM
injections before that query produced NOT_PASS; after-query injections
preserved PASS as after-decision events. Signals are blocked across terminal
serialization/rename, with a second query after serialization. This is not a
promise that every signal until rename revokes the terminal result.

No software or hardware build is on the execution path: RunOptions uses an
explicit frozen M6 simv, skip_build=True, jobs1, commit_trace=True,
timeout5400, no FSDB. A new pinned parent authorization must name this plan,
unit/reference review and explicitly accept the budget risk. Fresh launch.json
and absent replay output prevent retry/overwrite.

`owner_gate():122–145` requires direct MainPID and exact cgroup/unit identity,
active/running service, RuntimeMaxUSec6600, KillMode=control-group and no restart.
The service query constructs a trusted explicit user-bus environment. The
prepared command starts the Python worker directly. Resource admission counts
comm-or-argv0 simv once, enforces cap24/MemAvailable32GiB, adds jobs1 and only
the supplied unused external reservation. Sealed `reserved_slots=0` requires
the parent's coordination to be accurate; this review did not establish any
current capacity or service state.

Budget5400/6600 is unchanged and has no automatic extension. The47-minute
estimate is planning evidence only: at273 retirements/s the reference work
would exceed the case bound. Timeout remains incomplete. No throughput or
DUT completion guarantee is inferred from the reference or host checks.

## Host audit and evidence

All **31 supplied host tests** passed independently. Their temporary fixtures
were redirected into this owned review directory; checker behavior was not
patched. Four added rejection cases (trap, backwards cycle, saved fflags,
park encoding) and four real signal-boundary cases passed. The interior-helper
mutations above expose a coverage gap not exercised by those31 tests.

Host01 and Host02 remain pinned HOST_FAIL draft evidence (0 tests/1 setup
error;31 tests/23 errors). Host03 is the current31-test PASS. Their history is
disclosed and was not overwritten or represented as DUT retries.

- [host_review.py](host_review.py), [host_tests.log](host_tests.log),
  [evidence.json](evidence.json): independent identities, supplied tests,
  ELF-byte checks, extra negatives, actual signal tests and module closure.
- [extra_helper_repro.py](extra_helper_repro.py),
  [extra_helper_evidence.json](extra_helper_evidence.json): balanced alternate
  helper-interior mutations and entry control, all synthetic host protocol.
- [findings.json](findings.json): conclusion and exact F1 references.

No reference acceptance is withdrawn by this entry-checker finding. No other
blocking discrepancy was found in the reviewed source, raw gates, budgets,
late pins or service/authorization path. Requested launch remains on hold
pending resolution of F1 and the parent's separate authorization/admission.
