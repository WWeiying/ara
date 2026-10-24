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
