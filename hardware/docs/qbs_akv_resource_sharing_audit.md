# QBS / AKV Resource Sharing: Static Preconditions

This is a current-source audit, not an implementation or PPA result. Resource
sharing remains an open item in `qbs_akv_efficiency_execution.md`; common module
source and downstream AXI arbitration do not mean hardware has been shared.

## Existing Resources

| Resource | Current Organization | Source |
| --- | --- | --- |
| QBS reader | One `qbs_read_engine` instance | `src/vlsu/qbs/qbs_engine.sv`, `i_read_engine` |
| AKV reader | A second physical instance | `src/vlsu/akv/akv_engine.sv`, `i_read_engine` |
| Reader queues | Two range slots, two burst slots per instance | `src/vlsu/qbs/qbs_read_engine.sv`, `QueueDepth` / `ReadOutstanding` |
| Legacy AKV payload | Two banks, 96 rows/bank, 256 bits/row: 6 KiB | `src/vlsu/akv/akv_context.sv` |
| AKV-v2 KV payload | Eight banks, 128 rows/bank, 256 bits/row: 32 KiB | `src/vlsu/akv/akv_v2_context.sv` |

The current VLSU owner barrier already makes special command ownership
exclusive. Two readers do not imply four simultaneously usable outstanding
transactions. Do not justify sharing by claiming a nonexistent concurrency
increase, or change outstanding limits while evaluating it.

The package defines eight Query rows and D128 F16, requiring2 KiB for Q.
`akv_engine.sv` deliberately routes Q writes to `i_context` even for v2
commands. Its v2 store contains K/V only. The two physical stores total38 KiB;
retaining all v2 KV plus Q requires34 KiB. The theoretical duplicate payload
capacity is therefore4 KiB, not6 KiB. This is neither a measured area saving
nor a permission to discard legacy accesses. Column capture registers,
pipeline state and SRAM-interface logic are additional resources.

## Reader Extraction First

Preserve current command admission, tags, translation/PMP checks, response
routing, completion backpressure and resident activation/KV contexts. The
reader has to remain clocked while its selected owner drains. Placing it
inside just the QBS or AKV gated clock would be unsafe for the other owner.

An owner transfer must not use the absence of a new AR as an idle test.
`qbs_read_engine.busy_o` includes queued ranges, planner state, held AR, burst
responses and pending completion. A fault is not published until burst
responses and stalled AR drain. The VLSU barrier also includes the registered
AXI cut, ordinary load/store state and prefetch state. Retain terminal-event
ownership through this boundary rather than switching a live reader's mux.

Before an RTL change, recover a pinned success and fault trace showing:

1. The old owner's last data/completion handshake and storage write drain.
2. Empty range/burst queues, idle planner, no stalled AR, no pending completion
   or translated request, and an empty downstream registered cut.
3. The next owner's first accepted command and correctly routed response.
4. Unchanged QBS activation and AKV resident context identity across the switch.

An old PASS summary alone cannot prove these cycle-level facts. If existing
waves omit any internal signal, record the missing evidence and use one
bounded, discriminating follow-up test rather than guessing from total cycles.

## Storage Sharing Second

Legacy F16 fills permit two-byte-aligned destinations. A128-bit incoming beat
may cross a256-bit row; alternating legacy banks handle both writes without
two accesses to the same single-port bank. The v2 writer instead asserts
16-byte alignment. Directly wiring the legacy writer into the v2 interface
would violate a supported access case.

A unified store therefore needs a checked legacy-to-bank write adapter,
retained Q storage, row/column replay arbitration, and the existing
publish-after-write-drain rule. REFILL must preserve Q; fault/reset must not
publish partially written state. Command exclusivity does not imply that
resident contexts can be destroyed between commands.

Evaluate reader sharing and payload sharing separately, with matched success,
page-boundary, backpressure, fault-drain, reset and resident-context reuse
tests. Compare command cycles and complete operators before accepting either.
No synthesis, PPA claim or RTL modification is part of this static audit.

## Existing Evidence and Next Discriminating Test

