# e8/m8 Actual Software Cost

SOFTWARE_COST_GATE_PASS_PENDING_INDEPENDENT_ARTIFACT_REVIEW_NOT_REFERENCE_NOT_DUT

Short C/UB: 9 real-ordinal positives, 9234 output byte negatives (including both byte guards and the protected2B tail),384 full128B mask byte negatives and6 wrong-mode negatives. No fullstream Host or ELF execution.

| Backend | Positive CFG upper | Comparator instructions | Comparator instructions saved vs old451/call | Comparator scalar loads (all) | Literal-pool loads | Stack gap |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| soc | 2586331 | 1686072 | 160773 | 707445 | 0 | 654824 |
| spike | 2584640 | 1686072 | 160773 | 707445 | 0 | 646368 |

Actual CFG counts every executed instruction in the linked success path, including constant rematerialization, branch/join/setup and spills. It includes main, original helpers and printing/startup allowance. Main load/store totals and per-PC visits are retained. Gold load savings alone are not a total-memory or runtime claim.

Geometry is e8: a/b each1024B only, no extra e16 BSS shadow; out+1, SH/LHU2B tail, vtype3. Full4095 source history and inputs checked at each linked helper call. All528255 output reads and full128B masks remain.

This is static linked CFG, conditional on successful original vector results, not architectural reference or DUT acceptance. No new firmware count or <3h guarantee exists. Original artifacts/failures and compiler flags remain unchanged; no flags search, reference or VCS was run.
