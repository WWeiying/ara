# Full6720 M9 Prepared Entry

Prepared and dry-run only. **No DUT started.** Parent launch review remains
required. The full reference has independent terminal acceptance:
`../full6720_e16_mf4_reference_review01/TERMINAL_REVIEW.json`, SHA256
`05488c3fe4aa56eab93011a7903ff0bfc5a7a7a9eece9a56bd6210e1b47ff9ff`.

## Exact Inputs and Bounds

- Same SoC ELF SHA256
  `5242911cb3a64d2bab02be8babdad363d75796a5f25dd351b82706c6279aca7c`;
  actual SoC PC/code, MMIO CTRL0 and UART, not Spike addresses/HTIF1.
- Frozen M9 image `current_board_memory_candidate09/campaign/image`;
  image.json SHA256
  `48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a`.
- Original contiguous6720 calls, three21-instruction helpers plus capacity3;
  all144B/call =967680 bytes, flags/vstart6720 and original fixture bank1.
  Scenario-only input/seed initialization and row-level mask reuse retained.
- jobs1, simulator10800s, worker12000s, service13200s; cap24, memory>=32GiB,
  reserved0. No build, FSDB, retry or automatic budget extension.

## Implementation and Evidence Boundary

`strict.py` inherits the accepted reference's source-event methods, scalar
memory decoder and control-flow evaluation. It adds only RVFI transport/source
mapping and observes real returned scalar values. It never synthesizes Spike
vector effects; the full18 actual output LDs and CSR return values establish
architectural results. Original helper memory operations have generic protocol
and source-owner coverage, not a claim of independently observed per-lane data.

`checker.py` reuses the sealed six-event lossless observer and owner pairing.
Required owners:33600 memory and5760 nonempty reduction targets. Alloff mask
with VL>0 remains required. Only960 VL0 targets may have no backend owner.
Actual alloc/done totals are reconciled; they are not forced to this minimum.

`replay.py` binds the mature M9 worker in a private module instance, preserving
its numeric-first monitor receipt, stop-first-failure, sticky abort, late disk
plan validation and full generic/source check. No shared helper was edited.
Runtime DETAIL monitoring waits for the complete original
`scenario/op/vl/mask/frm/flags/expected_flags` line plus newline. This source
has no errors field in DETAIL. Post-run raw veto remains strict. Numeric child
outcome is durable before any DETAIL parsing; diagnostic I/O cannot erase it.

Service uses `RemainAfterExit=no`; `exit_hook.py` records actual systemd
SERVICE_RESULT/EXIT_CODE/EXIT_STATUS then executes one bounded metadata-only
collector. Unknown/missing/nonzero exit is not success. Collector does not
repeat semantic CSV parsing. Reference raw identity is inherited through the
accepted terminal review + COMPLETE + audit-result hashes and size; raw is
excluded from repeated input hashing.

## Actual Short Tests

- `host01.wait.json`: numeric0,6.334799s;15 short tests. Actual SoC helper windows
  for all three operations, VL0/nonzero/sticky/last case; complete144B tails and
  guards; wrong NV/vstart/restore, bank, opcode, missing fresh data/helper;
  required-owner pair deletion including alloff; ABI opaque spill; numeric-first
  failure and metadata/plan drift. No full source Host or reference rerun.
- After the narrow runtime-monitor change, `monitor_host01.wait.json`:
  numeric0,1.169485s; one actual-run-hook test. Every partial DETAIL split waits;
  full line stops; base Fatal retained; actual `base.run` enters the local hook;
  missing diagnostic file still leaves numeric outcome and abort saved.
  This is separate supplementation, not a claim that host01 ran the later hook.
- `prepare01.wait.json`: numeric0,2.925872s.
- `dryrun01.wait.json`: numeric0,3.980799s; exact private command generated,
  no console/CSV/simulator execution.

## Prepared Identity

`prepared01/plan.json` SHA256:
`49ffb74caba23b096d9addb009511a4d92e21f51c9182379d839b345e53978a1`.
818 pins; owner contract and immutable reference raw identity are explicit.
`prepared01/ready.json` SHA256:
`f1f0dfde222eeb36e11243b800dc113b487102f45333ad11b03aa6df385e77f8`.

The ready file contains the exact future systemd argv. Replace only its
independent ENTRY-review and parent runtime-admission placeholders with actual
paths/hashes after review. `replay.approval_gate` defines the existing schema;
preparation alone does not authorize launch. Do not modify the pinned worker.

## Time Estimate

Measured comparison proxy, not this DUT: accepted M9 unboxed FP16 full17920
`fp_compare_unboxed_full17920_vcs_m9_plan01/prepared02` child6687.051487s,
firmware_to_CTRL2665788. Scaling by this reference's1126049 instructions gives
2824.66s (47.08min). Reduction latency and system throughput differ, so this is
only a planning proxy, not a completion guarantee. Fixed10800s remains the hard
simulator limit; a timeout alone is not evidence of a hardware deadlock.
