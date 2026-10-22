# Prepared Handoff, Not Launch Authorization

`prepared01/plan.json` SHA:
`b2fb0d810d7004769a18c7b0527e14b013979791ace008edb4155240126bb586`.
1240 pins; Host `host01/status.json`: 29 PASS; `prepared01/dryrun_gate.json`:
exact10 DRYRUN_ONLY_NO_DUT. Draft01/02 were passing development tests, not
blocking DUT findings. The outstanding independent-review binding is resolved.

The exact worker argv and direct-owning systemd command are respectively
`command` and `service_command` in `prepared01/ready.json`. Substitute only
`PARENT_REVIEW_JSON` and `PARENT_REVIEW_SHA256` after parent entry review.
Unit `ara-nf2-remaining34-j4-m6-01.service`; RuntimeMaxSec27000, KillMode
control-group, Restart=no. Max3 total workers; unchanged per-ELF bounds in plan.
7.5h is the outer worst-case protection, not an expected elapsed time.

Parent review JSON required fields:

```json
{
  "decision": "AUTHORIZE_NF2_REMAINING34_J4_M6_ONCE",
  "plan_sha256": "b2fb0d810d7004769a18c7b0527e14b013979791ace008edb4155240126bb586",
  "unit": "ara-nf2-remaining34-j4-m6-01.service",
  "pilot_audit_sha256": "79037611e05a12289eb6734b836f8cbcb5c28658bd0a88f3002fc895d5bb51ee",
  "budget_risk_accepted": true,
  "independent_reference_pins": "COPY THE OBJECT FROM prepared01/plan.json, NOT THIS STRING"
}
```

This is a schema/example, not a written authorization. Actual independent
reference schema is `nf2_remaining34_independent_reference_audit_v1`, status
`ACCEPTED_REFERENCE34_NOT_DUT`. REVIEW/audit/group/source pins are all bound.
Pilot gate requires actual COMPLETE, exact persisted numeric child0 and raw
independent evidence; ERROR/null/console-only recovery cannot authorize dispatch.

No VCS, reference or compilation was executed in this runner directory; no live
simulation query was made. J4 uses old identical ELF and old observer with its
original b3/b5 contract, separately from the configurable remaining34 observer.
The two J4 positive controls are outside the source40 failure count. All ten
jobs must actually PASS before claiming remaining34 + J4 current-M6 acceptance.

`SOURCE_MASK_CORRECTION.md` separately records the original16B allocation with
source line/hash evidence; it does not alter old sealed docs or this plan.
Worker/checker/Host/plan are now frozen for parent review and execution.
