# Final Terminal Review

Decision: ACCEPTED, full continuous1134 source-port on frozen M9, with366 original
exclusions. This is not Linux acceptance and not the earlier partitioned runs.
Reviewed continuous_packed_vcs_m9_plan01/prepared02 only; prepared01 is unchanged.

## Actual Exit And Scope

- Persisted simulator outcome: numeric0,7442.520112464204s, no timeout, failure
  marker or cancellation. Producer complete PASS, aborted=false, retries=0.
- Actual ExecStopPost environment: SERVICE_RESULT=success, EXIT_CODE=exited,
  EXIT_STATUS=0. This is the recorded hook, not inferred GC/systemctl defaults.
- Collector PID3003728 actually waited to exit0 in15.751907765865326s, not timed out.
  Actual command invokes collect02.py; SHA
  c3fb26193987c8e1475f73e5ee41b7c8506814ba92e1cfa58e2e301f098aeb02 matches
  the current callback and the literal enforced by pinned exit_hook02.py.
- Strict result:1134 original ordered calls,366 exclusions,1233792 checked output
  bytes,2268 vstart reads,21366 helper instructions. Full order=true,
  partitioned=false, raw architectural exit0, exactly one semantic CSV pass.
- Fresh input stores145152; fresh output stores154224; output word reads154224.
- Owners:4536 payload requests;3402 required staging/readback plus864 required
  nonempty targets =4266.270 empty targets legitimately exempt.4266 allocations
  and4266 completions; zero live owners at termination.
- Generic and strict summaries agree:4386671 rows,4344110 retired instructions,
  final cycle5896292. Original console reports1134/366/errors0 and board PASS.

## Binding And Limits

Freshly checked plan/complete/strict/actual-child/service/collector hash links,
13 small terminal-evidence and approval files, and the pinned exit-hook callback.
Plan contains746 input pins; producer and collector both certify unchanged pins.
Collector code verifies all746 inputs and12 terminal evidence pins. This review
inherits that recorded full verification instead of rehashing large inputs.
The CSV digest agrees across strict, collector and evidence bindings; this review
neither parsed nor rehashed the505088558-byte CSV. No simulation or reference ran.

| Evidence in prepared02 | SHA256 |
| --- | --- |
| plan.json | dda443312e22010c1b68a0090032d15682049c554b1cc879f780444ca10ca51d |
| complete.json | e6d02ec614aefb678b9795b442cdabe742ef101137bf7e0fba61ccfb1320567c |
| collector_result.json | f5f60e8190454d548aec683d1a8e8a65bca9107d210e83436152b203aea877db |
| collector_exit.json | bb817ca3cca2013fa0baab04d1c0e41aa7f42063c7605babc82c5b85983ae750 |
| service_exit.json | 2d6518df394dc710b4cfde1223fe4f55d0432025f09aee53bf760dfdcd9ef0f9 |
| launch_invocation.json | c242c10b8a1c7dba2bad56a99b759d5340a069f9e30d38f26e9776e8fb86cb8f |
| service_submission.json | 7cd184cd2c74e2e2e544c601acdbe85ff24f1bac26a80d8fd9064b739fb43a88 |

Strict result SHA:c15eeadc73dbe239c2a9c1b6d2cd541c3acef9523bdff36791a848aac5e35616.
Cross-bound CSV SHA:aac943d49efcc5de31d4923a3e9f2bba77f54c2448aa6c3b4be4d6d42b6c5116.
No blocking discrepancy found within this metadata-only terminal review.
