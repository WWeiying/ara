# VSTU Public-Port Result

`current01`: **6/6 scenarios, 12/12 stores PASS**. One compile (25.08 s), one
bounded VCS invocation (10.64 s including startup). No fixture revisions or
reruns were needed. No production RTL changed by this test owner. Full source
review, predeclared oracle and exclusions are in README.md; this is real VSTU
with modeled public peers, not real AddrGen/MMU/AXI fabric or full-SoC signoff.

## Identity and Evidence

- VSTU: `139b27c0784c867b7a6032665c1634bb4b843ec2d9be5c4a3c6cb6d8fd2919f2`.
- TB: `188f25b37b41a5525d260dbbbf3abe72ea507844515767c544aae4ee2426502e`.
- Runner: `09c0f782ddcf118cf804c2029192b2e29bce6926b27f018a0f57d7dc5d7addb0`.
- Immutable copied inputs and hashes: `current01/frozen/`, `current01/pins.json`.
- Actual inputs/events: `current01/run.log`, `current01/cycles.csv`.
- Machine result: `current01/status.json` (`PASS`, frozen hashes verified).

No original Linux/ELF testcase is claimed. These are independently constructed
public-interface regressions for the documented ordered skip/exception/B
contract. No baseline-vs-candidate speed claim is made: VSTU itself is unchanged.

## Measured Outcomes

Cycles are local to each reset-isolated scenario. `done` below is the registered
public `pe_resp_o.vinsn_done` sampled on the next clock after the combinational
completion decision; B handshake and marker acceptance can share the earlier
edge. All checks use public inputs/outputs, not private queue counts.

| Scenario (owner0) | Descriptors / skips | W beats / B | Marker offered / accepted | Last B / done |
| --- | --- | --- | --- | --- |
| All skip, e16 VL20/start3 | 17 / 17 | 0 / 0 | none | none / 24 |
| Sparse prefix, exception7 | 8 / 5 | 2 / 2 | 15 / 31 | 31 / 32 |
| Same, both prefix B error | 8 / 5 | 2 / 2 | 15 / 31 | 31 / 32 |
| Normal masked VL20/start3 | 17 / 11 | 6 / 6 | none | 37 / 38 |
| Normal vm1 VL32, two-beat burst | 1 / 0 | 2 / 1 | none | 13 / 14 |
| First active element fault at start1 | 1 / 0 | 0 / 0 | 7 / 7 | none / 8 |

- All-skip owner0 held WREADY low throughout. The trace has zero WVALID cycles;
  all 17 tokens still retired, with no generated B response and no B-ready pulse.
  Two predicate/data windows were supplied, starting from nonzero vstart3.
- Both prefix-exception scenarios wrote active elements1/4 on cycles8/12 with
  strb `0000000c` / `00000300`; the five other prefix elements were skips.
  Marker7 remained unaccepted for cycles15-30. Responses arrived at27 and31;
  only at31 did the terminal descriptor handshake and completion occur.
- Error scenario returned SLVERR then DECERR. Registered error at32 was
  ST_ACCESS_FAULT, VA `0x40001002`, vstart1: the first failed W burst, not the
  later error or marker7. The successor had no residual error/abort pulse.
- Unmasked control used WLAST0 then WLAST1 at cycles7/8 and exactly one B at13,
  exercising burst accounting rather than only size1/len0 descriptors.
- Every case's owner1 was a new masked e16 VL9/start2 store with different
  data/VID and old EEW64, after owner0 had used old EEW8. Without reset or flush,
  each produced exactly two checked W/B, seven descriptors/five skips, one
  completion/done, and public idle1 after running-ID release. Post-done guard
  cycles detected no duplicate completion. All six owner0 stores also reached
  idle1; no stale input word was concealed by a flush.

## Input and Output Layout

Sequential source byte `b` in a 32-byte lane word is placed independently as
`lane=(b/E)%4`, `slot=bitreverse(b/(4*E), log2(8/E))`,
`offset=slot*E+b%E`. Data uses E=1 for owner0 and E=8 for successor owner1;
predicate bytes use E=2 for e16 in both. This corresponds to VSTU's separate
old-source-EEW and current-mask-EEW contracts. The oracle never invokes DUT
`shuffle_index`: expected W data is the linear architectural byte pattern at
the AXI byte address, with the independently calculated complete strb and
WLAST. Every strobed byte is compared, not merely a checksum or element count.

## Boundary

This establishes skip progress, ordered terminal-marker drain, delayed B
accounting/error priority, and isolated-owner cleanup under the modeled
protocol. It does not establish translation suppression, AW publication,
dispatcher trap/FOF behavior (stores have no FOF), speculative future operand
cancellation, or concurrent younger store acceptance. The existing
`commit_cnt == 1` exception-entry restriction still requires upstream ordering;
the tested successor is deliberately admitted after prior done. No new broad
matrix, random testing, or full image build was started.
