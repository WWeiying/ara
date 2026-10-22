# Independent M9 Full6720 Terminal Review

Decision: **ACCEPTED_M9_FULL6720_SOURCE_PORT_NOT_LINUX**. The sole authorized run completed the full original e16/mf4 reduction source-port scope. No blocking discrepancy was found in the terminal identity, actual exit receipts or generated strict/generic/owner summaries. This does not close the original Linux environment.

## Actual Completion

- Actual simulator monitor: integer returncode0, 3076.519099968951s (51.275min), timed_out=false, failure_seen=false.
- Actual systemd ExecStopPost: SERVICE_RESULT=success, EXIT_CODE=exited, EXIT_STATUS=0. This is an outer-service receipt, not an exit inferred from internal PASS or a missing unit.
- Collector actual wait: integer exit0, 4.476906944997609s, timed_out=false; its log hash matches the actual empty log.
- Worker: PASS_M9_FULL6720_REDSPECIAL_SOURCE_PORT_NOT_LINUX, retries0, aborted=false, pins_unchanged=true. Exact one-member summary agrees with COMPLETE and runner status COMPLETE/PASS1.
- Independent event notification agrees with collector, actual simulator outcome and service receipt. No task was restarted or queried live for this review.

## Full Scope and Owners

The already-produced strict result covers all6720 calls and all967680 output bytes: each call's full128-byte destination plus two8-byte guards. Flags and vstart each have6720 checks. All141120 original helper retirements (21 per call) and3 capacity instructions are present. Source events are input_SH128, seed_SD128, fixture_fields6720, mask_SD26880, output_SD120960 and output_LD120960. Console summary in the strict result reports cases=6720, flags_seen=21, errors=0 and complete board success markers.

The strict and generic summaries agree on1421335 CSV rows,1120846 retired instructions and last_cycle3706928. Firmware through actual CTRL0 is1120840, followed by6 parking retirements. Architectural request, CVX request and response counts are73923 each; exception and replay counts are0.

The generated owner ledger was checked as metadata, not regenerated from CSV: all calls0..6719 occur;33600 memory operations and5760 nonzero-VL targets are necessary and each has a completed owner. The960 VL0 targets remain optional, not a waiver for nonzero-VL all-masked operations. Actual backend allocation and completion totals are39360 each, every recorded owner balances, and no CSR replay is present. Configuration entries total33603. These are actual DUT-derived owner summaries, not reference owner predictions.

## Exact Binding

| Evidence | SHA256 |
| --- | --- |
| prepared01/plan.json | `49ffb74caba23b096d9addb009511a4d92e21f51c9182379d839b345e53978a1` |
| ENTRY_REVIEW.json | `b46ac6594eb136f8000167e9003ee4dfb6412262b314259d8c069fe30e1220d4` |
| parent_run01.json | `d2919f108d9f18d49bba4603ebf027a2e8b45bf4e3cc326d73b039f73f7ab5c6` |
| prepared01/complete.json | `5505cb8341d7b8375c4e7658db978b914fb5689c5b86342d7a440224bf0580a1` |
| prepared01/collector_result.json | `8805c2b0604ec2f632a939c743091d9329c350a6f524746db93519ea59da9d19` |
| prepared01/collector.wait.json | `274f5b11e57aaecfe0dc73d33b0bd2c0007e0c8e3fcf67fabd2d9842803c8e9e` |
| prepared01/service_exit.json | `69f09cab7b7721c902ffe13fc26d292f149ff3cf4aea81586ba0b6edd1c738e3` |
| terminal_event01/notification.json | `f33d0ef6d754a75d908dd2b46f58f0f230bd755ac0bf5b2ed8690ce774149547` |
| strict_original.json | `7c95c5e332f828a08b14ff0094982dfbf4b4d384bd7d1cfb5772b3f9cdc04da6` |

Private input ELF hashes to the accepted source ELF `5242911cb3a64d2bab02be8babdad363d75796a5f25dd351b82706c6279aca7c`. The actual command names the frozen M9 executable and this private ELF, original runtime name, seed1 and NO_FSDB. Current image.json matches `48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a`. Exact parent authorization, entry, plan and captured direct service ownership agree.

Seventeen distinct nonraw evidence/approval files were independently hashed against recorded pins, plus seven current local code pins and image.json. The complete818-input verification is inherited from the reviewed worker and collector; this review does not claim another full818-file rehash. Recorded CSV identity `299986cfe3774563d87a395a03fa7288715ab80ba97a8eaddd9bfebb1b06d0b9` agrees across strict result, COMPLETE and collector; it was not recomputed here.

## Review Limits

No CSV, raw console or reference trace was read, statted or hashed in this review. Full semantic checks and raw failure veto inherit the sealed checker/collector execution; their metadata and relevant code identities were checked. No new simulation, Host, reference, build, live-service query or shared-ledger edit occurred. Vector payload is not directly observed by this RVFI adapter: acceptance relies on the complete actual scalar output reads, original CSR oracle and actual protocol evidence as established by the entry review. The accepted scope is the full original6720 source port on frozen M9, not original Linux closure or other reduction shapes.
