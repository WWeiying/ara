# Fullstream Source / Context / FP Gate

Successor only. No accepted predecessor, production RTL, API, or ISA changes.
Default operation prepares snapshots and runs host tests; it never invokes EDA.
The parent reviews the bundle before a separately authorized VCS execution.

## Accepted Inputs

- Context/FP: `resident_pv_context_fp_agent_20261108_01`.
- Source/import: `resident_pv_import_agent_20261108_01`.
- Both must retain PASS, source/image identity checks, all inherited pins,
  closed report artifacts, and the original independent SoftFloat body bytes.
- Four real frozen StA operand_queue instances use DataBufDepth=2,
  FPUSupportNone, NrLanes=4, VLEN=1024, AccessCmdPop=1, and the frozen lane.sv
  command struct. CmdBufDepth remains VstuInsnQueueDepth+MaskuInsnQueueDepth=5.
  Commands are EW16, elem_count=96, conversion None, non-reduction.

Source layout is unchanged: six registers, 24 words per lane, sixteen reserved
seed words with eight-word head stride, then eight groups of eight interleaved
coefficient pairs. Inactive seeds and coefficient tails have nonzero poison.
Active seeds and coefficients are transported from original accepted records.
The independent natural halfword offsets are lane+{0,8,4,12}, low to high.
No payload arrays are added to the importer; only testbench helpers pack sources.

## Minimal Commit Guard

`akv_resident_pv_cluster.sv` is a copy of the accepted context snapshot with
exactly two changes, mechanically checked by host tests and preparation:

```systemverilog
input logic commit_permit_i,
.lane_result_valid_i(lane_result_valid & {4{commit_permit_i || commit_authorized_o}})
```

The group already holds lane ready low before commit. Masking group input valid
blocks authorization itself, even when external write-ready is high. Once
authorized, the existing sticky authorization continues to expose lane results.

The parent-side test harness permits commit only after error-free import drain
and error-free reader completion. Reader completion/error is latched because its
done may retire before the fixed source tail. This gate does not infer source
emptiness from FP or reader completion.

Importer done remains held until overall transaction retirement. Both success
and error paths gate cluster done_ready on import_done, reader completion, and
reader retirement. Only the accepted overall done acknowledges importer done.
Cluster ownership therefore remains held through source drain, FP completion,
and final acknowledgements. Abort is forwarded to importer, reader, and cluster;
no queue flush is used. An ordinary following command sentinel must survive.

## Exactly 69 Transactions

Normal run: the accepted 66 selected cases, including the three real no-injected-
stall replays, keep original per-lane bodies, stream bytes, FMA operands/results,
rounding modes, flags, commit data, and independent native VMFPU probes/checks.
Totals remain 36,976 FMAs and 2,544 architectural writes.

Separate guard run: three copies of the original real D128/H2/T9 record, changing
only header IDs. All 1,728 FMA expectations remain original:

1. Stop issuing after word 17 per lane, leaving six unused source words. Wait
   until all FP returns and private results exist, then hold external write-ready
   high for twelve cycles. Neither commit authorization nor write-valid may
   appear. Release the tail, drain all 24 words, and complete normally.
2. Repeat the gap and abort before authorization. Keep the tail blocked after
   cancellation. Wait for cluster error done, then hold it for at least twelve
   additional cycles with done_ready low, importer still draining, and no
   architectural writes or acknowledgements. Only then release the tail and
   acknowledge overall completion after full source/reader/FP drain.
3. Reuse successfully without any reset/flush between the guard transactions.

The cancelled transaction changes only architectural expectations to zero
writes/acks/error flags; every FMA, stream, seed, return, and native-probe check
remains active. Guard success/reuse produce 128 total writes. The normal checker
is invoked unchanged; the guard checker separately requires delayed-tail and
cancelled-terminal receipts. No further cases are added.

Each guard transaction also holds each actual VMFPU result for two observed
valid/not-ready edges. The original ownership checker still requires nonzero
private backpressure; no check is relaxed. Preparation fixtures alone cannot
prove that coverage: the first frozen run passed the normal checks but failed
the guard ownership check because its pre-adapter input gates never produced
adapter-visible private stalls. That failed run remains unchanged. A fresh
successor adds this explicit output handshake test and exact per-lane receipts.

Every transaction independently checks 24 imported words, one source command
pop, and one intact following ordinary-command sentinel per lane. Operand issue
uses real queue credits and one-cycle responses; controlled source/downstream
stalls test skew and backpressure. This is not actual VRF arbitration or SoC
acceptance. Real no-stall records report first source issue to import done, last
FP return, final acknowledgement, and overall retirement, not whole-model speedup.

## Preparation And Review

```sh
python3 -B verification/performance/resident_rvv/pv_fullstream/test_run.py
python3 -B verification/performance/resident_rvv/pv_fullstream/run.py \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_fullstream_AGENT_UNIQUE
```

Preparation copies explicit accepted context/import snapshots, the selected
production/header closure, and all six successor files. Compiler paths and
include directories point into the new frozen bundle. Inherited documentation
pins remain enforced. `cluster.diff` and `tb.diff` support parent review.
`source_harness.svh` is the only new testbench source transport include.

`prepared.json` must say PREPARED_NOT_EXECUTED with host_tests_pass=true.
Host tests do not compile SystemVerilog or establish gate acceptance. Launch only
after parent authorization, using the bundle's frozen runner:

```sh
python3 -B OUT/inputs/run.py OUT --execute-prepared --parent-reviewed
```

The parent should directly own this worker in a transient systemd service,
capture stdout/stderr separately, and confirm actual VCS execution. The shared
execution budget is 540 seconds for host tests, compilation, and both simulations.
No synthesis, Verilator, URG, or API/ISA changes. Stop on the first failed run;
preserve its evidence and report a hypothesis before changing RTL.

Source/image identity is rechecked after execution. Artifact hashing uses a
closed-file allowlist and excludes live service logs. Do not edit any local
successor file while its frozen bundle is under review or execution. This is the
last combined prerequisite gate before the parent's safe production-integration
decision, not authorization to expand the prototype or start additional gates.
