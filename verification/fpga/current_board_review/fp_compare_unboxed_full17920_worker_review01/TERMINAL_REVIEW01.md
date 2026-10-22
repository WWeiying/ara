# Independent Full17920 M9 Terminal Review

Decision: **ACCEPTED_FULL17920_M9_INDEPENDENT_TERMINAL_METADATA_NOT_LINUX**.
No blocking inconsistency remains. Coordinated with Tesla: his producer, collector,
and observer were not rerun. No CSV or reference raw log was opened; no live
service query, simulation, reference execution, compilation, or sealed edit occurred.

## Identity and Actual Exits

- Prepared directory: `../fp_compare_unboxed_full17920_vcs_m9_plan01/prepared02`.
- Exact plan SHA256: `b6d0677124a045a35294a1c0be4a7b0f6a004f52e9f570e6e5b9478c4296bdbd`.
- M9 image manifest: `48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a`.
- Private/original source-port SoC ELF: `19afd0c6fd9c0810efbfdd9a635d092672554e6a1f3d4a3a537af00c4de13e37`.
- Actual monitor wait: numeric child **0**, **6687.05148726888 s**, no timeout or failure_seen.
- Producer: one full case PASS, aborted=false, retries=0, pins_unchanged=true.
- Actual ExecStopPost receipt: SERVICE_RESULT=success, EXIT_CODE=exited, EXIT_STATUS=0.
  This is a recorded systemd outcome, not a missing/GC unit interpreted as zero.
- Collector actual wait: **0**, **9.037510651163757 s**, timed_out=false.
- Observer actual wait: **0**, **2281.0216443538666 s**, timed_out=false.
  Notification waiter also recorded actual wait 0; its file-appearance message alone
  is not acceptance. Notification SHA matches the observer result
  `3e93fcbcb3309cf16a18062d90377ded614772e42da30614c59243c145d33b61`.
- Recorded command, private ELF, owner plan, launch approval pins, and terminal hook
  agree. RemainAfterExit is JSON false; no manual stop was needed for collection.

## Complete Accepted Scope

| Evidence | Exact count |
| --- | ---: |
| Original contiguous calls / flags / returned vstarts | 17920 each |
| Predicate-result bits / guards | 286720 / 35840 |
| Helper instructions / capacity instructions | 326144 / 3 |
| Fresh stores / input LD / output LWU / record LD | 734720 / 143360 / 17920 / 2240 |
| FPR committed writebacks | 10752, 336 for each of 32 seeds |
| CSV rows / retired instructions | 3413323 / 2665794 |
| Final CSV cycle | 6152665 |
| Architecture request/response ledger entries | 179203 |
| Required memory / nonempty target owners | 89600 / 15360 |
| VL=0 elidable targets | 2560 |
| Actual backend alloc / done | 104960 / 104960 |

The metadata reviewer independently matched every call's owner entries, PC,
instruction, helper index, required qualification, and alloc/done against the
bound full17920 model and actual SoC helper specification. All five memory
owners remain required even for VL=0; only the empty target is elidable. No
missing owner was waived based on numerical success. Generic request/response,
row and retirement totals agree; replay and exception counts are zero.

The original sealed semantic pass reports all data/flags/vstart/fresh/ABI/helper
checks; this review verifies its identity and complete metadata consistency,
not an independent second numerical traversal. The actual console contains the
exact reconstructed program UART text once, all full-scope pass markers, and
simulator SUCCESS, without FAIL/ERROR/TIMEOUT vetoes.

FPR scope is **committed writeback payload**, including rd=0 for FMV.D.X to f0,
as established by the frozen M9 FPR wiring entry review. It is not physical FPR
cell readback, an accelerator operand snapshot, or inference from qNaN results.
No extra post-restoration CSR readback is claimed. This accepts the complete
source-port parent, not original Linux execution/incident closure or an alias
scenario.

## Pins and Review Receipt

All **750 input pins** remain bound. Including approvals and terminal evidence,
**776 unique pins** were checked: **774 nonraw files rehashed**, and exactly two
raw artifacts inherited without rereading: the sealed reference commits log and
the DUT CSV. All producer/collector/observer CSV hashes agree on
`05b8a0413378031366c55e0f6e478a422d7fcfe989132dcd8f89c001b8b0bfa4`.
The complete pin map and inherited identities are in `TERMINAL_REVIEW01.json`.

Command from repository root:

```sh
python3 verification/fpga/current_board_review/fp_compare_unboxed_full17920_worker_review01/terminal_metadata01.py
```

Final actual command exit **0**, tool chunk `0ab4b6`, elapsed **7.518213005 s**.
Two earlier reviewer-only schema assertions are preserved in
`terminal_metadata_attempt01.json` and `terminal_metadata_attempt02.json`:
JSON false versus string no, and reconstructed UART versus whole simulator
console. Neither was a producer/DUT failure; neither read CSV/raw. The final
review did not overwrite any producer or observer evidence.
