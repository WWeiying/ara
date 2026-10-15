# M6 Original Unboxed265: Prepare Only

This is a thin scope adapter over the frozen merge98 execution framework,
not a new simulator runner. It imports the immutable reference instruction/setup/
oracle checker, adds CSV normalization and strict raw console veto. The owned
dut_strict.py is the reference checker with exactly one backend guard added:
in-memory console capture is Spike-only; SoC has no replay_log symbol and uses
the separately verified UART console. No architecture check is removed.
Host01's missing-symbol/import failures are retained; host02 uses the corrected
backend guard and loads the existing frozen Python dependencies first. Existing
runner performs private ELF copies, monitored immediate failstop, no retries,
COMPLETE checks, sticky cancellation, final fresh plan/pin validation and atomic
terminal publication. Imported module settings affect only this Python process;
no shared helper or sealed source is edited.

Exact original scope:265 natural calls/264 predecessors,cap16,op0..3 each56x17,
op4 41x19,4240 result bits,530 guards,265 flags/vstart; unused op5..9 entire PC
ranges rejected. Original unboxed fmv.d.x and fixture setup retained. Tail accepts
only original {old,1,wanted}, VL0 requires old. Strict DUT CSV proves actual scalar
oracle/CSR results, not unobserved internal FP operand buses. Reference raw separately
checks full vector source, result and store.

Fixed scope budget: one job,case5400s,service6600s (1h50m),noFSDB/noBuild/noRetry.
Actual reference701895 instructions: at273 retired/s with20% allowance about3085s;
at accepted same-family696/s about1210s. Neither proxy guarantees completion.
This is a new case-specific budget, not a change to any old plan/timeout.
Runtime admission checks cap24 and >=32GiB available memory, unused reservations
plus actual live workers counted once; preparation does not inspect live jobs.

Prepare/dryrun commands are recorded in prepared01/ready.json and dryrun metadata.
Only a later parent approval with exact plan SHA, READY SHA, independent audit+review
actual hashes, explicit budget acceptance and correct direct service owner can run.
The independent reference is pending at preparation; do not fabricate acceptance.
No launch has been performed. Parent/independent reviewer must confirm actual audit
schema before admission; an unexpected status/schema fails closed, never guessed PASS.

Host covers unboxed-zero wrong equality, tail-NV, sticky loss, VL0 preservation,
guards/vstart/missing oracle, target encoding, dead/interior helper execution,
source/argument drift, invalid exit, actual partial DETAIL immediate failstop,
late abort and fresh-disk-plan drift. Protocol fixtures are explicitly synthetic,
not a new Spike reference or DUT measurement.
