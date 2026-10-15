# Checker event-order correction before entry seal

Host01 is a real checker defect, not merely a malformed synthetic fixture.
Its durable actual wait exit is1, elapsed1.1683934079483151s, nine errors.
`host.log`, `host_receipt.json` and `host01_source/lifecycle.py` remain intact.
No reference execution or reference raw log exists at this preparation stage.

The actual mode0 mask path ends at an SB. Old `Lifecycle.enter` incremented
the PC cursor and immediately tested full mask completion before the parser
delivered that same instruction's store. The last SB therefore had not
incremented `mask_cursor` or cleared `mask_pending`. Valid input failed at
old line73. Several negative tests also stopped at this earlier unrelated
defect; their old outcomes are not evidence of reaching the intended mutation.

Required delivery is `enter(PC, pre-registers) -> memory/register effects ->
leave(PC, post-registers)`. The corrected parser calls store/read/effect,
updates registers, then calls leave. The old phase completeness predicates
are unchanged and now run in leave, with an additional exact closing-PC
check. Missing the last effect still rejects; moving the check is not an
exception waiver. Mask, FP and comparator phase completion use this order.

Source identities:

- Old lifecycle SHA: `788c8789eada5c569bd6d8a0eb1ddd8039b051def4495e03a1fdeda3dc5f26a8`.
- Corrected lifecycle SHA: `ba3d4d86b7b810ff3fbb3439059b7bc6b2053d0a61907f51e87508a06dae7065`.
- Corrected actual parser SHA: `d78a1f23d37d838c72bd115a26fb960b99f1438a42da76a7b68e80fd4600e698`.

Host02 retained all19 tests and passed actual wait0. New Host03 retains the
same19 and adds seven event-order tests: valid enter/effects/leave, missing
final store or premature close, wrong final store value, missing final LBU,
missing leave before next instruction, duplicate last store, wrong closing
PC. All26 passed, actual wait0, elapsed1.2774355690926313s, no timeout and all
tested source pins unchanged. Receipt SHA:
`5967481dc015d16bcf92c3f1e09658bbfa03d78c216351b22eb782e69ad9b917`.
The supervisor binds the actual checker and test source identities, not an
inferred prior version. No software Host compilation or reference was rerun.

These are small synthetic observer tests, not measured firmware or DUT
acceptance. The independent exact-entry review must inspect this correction
and the final entry hash before the single conditional reference may start.
