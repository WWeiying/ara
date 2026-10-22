# Candidate04 NV Successor Acceptance

**8/8 PASS** on the existing sealed candidate04 image. These are new directed
controls, not archived original cases. Host464 checks and Spike8/8 PASS
preceded VCS. No RTL edits, old-pin changes, image rebuilds, FSDB, timeout
changes, or retries. The same frozen SoC ELFs recorded in the prepared manifest
were copied privately by the integration runner and verified after execution.

## Measured Results

All cases are e16/m1, VL32, vstart16, sticky NX=1. Inputs contain exactly one
NaN; finite background truth is nonperiodic. Every case reported zero data,
setup, CSR and flag errors, vstart_after0, and firmware tohost0.

| Case | Exact expected/actual fflags | Result | Wall seconds |
| --- | --- | --- | --- |
| prestart_snan_eq, lhs5 | 1 / 1 | PASS | 43.55 |
| inactive_snan_eq, rhs17 | 1 / 1 | PASS | 43.35 |
| active_snan_eq, lhs21 | 17 / 17 | PASS | 43.55 |
| active_qnan_eq, rhs21 | 1 / 1 | PASS | 44.75 |
| active_qnan_ne, lhs21 | 1 / 1 | PASS | 44.15 |
| active_qnan_lt, rhs21 | 17 / 17 | PASS | 42.65 |
| prestart_snan_le, rhs5 | 1 / 1 | PASS | 41.24 |
| tail_snan_lt, lhs37 | 1 / 1 | PASS | 45.35 |

The sum of per-case wall times is348.57 seconds, not a hardware performance
metric. No comparison with candidate03 was run in this successor task.

## Qualification Conclusion

The source-origin repair is compatible with exact NV qualification in these
eight discriminating cases. Prestart and masked-off sNaNs do not publish NV;
an active sNaN does. Active qNaN EQ/NE are quiet, while active qNaN LT publishes
NV. Ordered LE with a prestart sNaN remains quiet. No new flag other than
architecturally expected NV is permitted; NX, frm and vcsr remain unchanged.

The pure-tail case has its sole sNaN at37, outside the correctly consumed VL32
stream. It rejects accidental consumption caused by a +16 source shift, not
tail gating inside a partially consumed source slice. Pure-prefix cases have
no tail NaN. The independent finite-data oracle would expose9-10 wrong active
bits under the advanced-source model, so passing flags alone cannot conceal
the old source-origin defect.

This is bounded e16/vv coverage. It does not establish every width, LMUL,
scalar form, alias, backpressure schedule, or original Linux program. The
previous finite FP3 includes a separate vf control; no new vf NaN claim is made.

## Strict Terminal Audit

After terminal notification by the service output, an independent read-only
postcheck verified all8 names/order and COMPLETE/PASS counts, simulator and
runner returncode0, exact per-case oracle markers and firmware success,
absence of raw failure markers, private ELF/image identities, actual candidate04
commands with `+NO_FSDB`, and all701 plan pins without drift. Host tests also
reject contradictory PASS+FAIL, trap, fatal, and incomplete console text.

- [Complete result](vcs_candidate04_01/complete.json): `PASS_NV8_CANDIDATE04`.
- [Source/runtime provenance](prepared01/provenance.json).
- [Host464 checks](host01/results.json).
- [Spike8 reference](reference01/reference.json), ISA `rv64gcv_zvfh_zvl1024b`.
- [Reusable SoC manifest](soc01/programs.json), SHA256:
  `52d507e7f7eea80bf41f4f8714b72a46bd87475792b6f4f91e5427d849a62e2a`.
- [Plan and target PC/opcode/ELF pins](vcs_candidate04_01/plan.json), SHA256:
  `ae0bf4f5746944cf4d8a05b3033e3debe3706cd21479a153ebe7e3e39aa509b6`.
- Terminal SHA256:
  `c4c7713a67c2d97cd99b42c1822f1540f135bb7fdd15e85e373c4827229c14e4`.
- Candidate04 image ledger SHA256:
  `e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.

The one admission inventory recorded5 live/reserved slots and183.45GiB
available. Jobs1 and first-failure-stop were retained throughout; all8 passed
without invoking the stop path. No external job was modified.
