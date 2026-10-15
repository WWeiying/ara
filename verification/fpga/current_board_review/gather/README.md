# RVV-19 Gather Prestart Write

Focused real-MASKU VCS unit, four lanes, VLEN=1024. No force, hierarchical
injection, replacement MASKU, full-image build, Verilator, ZCC, or commit.
Only the gather byte-enable branch in `hardware/src/masku/masku.sv` changes.
The parent's SlideUnit read/commit patch remains intact.

## Provenance and scope

- Main-worktree `hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/repro/README.md`,
  short scenario `gather_restart` and section 4, supplies the generic
  e16/m1, VL2, vstart1, all-on `vrgather.vx` index0 fixture. That generic
  vx fixture was not board-tested; the genuine board-tested per-ELF gather
  cases below are separate provenance.
- The integration agent's `../integration/prepared/gather_prestart/original/`
  retains the assembly and C initialization: source element i = 1000+i,
  old destination = 91, required first two results = [91,1000].
- `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_verified_handoff03/rvv_small_gather02/`
  retains the genuine per-ELF single trials. For example, e16/m1 ops0 records
  prestart element0 expected91/actual61881. Its randomized source is different
  from the generic 1000+i fixture; this unit does not claim identical wrong
  values or replay all 83 cases.

This establishes current MASKU prestart write corruption, not an original
board stall cause, dispatcher/VALU integration, or a full software execution.
Original-source integration remains owned by the parent agent.

## Static path and hypothesis

1. Admission initializes `issue_cnt_q`, `processing_cnt_q`, and `commit_cnt_q`
   from VL, and index/output state from zero. Gather traverses the prefix.
2. ALU operands supply indices; scalar mode overrides the extracted index
   with `scalar_op`. The index FIFO retains full indices. The request FIFO
   broadcasts index/NrLanes, source register, EEW and end-of-stream flags.
3. Lane MaskB requests read one lane word containing that lane-local index.
   `masku_operands` buffers/deshuffles those source words. MASKU selects the
   indexed element and accumulates one destination element per issue step.
4. `out_valid_cnt_q` is word-local. `issue_cnt_q` starts at VL and decreases
   by one for each gather element actually processed, so `vl - issue_cnt_q`
   is the absolute destination position even across result words/stalls.
5. Before repair, `be_vrgat_seq_d` uses only vm/predicate. Tail BE restricts
   writes to VL but does not suppress prestart. Result queue ports expose
   the resulting enabled prefix write. Normal grants acknowledge writes;
   final grants follow one cycle later and allow instruction completion.

Falsifiable prediction: index0 is requested and source1000 is delivered,
then lane0/address96 writes data0x03e8 with BE03 despite vstart1. A source
selection bug would instead affect fetched data; a completion-only bug would
not account for the observed enabled prefix write.

Repair: AND the existing vm/predicate expression with
`(vinsn_issue.vl - issue_cnt_q) >= vinsn_issue.vstart` in all four gather
SEW BE assignments. Data computation, request traffic, counters, queues and
completion are unchanged. VCOMPRESS uses `be_viota_seq_d`, not this gather BE.

## Port model and checker

`gather_prestart_tb.sv` instantiates repository MASKU and its real operand
buffers. All stimulus/checks use ports; no internal DUT names are accessed.
Index ALU words are retained until handshake. Each lane independently queues
accepted gather requests and returns the addressed source word on MaskB;
no-data tokens produce no operand. MaskB never receives old destination or
golden data. Layout conversion uses an independent bit-reversal mapping.

The golden model uses stimulus indices and the architectural [vstart,VL)
window, not DUT requests or output values. The actual destination begins
with 91 and changes only on enabled external write bytes. Checks cover all
128 bytes, exact per-byte write counts, prefix/tail preservation, completion,
one last-request token, and drained responder queues. An all-zero BE result
transaction is legal and still receives its normal/final grants.

## Measured evidence

`before01/` pins the pre-fix source, testbench, dependencies, commands and
logs. `--expect-bug` does not redefine the golden result: it requires exactly
two wrong bytes, two prestart enabled bytes, and actual [1000,1000].

| Historical case | Before | After |
|---|---|---|
| Source request cycles / indices | 3,4 / 0,0 | 3,4 / 0,0 |
| Write cycle / address | 7 / 96 | 7 / 96 |
| Lane0 BE / data | 03 / 0x03e8 | 00 / 0x03e8 |
| Lane1 BE / data | 03 / 0x03e8 | 03 / 0x03e8 |
| Actual first two e16 values | [1000,1000] | [91,1000] |
| Prefix bytes / mismatched bytes | 2 / 2 | 0 / 0 |
| Completion cycles / requests | 9 / 2 | 9 / 2 |

The bounded 160ns test and cycle-stamped port trace discriminate the cause
without needing a larger waveform run. `after01/status.json` records the
post-fix suite outcome: **PASS, 12/12 cases**, each with zero prefix writes
and zero mismatched bytes. The suite includes historical/start0/unmasked/all-off,
start==VL, out-of-range scalar, vector-index and EI16-index cases, and
cross-result-word restart with alternating predicates at SEW8/16/32/64.
This is functional cycle-count evidence, not synthesized timing evidence.

Pinned MASKU SHA256:

- Before: `2d9b42dc9f4eb042477e650695fade114088dc19c7314f029165657cb2b06e30`
- After: `88692c2fc0edb6267d45edf43abce31b8e6be70e28a1e0adddc5dc1a11526a0d`

The working MASKU matched the after hash at handoff. Snapshot-to-snapshot
diff contains only the gather guard. VCS reports one expected TFIPC warning
for intentionally unconnected outputs, with all input ports connected.

## Reproduction

From the integration worktree, with an unused output directory:

```sh
python3 verification/fpga/current_board_review/gather/run.py \
  --out verification/fpga/current_board_review/gather/replay --regression
```

VCS home is `/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1`;
license server is `27000@t7920`. Each build snapshots all inputs with SHA256
pins. Compilation is bounded at 240 seconds, each test at 600 cycles and
30 wall-clock seconds. The runner stops on the first unexpected failure.
The archived pre-fix binary can be rerun with `+EXPECT_BUG`; do not roll back
shared RTL to reproduce it.
