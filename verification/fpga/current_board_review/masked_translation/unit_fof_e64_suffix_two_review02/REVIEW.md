# Final Owner-Delta Entry Review

Decision: **NO_BLOCKER** for the exact prepared M9 two-single plan. This closes
the worker-owner P1 in review01; its historical HOLD remains unchanged.
This is entry acceptance, not a DUT result or physical MMU-activity proof.

- Plan SHA256: `3bc80c42d8e6bf7f722d81184ef8fc4bcac099e2518547292f5172665324e949`.
- Machine-readable review: `result.json`, SHA256
  `eb3c560dee1650dc0f84f032375713b96108e1e7a3e47e2871d8cad23eceed90`.
- Owner checker SHA256: `b840dbf0ab8af33f4a86c69a0fc70ed0127c4654590cf275d3dfe4877637dcd3`.
- Two jobs, 1800 seconds/case, 3900-second worker and 4200-second service;
  existing no-build/no-retry/no-FSDB constraints remain.

## Narrow Findings

1. The four required sites are the actual helper old-vd load (index1), mask
   load (index2), ordinary/FOF target (index3), and result store (index9).
   Exact PCs/encodings come from each prepared SoC spec. Each must have a
   matching architectural owner, CVX request/nonexceptional response,
   retirement, and at least one fully completed backend allocation.
2. At the actual retirement sites the inherited scalar CSR model supplies
   VL8/e64m1/vstart0, rather than assuming eligibility from the label.
   The target additionally checks the full 16-byte mask `[15,0,...,0]`
   and base `0x40000fe0`: four active prefix elements and four masked suffix
   elements. These are neither VL0 nor all-off cases. No suffix exemption
   or allowed target fault was added.
3. The frozen M9 monitor emits architecture sequence, original instruction,
   transaction and VID in the fields consumed here, and emits done before
   allocation for same-cycle VID reuse. The checker preserves that ordering
   and rejects unmatched/reused/pending backend ownership. It does not
   impose a guessed exact number of maintenance allocations.
4. `checker.artifacts()` actually calls `source_owners.analyze()`, requires
   the inherited exact PASS plus the four-owner successor signature, and
   matches row/retirement/cycle counts against generic validation. The
   subclass passes every unchanged row to the sealed full data/CSR checker.
   Both generic and source checks remain required, not alternatives.
5. Independent focused Host execution passed two valid owner streams and
   rejected deletion of each of four complete alloc/done pairs in both
   scenarios (8 negatives), with the expected site-specific rejection.
   Existing host02 records actual rc0/44 gates including orphan/wrong-owner,
   empty VL/start==VL/wrong mask; these older gates were read, not rerun.

The actual plan pins the new owner module and worker/checker. Relevant delta
inputs were hash-checked before/after this review. Accepted source/reference
review01 is reused; the old732 pins, references and large CSVs were not
re-traversed. No worker/live-service query or DUT launch was performed.

Use this directory's `result.json` and its SHA above for the existing worker
`--parent-review` / `--parent-review-sha256` fields. The parent's existing
two-case launch authorization requires no additional review layer.
