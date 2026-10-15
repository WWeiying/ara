# Full6720 M9 Terminal Metadata Reconciliation

2026-10-15. Complete original `rvv_fp_redspecial_e16_mf4` source-port
architectural scope accepted, not original Linux execution. No new DUT run,
CSV semantic parse, or large-trace hash in this reconciliation.

- [Collector](prepared01/collector_result.json):
  `PASS_FULL6720_M9_METADATA_COLLECTED_NOT_LINUX`, pins unchanged.
- Actual simulator numeric0, 3076.519099968951s, no timeout/failure.
- [Service receipt](prepared01/service_exit.json): actual ExecStopPost,
  success / exited / 0, not inferred from collected systemd defaults.
- [Collector wait](prepared01/collector.wait.json): actual0,
  4.476906944997609s, not timed out.
- [Event notification](terminal_event01/notification.json):
  `TERMINAL_COLLECTOR_ACCEPTED_METADATA_ONLY`.

Full original order 8 scenarios x 7 VL x 4 masks x 5 rounding modes x
3 operations x 2 sticky states: 6720 contiguous calls. All144 bytes per call
(967680 total), 6720 flags, 6720 returned vstarts, 141120 helper instructions
and3 capacity instructions accepted. Original fixture bank and source setup
events, full output/guards, flags_seen21 and errors0 are preserved.
The prior strict report records1421335 rows and39360 actual alloc/done pairs:
33600 required memory owners plus5760 nonempty targets;960 VL0 targets can
elide. No CVX exceptions. This uses the already completed checker report,
not another trace traversal.

Identity chain:

- Plan: `49ffb74caba23b096d9addb009511a4d92e21f51c9182379d839b345e53978a1`
- Complete: `5505cb8341d7b8375c4e7658db978b914fb5689c5b86342d7a440224bf0580a1`
- Collector: `8805c2b0604ec2f632a939c743091d9329c350a6f524746db93519ea59da9d19`
- Collector wait: `274f5b11e57aaecfe0dc73d33b0bd2c0007e0c8e3fcf67fabd2d9842803c8e9e`
- Strict report inherited identity: `7c95c5e332f828a08b14ff0094982dfbf4b4d384bd7d1cfb5772b3f9cdc04da6`
- Closed CSV inherited identity (not rehashed):
  `299986cfe3774563d87a395a03fa7288715ab80ba97a8eaddd9bfebb1b06d0b9`

Other ten reduction shapes retain their previously accepted selected singles;
this is not their full6720 acceptance. Other FP parents, Gather stalls,
kernel CSR/NF8 historical Linux evidence and arithmetic remaining scopes are
unchanged. Averroes completed the single independent metadata-only
[terminal review](TERMINAL_REVIEW.md):
`ACCEPTED_M9_FULL6720_SOURCE_PORT_NOT_LINUX`, no blocker.
Review JSON SHA:
`78427b0101fd2f57b78993ddbf0374c80dcb3588ae6240991645d0e0e9e296b3`.
