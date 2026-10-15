# e8/m2 M9 Terminal Metadata Review

Verdict: ACCEPTED, 2026-10-14. No blocking discrepancy found.

Scope: independent terminal identity, receipt, pin and existing strict-summary audit of `full_e8_m2_block_vcs_m9_plan01/prepared01`. This accepts one complete original e8/m2 4095-call source port on frozen M9. It supports the parent's accepted-shape union increment from 10 to 11; it is not original Linux historical-stall closure or an assertion that all shapes passed on M9.

## Actual Terminal Evidence

- Exact sole member: `arithmetic_original_e8_m2_full4095_block`; runner COMPLETE, summary and complete results identical, PASS, numeric child returncode 0, elapsed 4953.565439571161 seconds. No cancellation, timeout, observed failure, abort or retry.
- Actual systemd ExecStopPost receipt: `SERVICE_RESULT=success`, `EXIT_CODE=exited`, `EXIT_STATUS=0`, hook PID 3283289. This is durable hook evidence, not an inference from a missing service.
- Collector status `ACCEPTED_M9_ORIGINAL_E8_M2_FULL4095_NOT_LINUX`; PID 3283308 matches actual wait receipt, numeric returncode 0, elapsed 10.900947386864573 seconds, no timeout or retry. Its embedded service and monitor records match the separate original receipts exactly.
- The raw child receipt's `architectural_acceptance=false` correctly denotes a pre-validation outcome; subsequent strict and collector acceptance remain separate.
- Both console and VCS log contain the exact original pass marker `RVV_MATRIX_PASS sew=8 vlmax=256 cases=4095 elements=1048320 errors=0 seeds=3 guard_tail_mask_vstart=checked`. Independent small-log scan found no RVV FAIL/DETAIL, BOARD_REPLAY_TRAP, fatal or FAILED marker.

## Identity And Scope Binding

- Plan, approved entry, actual launch, actual command, private ELF, source ELF, input manifest and terminal receipts bind the same member and frozen `current_board_memory_candidate09/campaign/image` executable. Source and private ELF hashes match.
- Configuration remains SEW8, LMUL2, CAP256, physical register group 2, 256 data bytes plus two byte guards: complete 258-byte output, 32 whole-word reads plus the final two-byte read. Mask storage is 128 bytes and actual mask load is 32 bytes. Source index 255 is valid at CAP256; no OOR substitution is claimed.
- Existing strict report retains all 4095 continuous original calls, original once-per-seed initialization and per-group mask reuse. No partitioning or reduction of the original oracle.
- Independently checked all 4095 existing call-ledger entries: consecutive original ordinals, reads 0 through 32 for each call, returned vstart zero, and target PC/encoding matching the pinned per-operation helper.
- Counts: 1,048,320 results; 8,190 guards; 4,095 returned-vstart checks; 53,235 helper instructions with each of 13 positions counted 4,095 times; 135,135 packed output reads.
- Independently checked all 45,047 existing owner-ledger entries: unique architecture orders, every actual alloc count equals its done count, every required owner has an allocation. Required memory owners 20,475 plus required targets 2,592 = 23,067; required op24 targets 117. These are actual ledger checks, not only aggregate equality.
- Generic and trace-summary metadata agree: 45,047 requests/responses, 23,067 uop allocations/completions, zero exceptions/replays, 1,254,286 rows, 1,073,011 retired instructions, final cycle 9,132,185. Strict firmware-through-CTRL count is 1,073,005 plus six parking retirements.
- No explicit fflags oracle exists in this original integer source; none is claimed here.

## Pins And Audit Boundary

The plan contains 804 pins. Rehashed 815 unique non-raw files across plan, complete evidence, approval and actual image-input maps: all matched, including the original archived ELF and private/source SoC ELFs. No production or sealed artifact was modified. The metadata audit command completed with actual shell exit 0 (tool chunk `404fc4`, preceding execution `dac7d7`).

Neither reference `commits.log` nor DUT `commit_trace.csv` was reread or rehashed in this review. Their existing hashes remain bound through the accepted reference/entry and terminal collector. The DUT CSV hash agrees across complete evidence, strict report and collector; strict reports one semantic parse and collector reports zero semantic reparses. This review performs no new CSV semantics, simulation, reference execution or live-process query.

| Artifact | SHA256 |
| --- | --- |
| `prepared01/plan.json` | `94eed1996ba66e9451e3273e75efb9bd9297af4c9b43db4d78227a65996402bd` |
| Prior entry `e8_m2_block_m9_entry_review01/result.json` | `a3fb1447bee233dbd5e8d7510d789240f87a043825256ec89ae6cf6676531a9d` |
| Original archived `rvv_matrix_e8_m2` ELF | `fe193c889801184a3144895f4817f0e9e6a9dfffae3144f6bf5bbcd311a1c0c6` |
| Source and private SoC ELF | `30eca586d305d0636c125c4ad4ebdf9acf267feb6163b6c460b75e3bb5d1354d` |
| M9 `image.json` | `48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a` |
| `prepared01/complete.json` | `aacb617b1eb0443e2bc51c659bdefa56e9c6ff5ea7e0feaa140fc9ae540a7172` |
| `prepared01/collector_result.json` | `cd2e0039a71cc639313bf6c5db836b6488d42e4f629292385ac7e4fd383e761c` |
| `prepared01/collector_exit.json` | `3097d3acbacde6435745cb78e6a6ccbaa91cebfbc84692cd91deb96cfd7a04ae` |
| `prepared01/service_exit.json` | `aa7a9487c5abb68735e4f73df8ddc6dca4800ff264fa5b6ef22a552ccebe275e` |
| Member `strict_original.json` | `40ed46a0822ff6c54eb26c46f35e4366bdc9c1057161de7bf4e64d6baa55aed9` |
| DUT CSV, existing terminal hash only | `636121545976d7600f987f7f6d887afca909a455443ff9bd3db353f36db887b1` |
| Reference raw, existing pinned hash only | `0cff38cae8858ff430a97bf083eb7bab506ce7a4a076abc70ec9e8270a6ffb42` |
