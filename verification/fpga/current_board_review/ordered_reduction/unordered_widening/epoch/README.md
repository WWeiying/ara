# Reduction Epoch Snapshot

Stable candidate VMFPU SHA256:
`e9b8c8c2aa952b76661b01fa0a4b53d87e2f1d7219beb40a42a4d6998c5f7b12`.

Baseline (comparison producer plus earlier reduction candidate):
`93bdb014aa4475aaf29dd28c2aacb76f765132fd41e21f4b299b5012efdb63d5`.

## Measured Cause And Fix

The independent full-SoC measurement is retained in
`verification/fpga/current_board_review/reduction_epoch/measurement01/capture01/`.
Its `finding.json` shows first RX at cycle 7107, faster lane 1 starting the
next reduction at 7124 and clearing the sole active bit, old lane-0 publication
at 7130 with pending NV=0x10 but live global activity=0, and wrong seed 0x7c01
written at 7131 instead of canonical 0x7e00. The end-of-pair CSR read is after
both global completions, so this is not a premature CSR read.

Each lane now captures global activity exactly when it consumes its first
internal RX token in INTER_LANES_REDUCTION_RX with transactions remaining
equal to `$clog2(NrLanes)+1`. SLDU requires every lane's source partial before
producing that first aggregate; later rounds require every first RX to be
consumed before any lane can finish. Local TX acceptance alone is unsafe
because the SLDU input buffers accept lanes independently.

The snapshot is held through publication and lane-0 VRF grant, then replaced
at the next reduction's first RX. Both pending-flag publication and exact
empty-seed selection use it. The shared result bus also transports tree
partials before snapshot capture, so seed bypass additionally requires an
architectural result request. No state, counter, handshake, or wait is added.
NrLanes=1 has one RX round and enters SIMD_REDUCTION before publication or
writeback, so its captured register is available even for an FP64 zero-fold.

## Unit Results

Artifacts: `/home/wangwy/fpga_runs/reduction_epoch_unit_20261010/`.

| Lanes | Baseline directory | Baseline failures / 144 | Candidate directory | Candidate |
| --- | --- | --- | --- | --- |
| 1 | before1-02 | 0 | after1-02 | 144 PASS |
| 2 | before2-02 | 59 | after2-02 | 144 PASS |
| 4 | before4-02 | 57 | after4-02 | 144 PASS |

All 432 before/after completion-cycle pairs are identical. Failures occur in
both 0->1 and 1->0 activity transitions, not 0->0 or 1->1. Case 8 is the minimal
FP16 sum, active sNaN-seed reduction followed by inactive finite-seed VL1:
2/4 lanes before return 0x7c01 with flags 0; after return 0x7e00 with NV=0x10.
The second result remains 0x3c00. Four-lane case 8 is 71 cycles both ways:
first RX cycle 751, younger lane-1 first issue 768, old publication 774 and
writeback/registered NV 775. Candidate snapshot stays one despite live global
zero; next first RX at 783 captures zero for the younger instruction.
The slow-source discriminator, four-lane case 10, accepts lane-0 first TX at
cycle 892 with global=0 but first RX at 929 with global=1. It directly rejects
first-TX capture while validating the later all-source-complete boundary.

Each lane count covers FP16/32/64, sum/min/max, all four activity transitions,
finite or sNaN second seeds, slow source delivery and VRF-grant backpressure.
Two reductions are queued without a fence; no reset between the 144 pairs.
Every pair checks first-RX barrier activity, one snapshot opportunity and flag
pulse per lane/instruction, exact result/count/address/BE, individual flag
ownership and the dispatcher's OR-all-data/OR-valid sticky flag behavior.

Real VMFPU/FPnew instances, independent real TX spill registers and real VMFPU
RX spills are used. The SLDU is modeled as complete-lane aggregate rounds with
independent response acceptance; operands are driven at the already-converted,
seed-neutralized interface. This is not a CPU, real operand-queue, real SLDU,
sequencer, CSR or whole-image test. Empty sNaN exact copy checks preserve this
implementation's permitted behavior, not universal Spike bit agreement.

## Preservation

Unchanged existing runners, all using candidate SHA above:

- `preserve80`: 80/80 unordered/widening PASS, matched to comparison artifact
  `unordered-preservation01`.
- `preserve166`: 166/166 ordered PASS, matched to `ordered-preservation01`.
- `preserve606`: 606/606 comparison producer PASS plus 648 format-bank checks
  and queued mixed-operation flag/tag ownership, matched to `after02`.

Every results.csv row in all three preservation sets is identical to its
pre-epoch-patch counterpart, including completion cycles, results and flags.
The counterparts are under `/home/wangwy/fpga_runs/comparison_nv_producer_20261010/`.

## Reproduce

From the integration worktree, choose a fresh output directory:

```sh
python3 verification/fpga/current_board_review/ordered_reduction/unordered_widening/epoch/run.py --lanes 4 --out NEW_BEFORE
python3 verification/fpga/current_board_review/ordered_reduction/unordered_widening/epoch/run.py --lanes 4 --out NEW_AFTER --vmfpu hardware/src/lane/vmfpu.sv --snapshot
```

Repeat with lanes 1 and 2. Inputs, commands, SHA pins, CSV traces/results and
top-level bounded FSDB are retained. `before4-01` and `after4-01` are retained
testbench compile errors from a missing package qualifier, corrected in -02;
they are not RTL measurements. No shared helper or original bench was edited.

VCS host only; no full build, Verilator, ZCC, URG or commit. Real epoch case
acceptance on the final integrated image remains the parent's responsibility.
