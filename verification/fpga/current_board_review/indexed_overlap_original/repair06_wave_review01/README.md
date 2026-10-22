# M6 Indexed Overlap: Bounded Wave Review

Status: **MEASURED_M6_OLD_FAILURE_PATH_CORRECT_IN_BOUNDED_WINDOW**.
Final machine evidence: `finding.json`; detailed wave ledger:
`wave_findings02.json`; architectural CSV reconstruction: `ledger.json`.
This is not whole-50-round acceptance or a service-exit audit. No DUT was
started, no RTL changed, and no original artifact was written by this review.

## Acquisition and Recovery Provenance

The original console contains the actual
`INDEXED_PROFILE_CLOSED_AT_1000000NS` marker at line 34442. The pinned Tcl
disables and flushes dumping, then resumes simulation; it does not close the
writer/container. Two hash samples two seconds apart found all 13 original
FSDB-family files stable. Byte-identical private copies are in `inputs/`.
`acquisition.json` records the complete before/after hashes and copied pins.

The first metadata check incorrectly inspected stdout rather than the tool's
stderr; that failure remains recorded. Subsequent bounded scope extraction,
then direct bounded conversion without scope extraction, both rejected the
still-open FSDB container. These are offline acquisition failures, not DUT
failures. Their logs remain `export.log` and `export02.log`.

Vendor `fsdbrecover` was run once on the private copy and its copied sidecars,
producing **derived** `recovered.fsdb`. The tool merges temporary index/data
files; it does not repair signal values. No values or timestamps were supplied
or fabricated. No `-del_src` or `-cp` option was used. Exact recovery/export
commands and tool identity are in `recovery_export.json`; vendor logs are in
`fsdbrecoverLog/`. Original-family and private-copy hashes matched before and
after that operation. Finalization independently rechecked every copied pin.

Both original-copy and recovered summaries report **100fs**, maximum tick
10000000000, exactly **1000000ns**. The successful export covers only
367700..369300ns (1600ns), safely inside that boundary. `recovered_focus.vcd`
contains the vendor-exported selected scopes; `focused516.vcd` further filters
it to 516 named signals without changing their samples. No full-wave export
was performed. Wave clock period is 10000 ticks = 1ns; pre-edge wave time is
CSV monitor cycle + 15.5ns. Console `$time` rounds half-nanosecond events.

Main-file SHA256 identities:

| Artifact | SHA256 |
| --- | --- |
| Acquired raw original and immutable private copy | `4b5439084dd6e337a3005116a3358191ef7251d81a9f3374003cc7b7f1340e96` |
| Recovered derivative | `6ab468a2209d4623c738aa8f5e2b4c49883ed1c3859cf11d3f3fd611d3589e5d` |
| Later writer-owned original observation | `c05374791d84f15edf75b030d5af1735503957b0bd000f5d3e27bf6e05f2c3d4` |

At finalization the original main file had grown from 7267393 to 7297805 bytes
and its sidecars were gone. Thus the original did **not** remain byte-identical
forever: it changed after the successful recovery/export stability checks.
The later state is recorded separately in `finding.json`, consistent with
writer container finalization but not proof of simulation success or service
exit. The private raw acquisition remained unchanged. The recovered container
is not claimed byte-identical to the later original.

## Measured Sequence

The M5/M6 private ELF hashes match:
`5a73bf57dc9d9cef6136ec8daa53e409c77abd5e0e47645d403392df5310347f`.
M6 image identity and input/command identities are bound in `finding.json`.

| CSV cycle | Observation |
| --- | --- |
| 368497 (settled wave 368512.5ns) | CSR vstart15, mixed VS2 layout true, surviving `reshuffle_req_d=010`; v4 EW32/v5 EW64 |
| 368501 / 368516 | Source v4 EW32->EW64 maintenance allocated / completed |
| 368519 / 368536 | Snapshot capture allocated / completed; all 4 lanes x 8 words captured after source completion |
| 368540 / 368555 | Destination EW64->EW32 maintenance allocated / completed |
| 368557 | Original VLXE allocated, VL32/vstart15, `old_eew_vs2=EW64`, snapshot replay enabled |
| 368561 | Snapshot word4 replay: lanes `[17000,4000,11000,1e000]` hex; queue valid, live VRF valid false, physical v4 tag EW32 |
| 368562 | Same words visible at AddrGen input, raw index `0x17000`, saved old EW64 and replay flag retained |
| 368576 | Actual MMU request VA `0x40017000` |
| 368588 / 368589 | MMU load fault cause13/tval `0x40017000`; AddrGen fault vstart16 |
| 368718 / 368722 | Architectural handler reads mtval `0x40017000` / vstart16 |
| 369018 / 369154 | Original address check succeeds / handler MRET |

M5's same fault16 had architectural mtval `0x400040017000`. M6's nine handler
checks at this fault all match. The old concatenated-index failure is absent
at this measured point: conversion precedes capture, replay supplies the saved
EW64 word despite the destination EW32 layout, and the actual translated
request and architectural fault agree.

For this original VLXE's data write at cycle368588, all lane addresses are17
and byte enables are `[0,0,0,0xf0]`. Applying the pinned four-lane EW32 shuffle
and v4 base address maps these to logical bytes60..63, **element15 only**.
Prestart elements0..14 have no enabled bytes in this data write. Maintenance
layout writes are separate; this is not a claim that no VRF write occurred.

## Evidence Boundaries

- The final settled mixed-layout flag and surviving `010` are measured.
  Earlier procedural assignments within the same `always_comb` are static
  reconstruction, not separately sampled pre/post states.
- Backend allocation/completion uses actual CSV uop events. `seq_ready` is a
  delayed load response and is not treated as the issue handshake.
- Replay queue-valid and requester replay metadata are measured. Queue-ready
  gating is supported by frozen RTL; a separate undumped ready is not invented.
- AddrGen input word is measured with whole-word ready0, not mislabelled as a
  full-word dequeue. `idx_op_cnt` is remaining count, not logical element index.
- CSR/check/MRET evidence comes from the copied CSV prefix through cycle600000.
  No terminal result, full50 oracle, controls, or service state is inferred.

`finalize.py` passed all causal-chain assertions and binds the final evidence
hashes. Earlier `wave_findings.json` is an intermediate offline analysis;
`wave_findings02.json` is the final detailed wave evidence.
