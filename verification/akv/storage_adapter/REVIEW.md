# Legacy Repacker Static Review

Date: 2026-10-24

## Conclusion and Evidence Boundary

No blocking correctness defect was found in the reviewed adapter or updated TB
under the stated producer/consumer contract. The new TB closes the previously
identified no-idle row-identity transition and final-fragment latency checks.
This is a source review, not a simulation acceptance receipt.

Only this new document was written. No RTL, TB, runner, existing report, or
canonical source was changed. No build, simulation, or worker-status inspection
was performed. The unit03 source-pins inventory was read solely to check source
identity and that this new document was not an existing pinned input.

Reviewed files, relative to this directory, match
`verification/out/akv-legacy-repacker-unit-20261024-03/source-pins.json`:

| File | SHA-256 |
| --- | --- |
| `akv_legacy_repacker.sv` | `78ce01557cfdc226b1d6102f88e47afbfef45f54b7735206b88f73e3f45f0a3b` |
| `repacker_tb.sv` | `a515891f1bb6e9573df6bf095cd6478a392b3459d581d2eb34001220ac30f5c8` |
| `run_unit.py` | `264099a7005050c37f2b18dcb2e7bd933a9b29f2328a2082a4fe6345366661d4` |

## Updated Testbench

- `repacker_tb.sv:102-109` drives two 128-byte rows with distinct tags on
  consecutive cycles, without a drain between rows. At the first row's last
  output, the scoreboard changes the expected identity and resets its offset.
  This checks the overlap of an old registered emission with a younger row's
  stage0 fragment. The final completeness check rejects a missing second row.
- `repacker_tb.sv:24-48` records each final input capture at a positive edge and
  checks the final output at exactly capture cycle plus two. Both timestamps
  are recorded in one monitor; stimulus changes at negative edges, and the
  monitor samples pre-NBA output values, as a synchronous SRAM input would.
  Current completed-row tags are unique, so an old timestamp cannot satisfy a
  later row's latency check. This establishes the expected output-consumption
  boundary in the TB, not physical macro timing or an instantiated SRAM test.
- The independent byte function, tag/offset checks, final-word check, poisoned
  invalid input bytes, and row completeness checks remain intact. All even
  source alignments modulo 16 are exercised for 128/192/256-byte rows, with
  gaps as well as consecutive fragments. The new chained rows are aligned and
  equal-length; they do not exhaust mixed-length or unaligned row transitions.
- Abort cases cover all seven nonzero even pending occupancies and a registered
  emission with a younger staged fragment. Output during those abort scenarios
  is forbidden by the scoreboard, followed by a new-identity recovery row.

The exact successful-output accounting is:

```text
original 32 rows: 8 * (128 + 192 + 256) + 7 * 256 + 128 = 6528 bytes
new chained rows: 2 * 128 = 256 bytes
unit03 total:    34 rows, 8 aborts, 6784 bytes, 424 writes, 34 latency checks
```

`run_unit.py:15-16,64-67` derives the byte/write totals and requires the exact
full-line summary, with 34 latency checks. Aborted data is not included in the
successful-output total. The parent's reported unit01 count-checker failure and
unit02 PASS were not independently re-audited here; unit03 remains unclaimed by
this review until its own terminal evidence is checked.

## Adapter Contract and Integration Conditions

- Input valid must represent an accepted payload fragment, excluding descriptor
  traffic. Strobes must be nonempty contiguous low bits, with an even byte count
  from 2 through 16. Offsets are logical byte counts within one contiguous row.
  Arbitrary sparse writes, holes, reordered rows, and interleaved tags are not
  supported. The simulation assertions enforce these assumptions but are not
  synthesized input validation.
- Pending data is masked and zero-padded before joining the next fragment.
  Pending occupancy is at most 14 bytes, the combined length at most 30 bytes,
  and at most one complete 16-byte word is emitted per cycle. The 9-bit row and
  position fields represent 256 without wrap. Successful row completion leaves
  no partial word. Architectural legacy D96 support is not implied by testing
  the adapter's 192-byte capability.
- Registered outputs retain their own tag and offset. Metadata may remain stale
  while write-valid is low; consumers must qualify it by valid. There is no
  output ready signal: the destination must accept every asserted write at its
  clock edge. Emit full byte enables at the existing half-row SRAM interface.
- Abort suppresses an outstanding registered write combinationally and clears
  stage0, pending, active, and emit validity at the edge. It cannot undo writes
  already consumed by SRAM. Connect abort to the failed owner's fault handling;
  do not wait for busy to clear before aborting an incomplete row. Pending state
  must not be cleared at ordinary AXI burst or page boundaries.
- Preserve committed Q contents during REFILL. Clearing transient repacker state
  is not clearing Q storage or changing the existing context-invalid-on-fault
  policy. Clocking must cover the final required write edge, and the next command
  acceptance must observe no stale staged write from the previous owner.
- Preserve the current v2 K/V aligned direct-write bypass. The present v2 store
  has combinational write steering, not eight registered write-data copies.
  Neither this adapter nor this review demonstrates per-bank FF removal, area
  savings, unchanged v2 latency, or any performance improvement.

Actual SRAM steering, read/write exclusion, engine completion/write-busy wiring,
fault/ownership drain, and v2 bypass cycle equivalence remain integration gates.
Active-reset recovery and malformed-input rejection are not exercised by this
positive TB. No production integration, formal equivalence, SoC result, or PPA
claim follows from this static review.
