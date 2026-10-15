# Full6720 Original Reduction Reference

Completed the sole authorized reference and sole closed-raw semantic audit.
Status: **REFERENCE_FULL6720_PASS_SOURCE_ONLY_NOT_DUT**. Independent entry
review was NO_BLOCKER; this report does not substitute for an independent
terminal review or architectural DUT/Linux acceptance.

## Actual Outcomes

| Process | Numeric wait | Timeout | Elapsed seconds |
| --- | ---: | --- | ---: |
| Spike | 0 | false | 3.525748 |
| Closed audit | 0 | false | 78.851887 |
| Outer executor | 0 | false | 89.832495 |

Receipts: `reference01/spike.wait.json`, `reference01/audit.wait.json`,
`controller01.wait.json`. The reference command, exact `rs 2000000; quit`,
actual launch PID and bounds are retained alongside these receipts. Original
120s/512MiB/reference and 600s/audit limits were unchanged. One invocation and
one semantic parse; no compile, reference retry, DUT, or RTL change.

Actual firmware through HTIF: **1126049 instructions**, below the compiled
conditional upper1142355. Raw1130000 rows include5 reset-ROM rows and3946
strictly empty original park rows after successful HTIF1. Raw size127144742B,
SHA256 `99b7f55b894d1fc33ceea75712cce0809cfe94bae3dbf98b33e23fd0e2365276`.

## Full Source Checks

- Original contiguous8 x7 x4 x5 x3 x2 =6720 calls; all three21-instruction
  helpers,141120 dynamic helper instructions plus original capacity3.
- All967680 output bytes (144/call), including full128B vector destination and
  both8B guards;6720 returned vstarts and complete flags; flags_seen21.
- Actual bank1 fixture LD/LW6720, original row order, raw target vector payload,
  CSR request/save/restore, every scalar read address/value and helper PC/code,
  contiguous helper windows, caller effective addresses and branch/return flow.
- Original scenario-only128 input SH;128 seed SD;26880 mask SD shared by each
  sticky pair;120960 output SD and120960 complete output LD. No strengthened
  per-call input freshness or fractional-destination truncation.
- Actual full success console, no DETAIL/FAIL/TRAP, HTIF1 and pure park to EOF.
- Executor verified all177 sealed input pins before execution and after the
  run/audit, including imported parser, memory decoder and transport. Review,
  ENTRY and pin-manifest identities were added to the execution receipts.

`reference01/COMPLETE.json` retains actual numeric outcomes, raw identity,
input stability and the full result. `reference01/audit01/result.json` SHA256:
`d9043307b07b5594608b8b81d21870d3fba6e8dfc0f82260e407c0cf98583e6e`.
The Spike ELF is unchanged:
`0326cc068509dd6a42a8840426de99fd251dcefe04e552bda5135c36040c7d1e`.
SoC ELF remains the separately compiled, unexecuted full-parent port; neither
this reference nor the previous selected M6 single closes its DUT scope.
