# FP32 Full17920 M9 Entry

Preparation only. No DUT launch is authorized by this directory or its ready
file. Hilbert's exact entry and a separate parent runtime binding are required.

## Identity And Scope

- Original failed parent: rvv_fp_compare_unboxed_unmasked_e32_mf2,
  source/hash-exact old FPGA handoff, not an invented replacement.
- Source port ELF: software01/execution01/soc/program.elf under the sibling
  fp_compare_unboxed_e32_mf2_full17920_prepare01 directory; SHA256
  520b652eb8a4d4dc634a17a36a9d5e71c382a4679afeb8aeb54746d18a37be73.
- Accepted sole reference: 2941812 firmware instructions, full17920, three
  actual numeric waits0. Its closed raw identity is inherited from accepted
  signed-by-hash metadata, not reparsed or rehashed here.
- Full17920 / 286720 predicate bits / 35840 guards / 17920 flags and vstart.
  Original185 instructions, 326144 dynamic helpers plus capacity3.
- Typed32 input banks each4096B: first64B fresh, remaining4032B retain exact BSS0.
  Each call49 fresh stores,16 inputLD, one outputLWU; totals878080/286720/17920.
  All128 mask and130 output initialized; the original output oracle reads4B.
- Required owner89600 memory +15360 nonempty targets=104960. VL0 target2560
  may be elided; memory helpers may not. Generic transport still checks all
  actual requests, responses, architectural instructions and alloc/done pairs.
- All10752 FMV.D.X committed FPR rd0 writeback payloads must equal raw32
  zero-extended to64; IGPR x0 remains0. This is not physical FPR readback.

## Runtime Contract

One case10800s, worker12000s, service13200s; jobs1, reserved0, fresh live cap24,
MemAvailable>=32GiB, NO_FSDB, no rebuild/retry. Service Type=exec,
RemainAfterExit=no, KillMode=control-group, Restart=no, TimeoutStopSec300.
ExecStopPost writes actual systemd exit facts before bounded180s metadata
collection, persists collector.wait numeric outcome, then terminal_event.json.
Unknown or missing exit facts cannot produce acceptance.

The private monitor preserves base FAIL_RE and additionally requires a complete
original DETAIL line with positive decimal errors and newline. Original lines
fit the mature256-byte carry buffer. Split-chunk matching is Host tested; the
full first tuple is durably preserved. Closed-console veto remains stricter.

The CSV is delivered losslessly to the mature generic observer and exact SoC
source observer in one semantic traversal. The terminal collector does not
repeat CSV parsing. Restore instructions/operands are observed; no new final
CSR readback is claimed. Source-port acceptance cannot close original Linux.

## Short Host Evidence

host01.wait.json retains actual1: an overly strict static check incorrectly
expected the dynamically assembled PASS line as a contiguous ELF string.
host01_sources preserves the pre-fix files. Runtime full-line oracle unchanged.

host02.wait.json retains actual1:34 methods passed; one assertion regex expected
"initialized" while upper-bank corruption was correctly rejected as
"Unmodified unused backing BSS". host02_sources preserves orchestration.

host_supplement.wait.json actual0 checks all6 subcases in that method, including
the previously unreached final b[4095] corruption. No production checker change.
host_final.json combines34 prior methods and this one corrected method, with
the original failures preserved. No source/full numeric Host, compiler,
reference, old raw or DUT was repeated.

## Entry

prepare_only.py/prepare01.wait.json preserve the initial preparation failure:
reference receipt bindings used Path keys, incompatible with the shared
string-key merge. No plan or DUT was produced by that failed invocation.

Active successor: prepare_only02.py runs the narrow typed-pin/actual-schema
contract tests, then replay_successor.py preparation/dryrun. The worker differs
only by string normalization of receipt keys and successor worker/hook/collector
names; test_prepare_contract.py verifies that exact text delta. Old worker,
all original Host results and the shared merge function remain unchanged.

prepare_only02.py records actual bounded preparation/dryrun waits.
prepared01/plan.json and ready.json bind the exact worker/checker, original
source, accepted reference, frozen M9 configuration and input/image hashes.
Do not substitute the historical original name for the source-port +TESTCASE.

Independent ENTRY_REVIEW.json schema consumed by replay.approval_gate:
decision=NO_BLOCKER_FP32_FULL17920_M9_ENTRY, plan_sha256, worker_sha256
(replay_successor.py), checker_sha256, strict_sha256, reference_review_sha256.
Parent runtime record requires decision=AUTHORIZE_FP32_FULL17920_M9_ONCE,
plan_sha256, entry_sha256, unit, budget_s=[10800,12000,13200], jobs=1.
These are future admission requirements, not assertions that either exists.
