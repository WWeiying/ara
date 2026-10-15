# Exact Slide-Up Owner Recovery

This is a new, offline-only successor. Original producer NOT_PASS, aborted=true,
service exit1 and collector NOT_ACCEPTED remain untouched. Simulator numeric0 is
durable, but is not by itself architectural acceptance. No simulator, reference,
build or RTL change is performed here.

## Measured Rejection and Static Cause

Original prepared01 records target call1200 (zero based), ordinal1201,
seed0/op19/li1/mode0/VL1/vstart0, helper8, retire771538, arch13209,
PC0x80000fd6/code0x38813c57, alloc0/done0. The actual original helper is
`vslideup.vi v24,v8,2,v0.t`. An arch_start is not a backend uop acceptance.

Frozen M9 dispatcher SHA
`c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d`
decodes unsigned VI offset at2329-2340 and suppresses ara_req_valid for
null_vslideup at5970-5978. Offset2 >= VL1 is locally acknowledged. The old
checker requires a backend owner solely when vstart<VL, which is too broad.
Its earlier strict.finish completed in control flow, but no strict report was
persisted: full numerical acceptance must not be inferred from that fact.

## Narrow Correction

The original Strict implementation is inherited unchanged for actual ELF
PC/code, source initialization, full514-byte oracle, fresh writes, guards,
vstart, startup/reset, CSR, exact13 helper windows, UART and CTRL exit.
Only the appended target owner required flag is qualified anew. The decoded
instruction must equal the actual source helper; only op19 with the exact
0x38813c57 encoding and unsigned immediate2 permits the additional offset>=VL
elision. No mask-based or general slide exemption exists. Optional owners are
allowed to occur, but every actual allocation still requires matching done.

The owner walk preserves retired/architecture pairing and the original exact
side-effect-free CSR replay rule. All five helper memory owners remain required,
including all-off cases. Expected target counts use the same exact opcode/VL
qualification rather than retaining the old vstart-only total.

Static original ordinal eligibility changes are1201..1206,2566..2571,
3931..3936 (18 total, VL1/2). Predicted required targets2592, helpers20475,
total23067. Op24 nonempty memory targets117 remain required. These predictions
are not a claim that the closed trace passes.

Short Host tests cover both empty lengths, VL3 completed and deleted target,
each deleted memory helper, slidedown, op24, incorrect encoding, forged required
flag, alloc/done mismatch, unchanged vstart elision, full static membership,
and the actual Strict.consume target append path. They do not substitute for
full semantic CSV validation.

## One Bounded Closed-Trace Audit

The closed CSV is327166937 bytes, original inode39499130028 and
mtime_ns1791991776504408226. Prepare records fresh exact stat and SHA, all787
original plan pins, inherited source/ELF/reference/image/import identities,
the failed receipts, raw console/command/private ELF and new checker/Host pins.
No CSV semantic parse occurs during Host or prepare. Binary digesting is not
reported as semantic checking.

One independent Hilbert entry review is required before `run`. The external
worker waits at most600s for one audit process, kills/waits on expiration, and
persists the actual wait rc before interpreting result.json. No retry or bound
extension exists. This budget is for a327MB closed trace, not the original
10573s DUT simulation. Exhaustion preserves NOT_ACCEPTED rather than extending.

The one pass combines lossless full six-event generic validation, inherited
full source numerical checks and corrected owner checks. Pre/post plan/pins,
CSV identity/digest, actual child0 and actual old service1 are all preserved.
Success is architectural offline recovery only, not old service success or
original Linux historical failure closure. Data/protocol error stops the audit.

Commands (no simulator executable is launched):

```sh
python3 -B recovery.py host
python3 -B recovery.py prepare
python3 -B recovery.py run --plan-sha256 PLAN_SHA --review HILBERT_JSON --review-sha256 REVIEW_SHA
```

Hilbert JSON binding schema: status=`NO_BLOCKER_ONE_CLOSED_CSV_RECOVERY_NOT_DUT`,
plan_sha256, checker_sha256, runner_sha256 and host_wait_sha256. The run directory
fullparse01 must be absent and is created exclusively. Original sealed files and
prior failed independent terminal review are never overwritten.

## Falsifiable Boundary

If the full actual helper/CSR ledger does not establish original VL1/start0 and
instruction38813c57, inherited Strict rejects it. A missing VL3 target or any
mandatory helper must still fail owner coverage. Generic transport must reject
lost/changed rows or unmatched tokens regardless of optional owner eligibility.
No additional waveform or point scan is needed to relax these conditions; the
user authorized one closed full pass after independent entry review precisely
because the original postcheck did not persist its strict report.
