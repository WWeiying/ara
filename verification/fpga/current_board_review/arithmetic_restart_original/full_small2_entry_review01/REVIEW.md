# Full Small2 M6 Independent Entry Review

**APPROVE_FULL_SMALL2_M6_ENTRY, conditional on new parent authorization and
runtime resource/owner admission. No blocking finding in this exact plan.**
This is launch preparation, not DUT acceptance. No live-resource query or launch
was performed; no Host/dryrun, Spike, build or second reference raw parse ran.

Plan SHA: `7ec58e3f38f5877838c7edf898d4b85d4872437dcdc54e7542357e8f2736f9ee`.
Reference READY: `db878aa262c882af8cf32dfa803426382b3869c1a0f47662c4a434bd8b6439b6`.
All860 plan pins verified, including raw-file hashes (hashing only, no parsing),
source/model/reference reports, actual ELFs, M6 image/snapshot and dependencies.
Actual review child wait: rc0,7.883855s, no timeout, one attempt; see
process_exit.json and verified.json. The checked plan remained unchanged.

## Reference And Source Basis

Consumed the approved recovery fullparse outcome
`0edaf36f891f25675e9b8638f2d8a92eea3894e8f5916e345d5ee4ed36f465b3`,
its actual prior process wait0/153.626305s, both complete call ledgers and pinned
raw identities. This independent static source/checker/evidence review accepts
that reference scope; it is explicitly **not a new independent full-raw audit**.
Historical failed/interrupted audits and producer pending-review labels remain.

The original C bytes were not recovered. The source is a byte-equivalent original
reconstruction backed by the retained22-program recovery; do not relabel it as
recovered original C bytes. Reviewed reconstructed C versus Python model: RNG,
seed/op/length/mask/start order, division edge cases, reduction/compress semantics,
and e32 FP table transition agree. Runtime-only diffs preserve complete loops.
Actual SoC/Spike ELF instruction bytes match sourceproof code maps; each original
capacity/helper byte window uniquely matches the archived stripped Linux ELF.

Exact scopes: e8/mf8 has25 operations/4095 calls; e32/mf2 has35 operations/5985
calls; each retains3 seeds and cap16. All10080 ordered model/report calls were
cross-checked,161280 results,20160 guards and10080 returned-vstart checks.
No partition resets or prefix cut. This covers two shapes, not all22 or Linux.

## Checker And Worker

checker.py uses actual per-SoC PCs, full startup BSS order, unique capacity16,
actual vlenb128, complete13-instruction windows and exact model call order.
Every call checks a/b, physical128-byte mask and18-element sentinel setup;
all16 outputs plus both guards are checked once, including inactive/prestart/tail.
Scalar addresses, widths, byte enables and source registers are checked; RV64C
loads and signed LW results are decoded correctly. FP setup uses original bit
tables, not scalar FP conversion in these ELFs. No invented fflags oracle is
claimed. Original CSR startup/vstart effects and returned0 are retained.

SoC UART reconstructs the oracle console; CTRL requires actual exit-store PC,
64-bit raw0/a0=0, not Spike HTIF1. Only original park may follow. Generic frozen
trace validation remains required, plus strict raw log/detail/error veto.
Host03 binds current scripts and records14 PASS methods with full4095/5985-call
positives and scoped negatives. Host01 startup-register fixture errors and
Host02 unusable-store-site interruption are retained, not accepted as PASS;
actual SoC BSS discovery and usable Host assignment sites are in the final code.

The monitor wrapper fsyncs actual numeric child wait/timeout/failure/command
before every generic postcheck. Timeout evidence survives cancellation labeling;
checker failure cannot turn it into PASS. Sticky abort, no retry, late disk-plan,
all input/image/review pins, COMPLETE membership and private ELF/command checks
gate terminal publication. Expensive checks do not hold a deadline latch lock.
The timer is joined before the final elapsed-deadline/atomic publication gate.
Direct MainPID/cgroup,13200s service,KillMode=control-group,Restart=no and explicit
trusted user-bus environment are checked at run. jobs2/cap24 and memory admission
remain live parent/worker responsibilities, not findings from this offline review.

## Budget And Admission

Fixed case10800s, worker12000s including observers, service13200s, jobs2.
The measured M4 prefix proxy gives e32 nominal slow9564s; plus20% is11477s,
**677s over the fixed case budget**. Different M6/op mixes and postcheck cost
make completion uncertain. Parent must explicitly accept this risk; no automatic
extension, reduced oracle or retry is approved. A timeout alone is not RTL proof.

ENTRY.json supplies the exact worker reviews() schema and evidence pins. Parent
must separately supply AUTHORIZE_FULL_SMALL2_M6_ONCE, exact plan/entry SHA/unit
and budget_risk_accepted=true. This review does not authorize a DUT launch.
