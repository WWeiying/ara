# Stage3 Central Control Gate Result

The bounded VCS run `stage3_control_gate_20261110_03` passed all 43 cases:
33 successful commands (including recovery) and 10 negative commands with
checked error completion. There were 12078 accepted payload/result comparisons
and 11361 simulated cycles. All 11 host checker/regression tests passed.

## Evidence

Output root:
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage3_control_gate_20261110_03`

- `report.json`: PASS, post_pins_match=true, post_image_match=true.
- Report SHA256: `b0099f9f0df97248f0147234e807dc828fd9736ebd3d6192c52349dc31d86e59`.
- Run-log SHA256: `0e589b0e2c879bed121b15a6beef42be2403c5ff288061e824411bbb3bf0578f`.
- `source-pins.json`, `image-pins.json` and their `-after` inventories retain
  selected accepted package bytes, production originals/copies, review docs,
  helper, tests, source list, compiler and simulator identity.
- Service `stage3-control-gate-20261110-03.service` directly owned the worker
  and completed successfully in 35.982 seconds. Simulation CPU time was 0.970
  seconds. These times are test cost, not a hardware performance claim.
- Current maintained successor: `control_gate_fix02/control_gate.py`,
  `control_gate_fix02/control_gate.sv`, `control_gate_fix02/control_gate_test.py`.
  Its sealed plan contains the pre-run scenario-dependent counter audit.

## Checked Contracts

Real production control/group/import/reader/fanout were composed with tagged
stub lanes and a synchronous Q/V and non-cancellable K-gather timing model.
No DUT internals were forced. Normal lane done followed every result handshake;
aborted lane done followed observed lane_abort. Architectural data, slot and BE
were consumed into a poison-initialized test VRF, including masked-tail checks.

| Contract | Observed evidence |
| --- | --- |
| QK geometry | T1/2/3/17/64 x H1/2 at D64, plus D96/T17/H2 and D128/T64/H2 |
| Q identity | Valid nonzero bases, last fitting rows, invalid resident-row and physical-row bounds |
| No QK VRF source | Poison source valids asserted; zero source-ready/acceptance; exact private zero seeds |
| Inactive/tail masking | No inactive-lane payloads/results; T17 packet mask; FP32 partial write BE and untouched VRF bytes |
| Barrier | T1 exactly one wait sample; multiple active lanes >=2; held result/data/slot/BE until commit and grant |
| Final acknowledgement debt | Every successful case held ownership 27-30 cycles after all lane completions while acknowledgements remained |
| QK abort before launch | Case 14: zero launch, seeds, memory requests, results and acknowledgements; completed in 13 cycles |
| QK abort during seeds | Case 17: three seeds accepted, no architectural results/acknowledgements |
| QK abort during K gather | Case 20: nine aborted-busy samples; seven lease-held cycles after all four abort-done handshakes; no early release |
| QK abort before commit | Case 23: all 18 seeds, 256 coefficients and 320 value beats delivered; zero architectural results/acknowledgements |
| PV failure drain | Cases 35 and 41: exactly 96 source words for seed abort and prelaunch-invalid context, respectively |
| Failure and recovery | Every negative case had error completion with zero results/acks; each followed by successful QK then PV without reset |

## Preserved Failures

Run `_01` failed the test VRF untouched-word oracle: its expected poison literal
contained seven bytes while initialization contained eight. `control_gate_fix01`
corrected only that literal and added a host regression rejecting the original.

Run `_02` passed the initial PV baseline, then failed the test's multi-lane
barrier-duration assumption on T1. With one active lane, the real group grants
commit on that lane's first result-valid edge, giving exactly one monitor
sample. The parent approved that exact single-lane criterion; `_03` preserved
the original multi-lane, final-debt, stall and functional requirements and added
counter diagnostics plus host mutations. No new scenarios or unexplained
threshold changes were introduced.

Neither failed output nor its source files were rewritten or relabeled PASS.
A final read-only audit rehashed the source and image inventories for all three
runs successfully. Production control remained
`61dce0dc5f108bb70da34f3f0f230c28415e9e71d882b3692f5fa35be871368f`.

## Limits And Defects

No remaining defect was observed within this bounded control/transport gate.
It does not prove arithmetic, actual SRAM, actual FPU/native coexistence,
engine admission, SoC integration, performance, or FPGA behavior. The engine
busy-admission guard was read statically only; reader/SRAM and real lane/FPU
gates are separate evidence. No production source was modified by this task.
