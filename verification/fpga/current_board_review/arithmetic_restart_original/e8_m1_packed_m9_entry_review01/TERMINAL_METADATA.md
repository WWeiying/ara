# e8/m1 M9 Terminal Binding Review

Verdict: **ACCEPTED**, the original full4095 e8/m1 source port on frozen M9.
This is a short independent attempt/entry/plan/outcome/collector binding review,
not a second semantic CSV or reference-raw audit. No simulation or Host test ran.
It does not close the original Linux/board stall and does not update aggregate
shape counts here.

## Bound Evidence

All producer terminal files are in
`full_e8_m1_packed_vcs_m9_plan01/prepared01/`.

| File | SHA256 |
|---|---|
| plan.json | `150703ba0c1dc2baf5fd6c68d21fa465fd8302056071405fee8ada05c8b4aa04` |
| Prior independent entry result.json | `ec5d9cd6fba336ead5f1d811fe8e981c8a1519b4517907125dc04413ac1d9c91` |
| complete.json | `a0f82cc0efb87d9d2c9d3843fc3b2e9a61f2fdd7b9fa12fd2b20db0628de5ffe` |
| service_exit.json | `90edd883e9b97944a03d463ec4679d9755177e587a0d9807184dae9c4bcbe87e` |
| collector_result.json | `285092af0aea9a36502dfb86acfbb08d54226ebfe44299bdb88b919f23a83893` |
| collector_exit.json | `45e2e6fe7fd826c35a44685b19862f5db94c61b625cef447b5cdbab3aac71e43` |
| strict_original.json | `c0b0823fb06a4dee44e579c8785b7a9ced29fd64ba75385d800ba783cf9d967e` |

Launch invocation, entry, actual launch, complete and collector bind the same
plan and exact one member `arithmetic_original_e8_m1_full4095_packed`.
Original archived ELF identity is
`199a69e4394959e73f0b7458359c06f0e39a09f4c621028eb356723684dd1f9a`;
actual source/private SoC ELF is
`60ce49d374a4b8491d503f3159d3d13c32489e30141b3a52192ea8f47eb01621`.
Frozen M9 image.json identity is
`48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a`.

## Actual Terminal Checks

- Original worker run is COMPLETE, one PASS, numeric child0,
  2909.581789597869s; persisted pre-postcheck outcome has timed_out=false,
  failure_seen=false and cancelled=false. No abort or retry. Command/private ELF
  and frozen image bindings match. Systemd ExecStopPost records actual
  success/exited/0, not an inferred outer exit from the worker's own PASS.
- Collector PID3234921 has actual wait0,5.832327626179904s, no timeout/retry.
  Collector accepts the same complete SHA, strict SHA, actual child outcome and
  service exit. The reviewed collector performs pin/hash binding without a second
  semantic CSV parse.
- Strict summary records full4095/524160 data/8190 guards,4095 returned vstart0,
  53235 helper instructions with all13 slots4095,69615 output reads, fresh130B
  every call, full_order=true and partitioned=false. Independently checked its
  generated4095-call ledger: every call has all17 reads and returned vstart0.
  This retains physical1/full128B plus two one-byte guards and actual vlm16B.
- Independently checked the already-generated45047-entry owner ledger, without
  reading CSV: unique arch_order, every actual alloc equals done, every required
  owner has an actual pair. Required23067=20475 memory+2592 targets; all actual
  allocations/dones also total23067. The117 required op24 memory targets remain
  required. No global owner waiver was substituted for the admitted precise
  source-model no-op policy.
- Strict and generic agree on876328 rows,695053 retirements and lastcycle5091453.
  Generic CVX request/response45047/45047, alloc/done23067/23067 and exception0.
  Original console PASS marker is present in both raw console logs, with no
  RVV failure/TRAP/fatal/unsupported veto found.

## Pin Scope and Limits

Rehashed807 unique nonraw plan/evidence/approval paths (plan has796 pins), plus
the actual input image-member map, with no mismatch. Did not reread or rehash
the accepted reference commits.log or DUT commit_trace.csv. Their preserved
identities are, respectively,
`80e1f0d351e0ddabc40bbf4aceae8e5585b09d215c2170d5f650bb521b8ebed9`
and `36434b3a7bfd977c035ee1bc52c157ff372f3f771fbe5a280b0c7d96698cea02`.
The DUT CSV hash agrees across original strict report, complete evidence pins
and successful terminal collector. This review relies on that completed
single semantic audit rather than claiming a new raw verification.

Independent metadata tool completion `5c04f1`: numeric0,3.926061871s.
No old result, sealed input, production RTL, or root aggregate count was changed.
