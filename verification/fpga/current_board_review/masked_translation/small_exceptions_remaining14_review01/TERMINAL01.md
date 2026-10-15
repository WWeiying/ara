# Remaining14 M9 Terminal Review

Decision: NO_BLOCKER for architectural acceptance of these exact 14 original-source Sv39 singles on frozen M9. This is a metadata and evidence-binding review, not a second CSV/reference parse or a Linux parent-program acceptance.

## Verified Outcome

- Exact membership: e8 scenarios 1/2/3/5; e16 and e32 scenarios 0/1/2/3/5.
- All 14 persisted simulator child and monitor outcomes are numeric zero; producer complete is PASS, no abort, no retries, and unchanged pins.
- Producer and collector each have their own recorded systemd `EXIT_CODE=exited`, `EXIT_STATUS=0`, `SERVICE_RESULT=success`. No service-GC defaults or submission return code were used as process-exit evidence.
- Collector accepted 76,726 checks / 2,288,235 rows, 56 required completed memory owners, 28 checkpoints, and 224 handler restores. All 14 independent case metadata audits returned actual wait status zero.
- The 1,442-entry verified ledger retains all 1,271 producer plan pins. Collector code/binding hashes, takeover command, current result metadata, child outcomes, and strict/generic extent bindings match.
- Full defined oracle, ABI spill/restore rules, CSR context and required backend ownership remain enforced. The two scenario-0 cases return VL4 and leave only original output slots 5..8 undefined; other cases return VL8. Typed seeds and width-dependent page data are retained.

The short independent metadata-check process exited 0 (0.678 seconds). It did not open or hash raw CSV/reference files; CSV hashes were compared between the existing evidence ledger and checker metadata. Producer checks and collector checks are not represented as newly repeated semantic parses.

## Actual Launch and Exit Evidence

Paths below are relative to `masked_translation/`.

| Evidence | SHA256 |
| --- | --- |
| `small_exceptions_remaining14_terminal_collector01/result.json` | `bf64ae647a470a855da7e98f712f75a92fead170c8cccf30f1891af906f65101` |
| `small_exceptions_remaining14_terminal_collector01/verified_pins.json` | `7682de534a9b72aed3855ef246a346aee6ebb5eb79c93fb5cc562c2633792f78` |
| `small_exceptions_remaining14_terminal_collector01/binding.json` | `c68ad61fd1bb9e85f2e377c4caa62b8809ade595207e2e6da94fee6ae7153257` |
| `small_exceptions_remaining14_terminal_collector01/service_exit.json` | `ff7cc082cdc7cd405bacfc27b0e67ffb031b2ff2f1ac0c764d67ba8aea379ec8` |
| `small_exceptions_remaining14_vcs_m9_plan01/prepared01/complete.json` | `99bbca30652b4964979b46b9e2ff77a5ee06bf2af9bf7c9d5c4d21b026b1987f` |
| `small_exceptions_remaining14_vcs_m9_plan01/prepared01/service_exit.json` | `3eb9e1a27eee342501aa65a9bc5150e57d39934d3b8da967a6643a406c6afd4d` |
| `small_exceptions_remaining14_vcs_m9_plan01/prepared01/launch_command_takeover.json` | `dfb556311fa523d84da5b3b8f52834649d067e6d6117ce6284afaca91bc10ce4` |
| `small_exceptions_remaining14_vcs_m9_plan01/prepared01/systemd_run_takeover.json` | `1a6057036b7bc3e897c821185f0b6c94ec232255910e7caf36bdb196aa808358` |

The actual takeover command matches the reviewed launch envelope after substitution of the final entry-review path/hash, including the real ExecStopPost receipt hook. Its submission rc0 is explicitly distinguished from the later worker exit. Collector bindings use these actual takeover filenames, not fabricated original-agent receipts.

Plan SHA: `165c12dfee46c7949de188aedf779f914e8ee76260290017b2636e3fa168108f`.
M9 image manifest SHA: `48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a`.
Final entry review SHA: `dedc7324c2c09e0f803c89d6a34f04333e4384eb967406b0ac0b88db89c2e808`.

## Scope Accounting

These 14 plus previously accepted M9 e64/sc0,1,2,3 give **18/20 on M9**. Original-source coverage is 20/20 across M6 and M9, but e8/sc0 and e64/sc5 remain M6 evidence until the separately assigned same-ELF M9 replay is accepted. Prior sc0/sc3 checker failure and its explicit offline recovery remain historical evidence; no old NOT_PASS was overwritten.

This acceptance does not prove zero physical MMU/AXI activity or Linux signal-frame/clone/COW behavior. No simulation, reference, build, RTL change, or live-worker query was performed for this review.
