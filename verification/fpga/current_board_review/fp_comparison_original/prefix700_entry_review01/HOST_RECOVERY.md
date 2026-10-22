# Worker Host Interface Recovery

Decision for this delta: NO_ORACLE_RELAXATION. Final exact-plan entry remains
separate. No Host/reference/DUT rerun was performed by this reviewer.

`full700_vcs_m9_plan01/host_worker01.json` retains FAIL_HOST,8 tests,
0 failures/1 error; SHA256
`db450aca4c44506f0413ad86e5c36b4133a6afd326e6d33281a4082ab084f9f8`.
It contains counts and input hashes, not the exception traceback. The producer
reported a missing `checker.VETO` attribute; static source inspection confirms
that exact incompatible interface: inherited
`nan_min_soc_vcs_m6_plan01/replay.py:317` accesses `checker.VETO.pattern`
when entering `engine_hooks`, before simulator dispatch.

This reviewer reconstructed both old file hashes from current files in memory:

1. Removing only `VETO = _source.VETO` from new checker.py produces the exact
   host01 checker SHA3c8edf307568ab096e0330ef8b107dcfe4b1bbea711d461e3634e8c3a743e471.
2. Changing only HOST_REPORT from host_worker02.json back to host_worker01.json
   produces the exact host01 replay SHA2f49e3a2ef41784353b76cf9d1d4dce3bab3f5e46fd15537c4ab22f47c36a103.
3. Every other host01/02 code pin is identical; all14 host02 code pins match
   actual files. Test source and full strict oracle were not edited for recovery.

The export reuses the unchanged failure regex from the immutable predecessor,
including explicit RVV_FP_COMPARE_DETAIL/FAIL matching. It neither removes a
veto nor catches an exception as success. The private full-oracle implementation
still consumes the local700 model; the diagnostic generator yields every row
unchanged and rethrows errors with additional context. Its patched-audit Host
case proves diagnostic context only, not full700 numerical acceptance.

Observed successor `host_worker02.json`: PASS_HOST_ONLY_NOT_DUT,8 tests,
0 failures/0 errors,3.212398585s; SHA256
`058e9ad4a90fa0444ce0a5acfd40ce5d98a54669e912fa8d9736d951b53c6a4e`.
Tests retain real frozen-parent early-postcheck0/17 numeric receipts, timeout
numeric preservation, real generic validator plus missing-owner/family vetoes,
wrong-scope/late-abort gates, exact console contract and diagnostic observer.
There was no DUT launch associated with host01 or host02.

Entry must bind these exact successor code hashes, full700 reference READY,
source_delta evidence, final plan/dryrun and actual authorization. A raw failure
that stops before postchecking must remain failure; a separate once-only closed
CSV diagnostic may explain it but must never promote it to PASS or rerun DUT.
