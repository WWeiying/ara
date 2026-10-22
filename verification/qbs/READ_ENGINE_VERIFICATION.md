# Reader Interface Contract Evidence

The added tests in `qbs_read_engine_tb.sv` exercise the standalone reader's
translation interface with a synthetic page mapping. They are not Linux boot,
CVA6 MMU, page-table-walk, TLB, privilege/PMP, ASID, or `sfence.vma` proof.
PMA is allowed in these added cases; its address/span is checked, not its policy.

## Fixed Markers and Hypotheses

The runner should require all four markers in each MMU variant:

```text
[QBS_READ_CASE] nonidentity_unaligned PASS
[QBS_READ_CASE] noncontiguous_pages PASS
[QBS_READ_CASE] second_page_fault PASS
[QBS_READ_CASE] post_fault_reuse PASS
```

| Contract | Stimulus | Discriminating evidence and failure conditions |
| --- | --- | --- |
| Nonidentity, unaligned | 106 bytes at VA `0x4001200fc3`, tag `0x91`; first page maps to PA page `0x283a50000` | Exact full AR bundle, 64-byte aligned PMA span, first lane 3, compacted byte data/strobes, logical offsets and tag. Reject identity addresses, padding bytes, excess/missing payload or completion. |
| Noncontiguous pages | Same transaction; next VA page `0x4001201000` maps to PA page `0x915b7000` | Two translation responses; ARs `0x283a50fc0`/len 3 and `0x915b7000`/len 2. Payload split 61+45, seven R beats, one completion. Both ARs outstanding before R release; deliberate AR, payload and completion backpressure. |
| Second-page fault, clean drain | Older 64-byte range/tag `0xa0`, crossing range/tag `0xa1`, queued range/tag `0xa2`; fault the crossing range's second page | At exception sampling: three accepted ranges, two accepted ARs, no accepted R, one queued range. No AR/PMA for the faulting page or queued range. Eight legal R beats drain with metadata advancing but no payload/completion. Fault remains MMU/tag `0xa1`/VA `0x4001201000`, exception valid/cause 13/tval equal to that VA. |
| Second-page fault, older error | Same setup, SLVERR only on beat index 1 of the oldest physical burst | The initially pending MMU fault is replaced by AXI-response/tag `0xa0`/VA `0x4002400110`, with zero MMU exception. Remaining R drains; legal RLAST must not fabricate a protocol fault. |
| Post-fault reuse | After each fault is acknowledged, retry 21 bytes at formerly faulting VA page + `0x23` with the failed tag | No DUT reset or counter clear between fault and reuse. Explicit PA/len, 13+8 bytes, two R beats, one completion and sequence 3. Final reader/slave queues empty, busy low, range ready high. |

The first two markers share one discriminating transaction; they are not two
independent simulations. Each fault variant and its reuse emits a named
`[QBS_READ_SUBCASE]` PASS. The last two aggregate markers require both variants
and both reuses to complete successfully.

## Timing and Oracle

- New scenario inputs and terminal checks are driven/sampled at negedge. The
  range sender holds VALID and its payload until the posedge monitor records an
  actual handshake, then withdraws VALID at negedge. Data-ready changes at
  negedge. The existing registered MMU/AXI slave state updates by posedge NBA.
- `contract_monitor` samples interfaces and old registered state at posedge,
  before NBA. Its blocking bookkeeping is read by tasks only on later negedges.
  It never treats a VALID level alone as acceptance. DUT event counters sampled
  at that edge are compared with the monitor's counts from preceding edges.
- The expected PA bursts and translations are explicit tables. Payload and
  metadata expectations do not read the DUT planner, DUT response metadata, or
  `model_paddr`. Independent R-handshake progress determines expected
  bytes-left, beats-left, cursor, offset, lane and error-drain state; DUT metadata
  is only the value being checked. SLVERR targeting is restricted to the oldest
  AR address so the second burst remains legal.
- The planner can translate while both burst slots are occupied: after the
  crossing range's first AR, it advances directly to second-page TRANSLATE.
  Slot availability gates AR, not MMU requests. The queued third range is
  accepted before that first-page AR even in combinational-MMU mode. The fault
  discovery assertions enforce these prerequisites instead of assuming them.
- Fault and completion outputs are held unacknowledged for at least four
  sampled edges. The oracle remains active for four idle cycles after terminal
  acknowledgment to reject duplicate/stale output. Each finish checks busy,
  range/burst/slave queue occupancy, pending MMU and all output valids.

## Trace and Execution

Each subcase produces at most 256 cycles of `QBS_READ_TRACE`, `QBS_READ_IO`, and
`QBS_READ_OUT` records, then fails on timeout rather than truncating evidence.
Records are explicitly `pre_NBA`; epoch plus cycle identifies reused tags.
They include request/AR/R/data/terminal valid-ready-fire, range/burst FIFO
occupancy and pointers, planner cursor/sequence, response metadata progress,
fault selection and event counters. This module has no PC/instruction or spill
buffer; none is claimed. There is no separate combinational next-state bus;
successive records show the registered state transitions.

`translation_count` counts sampled responses, including exceptions; `r_beat_count`
includes discarded drain beats; `payload_byte_count` counts only delivered bytes.
`outstanding_max` and `outstanding_full_cycles` measure burst FIFO occupancy,
not accepted logical ranges. Counter baselines preserve accounting over reuse.

Use one compilation and two executions: default delayed MMU and
`+COMBINATIONAL_MMU`. Both retain legacy cases and all six stalled-AR fault
cases by default; do not pass `+QBS_SKIP_AR_FAULT_TESTS` for this evidence run.
The test plan and probes were reviewed before compilation; no functional RTL
was changed to make these scenarios pass.

## Measured Result (2026-09-22)

`make -C verification qbs-read-contract QBS_READ_OUT=<new-directory>` snapshots
the four SV sources and AXI header, compiles once, then runs both MMU modes.
It refuses a nonempty output directory, requires all case completions and the
legacy stalled-AR matrix, rejects simulator errors/nonzero exits, and detects
source changes during the run. A first failed variant stops the suite for
trace analysis instead of automatically retrying.

Evidence: `verification/out/qbs-reader-linux-contract-20260922/summary.json`.

| Stage | Result | Host elapsed time |
| --- | --- | ---: |
| VCS compilation | PASS, no reported compile warnings | 24.076 s |
| Delayed MMU | PASS, all added and legacy scenarios | 10.693 s |
| Combinational MMU | PASS, all added and legacy scenarios | 10.693 s |

Each variant contains five named subcases: the nonidentity cross-page read,
two fault-drain variants and their respective no-reset reuses. The four
aggregate markers are coverage categories, not four independent simulations.
For example, the delayed run ends the last reuse at epoch 5/cycle 19 with
range/burst/slave queues empty, sequence 3 consumed, and 21 payload bytes
delivered; cumulative fault-plus-reuse counts are 4 accepted ranges, 4 MMU
responses, 3 ARs and 10 R beats. The flushed queued range has no AR.

This is real reader RTL evidence using a behavioral MMU/AXI slave. It does
not establish CVA6 page-table/permission correctness, custom-op atomic commit,
Linux hidden-context isolation, or a board/model pass.
