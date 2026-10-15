# Mask RAW Origin Boundary Unit

## Result

VCS `before02`: 22 completed data cases, 8 FAIL, 14 PASS; pure WAR control PASS.
VCS `after01`: identical TB, 22/22 PASS; pure WAR control PASS.
`before01` is retained as a harness compile failure (missing delta_counter
dependency), not an RTL result. No old results or expectations were changed.

Candidate ara_sequencer SHA256:
`f1d6095e1ade018b9225678a493438da04e7d84f68a956bdf7a116941bfafc5b`.
TB SHA256 in both runs:
`14aae0bffe9a9da8af335787591ec60355dbe9be491ea110c7ce05680a470c95`.
The source manifests differ only in `hardware/src/ara_sequencer.sv`;
extracted interface types and all other frozen dependencies are identical.
Each directory retains source hashes, provenance, commands, logs and status.json.

## Scope Review

The change at ara_sequencer's mask RAW classification (around line 648) keeps
the existing conditions and additionally waits for the known v0 writer when
`VSLIDEUP && stride >= NrLanes * ELEN`. It remains inside `!vm` and
`write_list_d[VMASK].valid`; it marks only that writer VID. It does not mark
the destination WAR readers later ORed into hazard_vm. The stride threshold
counts predicate bits/elements, not SEW-scaled data bytes. For four lanes it
matches the first nonzero MaskM word origin at 256 elements.

The existing per-instruction wait-complete propagation can conservatively
delay other operand requesters dependent on that same writer. This is not a
MaskM-only stall implementation. No request geometry or data layout changes.

## Measured Before/After

The eight failing baseline cases are IDs 1,2,3,14,15,16,18,19:
live producer, e8 offsets 256/512/768/257/511/1023 and e16 offsets 256/511.
All four lanes read X at cycle 14 before the selected word's write at
cycle 22, 31 or 40. After the patch their writer wait bit changes 00 -> 01,
and all four lanes read `ffffffffffffffff` at cycle 42, after completion.
Producer word writes remain at cycles 13,22,31,40.

For representative e8 offset1023 (case16), the actual sequencer publishes
hazard_vm=01, wait=01 at cycle6; real lane sequencers issue MaskM origin3,
length1, EW64 at cycle7. Actual requester VRF reads occur at cycle42 after
word3 write at cycle40. Baseline used wait=00 and read at cycle14.

All recorded fields of the other 14 cases are identical before/after,
including read/write/completion cycles. These cover no tracked hazard,
already completed producer, origin0 and in-word offsets, plus e16/32/64
legal origin0 boundaries. The separate real-sequencer WAR control stays
hazard_vm=01, lifetime=01, wait=00 in both runs.

## Evidence Limits

The unit instantiates real ara_sequencer, four lane_sequencers and four
operand_requesters. Architectural requests enter public ports. A modeled
LDU writes words0..3 through actual requester writeback ports; four-state
VRF storage records actual bank writes and samples actual MaskM read requests.
Completion is supplied only after all four lanes have written word3.
No forced state, internal injection or manually supplied hazard/wait bit.

This proves classification and actual request ordering, not a full original
program replay or final SLDU output. LDU execution and operand-queue sinks
are modeled. The independent parent SoC capture02 supplies original-program
evidence: word3 read103686.5ns precedes word3 write103689.5ns, producing X.
Original-case candidate replay remains the full pipeline's responsibility.

Run a new immutable output directory with:

```sh
python3 -B verification/fpga/current_board_review/large_offset_slide/mask_raw/run.py --out verification/fpga/current_board_review/large_offset_slide/mask_raw/NEW_RUN
```
