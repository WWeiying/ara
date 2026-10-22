# Original Exceptions20 Remaining Scope Review

## Basis and Scope
This records the completed read-only inventory, not a new verification run.
No hashes, reference, DUT, active CSV or live process queries were repeated
while saving this report. Main ledgers and sealed inputs remain unchanged.

Archive: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_exceptions01`.
Manifest SHA256 previously checked:
`c6d7c465085cf029c57136a7b09e79d3c232e3db2582dcfba3b2f4254b60b26c`.
The prior review verified all20 ELF and C/S identities against that manifest.
Membership is SEW8/16/32/64 times scenario0/1/2/3/5. Scenario4 is not a member.

## Image-Specific Inventory
Numbers below are scenario IDs. M2 entries mean source-derived coverage,
not execution of the archived Linux single or acceptance on M6/M9.

| SEW | M6 accepted, deduplicated | M2-only derived coverage | M9 launched, not accepted | No such acceptance/start evidence at review |
| --- | --- | --- | --- | --- |
| e8 | 0 | none | none | 1,2,3,5 |
| e16 | none | 0,2,3 | none | 1,5 |
| e32 | none | none | none | 0,1,2,3,5 |
| e64 | 5 | none | 1,2 | 0,3 |

M2 e16/scenario0 and2 map to extended8 members `fof_shorten` and
`fof_masked_suffix`; e16/scenario3 maps to `alloff_fault`.
Actual M2 summaries/extended8 terminal are PASS. These do not become M9 PASS.

M6 runtime IDs `fof_original_e8_scenario0` and
`fof_original_e64_scenario5` have producer and independent terminal PASS,
both actual numeric exits0. Keep these accepted singles deduplicated.

M9 runtime IDs `unit_fof_e64_scenario1` and `unit_fof_e64_scenario2`
bind the correct original names and READY members. Plan SHA256:
`3bc80c42d8e6bf7f722d81184ef8fc4bcac099e2518547292f5172665324e949`.
The startup artifact records actual simulator/CSV progress, not PASS;
complete.json was absent at the prior review. Do not duplicate either launch.

## Exact Remaining Lists
**18 members lack M6/M9 acceptance, including the two M9-running members:**
- e8: scenario1,2,3,5.
- e16: scenario0,1,2,3,5.
- e32: scenario0,1,2,3,5.
- e64: scenario0,1,2,3.

Removing the two running members leaves16 not yet accepted/not running at review.
For **new source coverage priority**, also exclude the three older M2-derived
members; this produces exactly **13 candidates**, not an18-to13 closure claim:
- e8: scenario1,2,3,5.
- e16: scenario1,5.
- e32: scenario0,1,2,3,5.
- e64: scenario0,3.

Full canonical names are enumerated in REPORT.json.

## Original Oracle Classes
P is the protected-page start; B=SEW/8. All have VL8, m1, selected original
helper11 instructions and capacity3. All require returned vstart0 and original
guards out[0]/out[9]. Oldvd is the per-element integer0x5b, not a wide-element
repeated-byte5b pattern.

| Scenario | Target/address/mask | Original required outcome |
| --- | --- | --- |
| 0 | FOF, P-4B, ff | VL4; first4 exact; final suffix4 excluded by original oracle, not forced to oldvd |
| 1 | ordinary load, P-4B, 0f | VL8; first4 exact, masked protected suffix4 oldvd; no fault |
| 2 | FOF, P-4B, 0f | Full8 exact as scenario1; no fault or VL shortening |
| 3 | ordinary load, P, all zero | No fault despite protected first address; all8 oldvd, VL8 |
| 5 | FOF, P, all zero | No fault or shortening; all8 oldvd, VL8 |

## Priority and Ownership
First: **e64/scenario3**, ordinary-load suppression from the protected first
element. This differs from currently running active-prefix/masked-suffix
scenario1/2 and accepted FOF-alloff scenario5. Only e16 M2 derived coverage
exists for scenario3 in this inventory.

Second: **e64/scenario0**, wide-element FOF shortening, not replaced by the
accepted e8 case. This is a static coverage priority, not a new bug claim.

Latest parent instruction assigns e64/scenario3 and0 preparation to Aquinas.
That assignment is recorded only; no READY, launch or acceptance is inferred.
Current e64/scenario1/2 tasks must not be started again.

## Evidence References
- M2: ../COMBINED02_ACCEPTANCE.md and
  ../sv39_extended/candidate02_extended8_02/complete.json.
- M2 scenario3: /home/wangwy/fpga_runs/current_board_memory_candidate02/campaign/sv39/summary.json.
- M6: ../fof_two_singles_vcs_m6_plan01/terminal_waiter01/TERMINAL_REPORT.md
  and terminal01/result.json.
- M9: ../unit_fof_e64_suffix_two_prepare01/READY.json and
  ../unit_fof_e64_suffix_two_vcs_m9_plan01/prepared01/plan.json,
  startup_observation.json.

REPORT.json retains the previously observed hashes and exact member mappings.
No complete exception-family closure, Linux clone/wait/signal ABI acceptance,
original-parent continuous history or all-bugs-closed claim is made.
