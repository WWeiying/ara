# Fixed Selected2 Independent Review

Read-only review of Tesla's final `fixed_restart_original/candidate04_plan01`.
No Tesla file was edited; no host tests, dry-run, inventory, or DUT was launched
by this review. Existing host/dry-run evidence was inspected, not rerun.

**Conclusion: no blocking runner defect found for this exact two-case plan.**
Parent authorization and external service configuration remain required; this
review does not authorize launch or claim DUT acceptance.

## Reviewed Identity

- Plan SHA256: `9a31f50d44c245bc7439db5a462bac3eed54c2eecae74ffeae5931d3ea6995f0`.
- `replay_selected.py` SHA256: `8e005917ec3742853e823189aa54774dd5965ab82c6ed7ae218fff84cef339c1`.
- M4 image ledger SHA256: `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
- All **807 plan pins independently rehashed, zero mismatches**. This includes
  inherited source/ELF identities and frozen image/source/helper identities.
- Existing host gate: 11 PASS; pinned log SHA256
  `188856f062f100dd5a4824cf72d7ed2f2969ccd29a74d7aa0830af3ae9a77ab6`.
- Existing dry-run: exact `fixed_e8_m4_single776` and
  `fixed_e8_m4_pair775_776`, both DRY_RUN, jobs2, frozen M4 simv path.

## Acceptance and Work Path

Source selection preserves original RNG, initialization, scalar oracle, and the
24-instruction helper; it explicitly skips earlier vector history. Plan entries
retain selected01 ELF hashes and source markers: single776 has VL512/start256,
control0; pair775-776 has start1/control7 followed by start256/control0.
Pair expected sticky-vxsat values are1 then0, not a blanket final-zero assumption.
The fixture RNG has no min-times-min pair; no fresh numerical oracle is substituted.
Reference costs are477331/371229 instructions, not the full777-prefix cost.

The worker verifies explicit approved plan/review hashes, actual fixed-unit cgroup,
all input pins, loaded local-module pins, M4 image files and compiled-source
manifest before execution, then verifies identities again before publication.
It requires a fresh run directory and creates `admission/` before per-case writes.
Frozen integration runner is reused without rebuild, with two jobs and1800s/case.

Raw scanning includes RVV_MATRIX_FAIL, RVV_MATRIX_FAILED, FIXED_*FAIL, trap and
framework fatal/error markers. Exact original count/pass markers, exact selected
trial sequence, simulator success/$finish and zero return code are required.
The inherited runner additionally checks its raw run log and input provenance.
The private ELF hash and exact PRELOAD argument are checked. CSV audit requires
ordered non-trapping retirement, all24 original helper PCs/opcodes per call,
exact call count, VL, vstart, vxrm/initial-vxsat setup, returned vstart/vxsat and
restoration of saved CSRs. An extra or incomplete helper invocation is rejected.

Failure, timeout, log/trace/identity exception sets sticky cancellation. The
underlying runner stops private process groups; sibling work cannot publish PASS
after cancellation. Terminal acceptance requires COMPLETE and exact2 PASS names,
matching summaries/returncodes, and joined workers. Publication uses the reviewed
pending-signal/abort decision; PASS is not inferred from earlier individual rows.

## Launch Conditions and Residual Limits

No code change requested. Parent must supply an authorized review confirming the
actual FP-merge unit (template currently deliberately false), and launch unit
`ara-fixed-boundary-candidate04-01.service` with **RuntimeMaxSec=2400** and
**KillMode=control-group**. `outer_s` in plan.json is metadata, not a self-enforcing
timer or a check of systemd properties. The600s margin above the concurrent1800s
case limit allows teardown and CSV/pin validation; no guaranteed wall-time is
claimed. This external launch condition is not yet verified by this review.

Reservation accounting totals23 slots: whole6, NF7two, NF8eight, prefix5two,
FPtwo, FP-merge1, fixed2. It uses max(actual,reserved) per identified cgroup plus
unknown live simv, rejects totals>24 or memory<32GiB, and treats non-disappearance
process-read errors as failures. Preflight recorded23 and195179696128 available
bytes; that is historical preparation evidence, **not fresh launch admission**.
Both launch and per-case admission must still pass; no retry/cap escalation or
external-process termination is authorized.

This would accept only two source selections (three vector calls), not original
777-prefix, all matrix shapes, original Linux timing, or closure of the archived
stall mechanism. No current DUT PASS exists in the reviewed preparation artifacts.