The archived `qbs_read_axi_20260908/fixed/run.log` exercises a stalled AR and
fault drain inside an independent reader. The accepted
`qbacc-soc-accept-20261023-02/neighbors/qbs_akv_handoff_smoke` checks successful
SoC handoffs with matched log, trace and ELF hashes. Neither artifact provides
one continuous cycle-level record combining owner transfer, injected delay or
fault, internal reader drain, storage write drain and resident-context identity.
Do not combine these independent PASS results into a claim that this boundary
has already been measured.

The smallest successor should retain the real VLSU and registered AXI cut,
start from `apps/qbs_akv_handoff_smoke/main.c`, and exercise a resident-context
reuse across a success handoff and a fault-to-other-owner-to-retry sequence.
Capture `command_fire`, `terminal`, both readers' range/burst occupancy,
planner state, held AR, pending completion, context write-busy, registered cut
state and resident context identity in the same bounded window. Check the
events before changing the physical reader organization. A validation-only
descriptor fault must not be substituted for an in-flight read fault.

## Isolated Reader Candidate

`verification/akv/shared_reader_candidate/` now contains a synthesizable
single-reader mux and a typed two-client interface. It is not in the production
source graph. Its accepted finite unit receipt is
`verification/akv/results/shared-reader-unit-20261024.json`: ten commands,
445 compared cycles, four faults, seven range completions and 4247 checked
payload bytes, plus three targeted ownership-assertion rejection runs.
The unchanged reader is the reference; this proves the mux's transparency
under the tested common history, not complete equivalence of two independently
resident engines or production integration.

The interface keeps the complete 16-bit tag. AKV adapters must zero-extend
their 8-bit tags and truncate only at the returning AKV boundary. Counter and
subrequest-sequence clear is the OR of accepted command pulses, independent of
active-owner registers. The future shared clock must OR the two enable signals
before one clock gate; do not OR two gated clocks. Old private reader probes
must move to the single actual reader, with explicit owner/command attribution.
Invalid owner closes client routing, but must not cancel a previously held AXI
or MMU transaction. Integrated owner lifecycle, write drain and the registered
AXI cut remain separate obligations.

## Storage Adapter Feasibility

Current `akv_v2_context.sv` writes the selected SRAM bank directly and has no
bank-local write-data pipeline registers. Do not claim savings by removing
nonexistent replicated data registers. Preserve this direct aligned-v2 K/V
path when evaluating unified storage.

The legacy alignment problem can be handled with a 16-byte repacker rather
than a second SRAM write port. The current reader compacts valid bytes into
the low byte lanes and emits a contiguous low-bit strobe, with monotonically
increasing logical offset per range. Legal F16 fragments contain an even
number of bytes, at most 16. Pending payload is at most 14 bytes, so a fragment
produces at most one complete 16-byte output and leaves at most 14 bytes pending.
Every complete row is 128, 192 or 256 bytes, all divisible by 16; legacy itself
supports 128/256 bytes, while 192 belongs to the v2 D96 path. Successful ranges
therefore finish without a partial 16-byte output. Burst/page boundaries must
not reset the pending bytes.

Aligned emissions can use the current v2 half-row write interface. A separate
logical 64-by-256-bit Q store needs only one half-row write per cycle, avoiding
the two-bank requirement caused by legacy fragments crossing 32-byte rows.
Actual macro availability, physical capacity and PPA are not established by
this logical shape. A legacy stage0 capture at E0, repack/emit register at E1,
and SRAM consumption at E2 can match the old final-fragment-to-final-write
latency; intermediate nonaligned writes necessarily move, so this is not a
claim of per-write cycle identity or measured performance.

The implementation must validate contiguous strobe, even byte count, offset
continuity and stream/token identity. Its internal accepted-byte count must
represent 256 without wrapping to zero. Emit metadata must remain independent
of the next range's stage0 tag. Abort must discard incomplete private bytes
without deadlocking on write-busy, and no old write may survive the next
command acceptance. A failed REFILL must not touch Q. General sparse writes
supported by an isolated SRAM primitive are not the producer contract of this
repacker; keep that scope explicit in its interface and tests. This is a
reviewed design direction only, not implemented unified SRAM.
