# Full17920 M9 Worker Entry Review 02

Decision: **NO_BLOCKER_FULL17920_M9_ENTRY**, for the exact prepared02 plan and
ready command below. This is preparation acceptance, not permission to launch,
not DUT acceptance and not Linux closure. A separate parent authorization is
still required. The plan01 HOLD and all earlier failed receipts remain valid
historical records; they have not been rewritten as successes.

## Exact Binding

| Artifact | SHA256 |
| --- | --- |
| prepared02/plan.json | b6d0677124a045a35294a1c0be4a7b0f6a004f52e9f570e6e5b9478c4296bdbd |
| prepared02/ready.json | 89c37924aefdcca6ada87dfb1430ce0bc8e6853c4827297eec10340b37e1339f |
| prepare_launch02.py | 5658f8d6cd516aa34b626a27dd19d5c7a9ca988f2ee27ab16cd69112738ba37c |
| exit_hook02.py | f24761dc2b37c7b1c018bfd907e4c43dbe91d34a43fbf5d71e547fb50ea6a669 |
| collect02.py | a692a72a5c51a783d2a3f38e0eea1250599fbef2a341265198122a7183894477 |
| unchanged replay.py | 88d7d1472f9475f6a678b7e2e3c114816cc49cb72acf255cb20a0a9adf95f4ac |
| unchanged checker.py | c3e5f0847d652f2ac7939372e91002a8ee0c56dd32808333a6527228417172f5 |
| unchanged strict.py | 0bfc7055399b1b3bac8692d0469b617f8efc93f8f752ac67fe01d3ee31c7d485 |
| prepared02/dryrun_gate.json | 6cf438dad8c3e95af97e2485c2dd2b5bb8c746cd6d1a154ef0cf27284ea8ca6f |

Paths in this table are relative to
`../fp_compare_unboxed_full17920_vcs_m9_plan01/`.
The independent pin inspection exited0:750 total pins,749 non-raw files rehashed,
zero mismatches. All746 old pin values are preserved. The sole closed-reference
raw identity remains bound to its independently accepted reference receipt and
matching size, without another raw traversal. Four new pins are the three
successor scripts and the unused replay02.py draft; neither the ready command
nor the collector executes that draft. Plan changes are limited to pins and
service_terminal_contract. Host28, ELF, model, source and reference are unchanged.

## Service Lifecycle

The actual ready argv now has Type=exec, RemainAfterExit=no, RuntimeMaxSec13200,
KillMode=control-group and Restart=no. It executes the original replay.py directly,
not a wrapper concealing the worker PID. Existing runtime checks require the exact
loaded/running unit, MainPID equal to self, matching actual cgroup and13200-second
budget. Future startup evidence should additionally record the actual manager
RemainAfterExit=no property. No actual service state is claimed by this review.

The reviewed launch command no longer retains a successful unit as active(exited).
Normal main-process exit therefore enters the stop phase and runs exit_hook02.py
automatically. The hook first persists the actual SERVICE_RESULT, EXIT_CODE and
EXIT_STATUS environment, without GC fallback or inferred success. It checks its
own and the collector's bound hashes before starting one metadata collector.
The collector's180-second wait and actual numeric returncode are separately
persisted; TimeoutStopSec300 provides stop-phase headroom without extending the
10800-second simulator or12000-second worker deadlines.

The collector accepts only success/exited/0, full producer PASS, durable integer
simulator0 with no timeout/failure, exact one-case membership, no abort/retry,
unchanged input/evidence pins, complete original scope, paired owner counts and
matching source/generic row counts. Missing service fields, nonzero exits or
missing complete/report artifacts produce NOT_ACCEPTED, not fabricated numeric0.
It rechecks console failure vetoes and the actual runner COMPLETE metadata.
Its CSV identity is explicitly inherited from the producer's closed digest; it
does not claim an independent numerical re-audit or parse the CSV again. Consumers
must require both collector_result and actual collector.wait success rather than
assuming that merely creating a result file proves collector exit0.

The actual dryrun uses M9 simv, seed1, the accepted original SoC ELF and exact
runtime +TESTCASE, +NO_FSDB and private trace path. Its run metadata records only
DRY_RUN, jobs1, timeout10800, and the prepare/dryrun tool receipt records numeric0.
No simulator/build output was created. The original future real-run path still
copies and checks its private ELF and writes numeric child outcome before checking.

## Source And FPR Contract

The FPR chain and complete source/checker review in ENTRY_REVIEW01 remain valid:
M9 image66 members and14 frozen source files matched; each original FMV.D.X must
retire its correct SoC PC/code with rd0 and full64 zero-extended b[0], with a
separate validated t2 source. The10752 writes/336 per seed are **FPR committed
writeback**, not physical FPR readback or an accelerator operand snapshot. GPR
x0 remains zero and is not updated by these FP writes. Host02 actual28/28, exit0,
includes payload-to-zero, boxing/high-bit, wrong destination/source and missing
move negatives. No Host suite was rerun for the service-only successor.

The unchanged strict scope is17920 contiguous calls,286720 result bits,35840
guards,17920 flags/vstarts,734720 fresh stores,143360 input LD,17920 output LWU,
2240 record LD,326144 operation-helper instructions plus capacity3. Required
owners remain89600 memory and15360 nonempty targets;2560 VL0 targets alone may
elide. DK0 old5b5b, original allowed tails, all32 raw scalar seeds and full flags
oracle are preserved. CSR restore instruction/operand evidence is not silently
upgraded to an additional post-restore readback. Original output bytes4..129 have
fresh-initialization evidence, not a source post-result oracle absent from the C.

## Conditions For Future Launch

The parent run record should bind this exact ready SHA as well as the exact plan
and independent entry SHA; execute only that argv with the review/authorization
placeholders filled. The original worker verifies plan and independent/parent
approval identities, while the reviewed ready supplies the actual service
properties. This review does not authorize another argv or an unreviewed wrapper.
Fresh cap24/memory32GiB admission, jobs1, fixed10800/12000/13200 bounds and no retry
remain mandatory. Reference2653044 instructions are not a DUT runtime guarantee.

No service, DUT, compiler, reference or additional Host test was launched for this
review. No active trace or raw semantic parse was requested. Only metadata,
source, existing receipts, exact argv and file identities were inspected.
