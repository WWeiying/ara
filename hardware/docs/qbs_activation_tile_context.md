# Capacity-bounded multirow activation context

## Purpose and integration boundary

This is the storage stage of cross-N activation reuse, not a completed matrix
optimization. `qbs_activation_context.ExtendedShapes` defaults to zero. The
engine, capability words, descriptor validator, reference model and runtime
still admit the established M1/Q8_K context only. No program may infer the new
shapes from this module parameter. Main and FPGA are not changed by this stage.

The target is to reuse the same quantized input tile across output tiles without
adding SRAM or changing accumulation order. It does not retain partial outputs
between commands. Long-K tiles exceeding the capacity still need a separate
striped-residency/partial-sum design; this stage does not close that milestone.

## Admitted storage shapes

With the parameter enabled, the primitive accepts these externally validated
combinations for Q8_K (292 bytes/block) or Q8_0 (34 bytes/block):

| Layout | Actual M | Stored rows per K block |
| --- | ---: | ---: |
| Row major | 1 | 1 |
| M4 interleaved | 4 | 4 |
| M8 interleaved | 5 through 8 | 8 |

K-block count is 1 through 32, and the entire payload must fit 4672 bytes.
M5..7 retain all padded rows in the existing layout; storage must not compact
away that padding. Row-major M2/M3 need multiple engine ranges and are not
silently interpreted as one contiguous interleaved slab.

Examples of the byte budget (not performance results):

| Activation | M | K elements | K blocks | Payload B |
| --- | ---: | ---: | ---: | ---: |
| Q8_K | 1 | 4096 | 16 | 4672 |
| Q8_K | 4 | 768 | 3 | 3504 |
| Q8_0 | 4 | 896 | 28 | 3808 |
| Q8_0 | 8 | 512 | 16 | 4352 |

M8/Q8_K/K1536 needs 14016 bytes and does not fit. A larger max-K tag alone
does not enlarge storage or make that shape legal.

## SRAM steering and timing contract

The two parity banks remain 146x128 logical bits each. Macro mapping remains
one 76x256 macro per bank, with two logical rows in each physical word. There
are 4672 addressable payload bytes and 4864 physical macro bytes.

Legacy mode steers four 32-bit words per beat. Extended mode steers eight
16-bit words because compact Q8_0 blocks start every 34 bytes. A valid beat may
cross one 128-bit row boundary; the two adjacent rows have opposite parity,
so both can be accessed in one cycle. No second read port is introduced.
Constant 34/292 multipliers and layout shifts form the K-block base address;
the address path does not multiply by an arbitrary run-time block size.

Fill bytes are compacted at the low end of the incoming beat by the reader.
Offsets are two-byte aligned in extended mode and every pair of byte strobes
is either 00 or 11. Valid bytes cannot extend beyond the selected K slab.
Replay emits 16-byte beats with an exact final strobe and slab-relative offset.
It holds data and metadata under backpressure. The byte offset is widened to
12 bits for the 2336-byte M8/Q8_K slab; M is widened to four bits to represent
eight without truncation. Default-mode ports retain their original widths.

Only a complete fill may commit. Lookup still compares context ID, generation,
profile, layout, actual M and K count. Beginning a replacement fill invalidates
the old context; abort cannot resurrect it. Reset cancels fill/replay and
invalidates metadata without requiring SRAM clearing. Fill and replay are
mutually exclusive. These are internal primitive contracts, not validation of
untrusted descriptors: the future engine admission must enforce the same budget
before any read request or side effect.

## Gates before runtime enablement

1. Legacy and extended byte-scoreboard tests with generic SRAM and the functional
   macro model; include full capacity, misaligned block starts, backpressure,
   all accepted M/layouts, metadata mismatch, release, abort and live reset.
2. Generated capability/ABI extension with backward-compatible capability
   parsing; exact byte-budget admission in RTL, reference and software.
3. FILL/REUSE/RELEASE integration for multirow layouts, including per-M-tile
   identity and no reuse across different input rows. Preserve DIRECT and the
   existing alias/version barriers.
4. Real-model equal-output VCS pairs including preparation, all output tiles,
   traffic, flags and fault recovery; ordinary RVV and legacy context regression.

No area, frequency, command speedup or model-level gain is implied by the
primitive tests. Macro models here check functional byte enables/addressing,
not vendor timing or physical implementation.

## Storage-stage evidence (2026-10-23)

All four VCS targets completed with exit zero, normal PASS markers and no
Error/Fatal diagnostics. The RTL and both testbench hashes were unchanged
through the runs. The independent reviewer implemented the extended scoreboard
and reviewed the RTL before execution; no RTL adjustment was needed after the
first tests. Raw runs are under
`verification/out/qbs-tile-context-20261023-01/`; the small archived manifest is
`verification/qbs/results/tile-context-20261023.json`.

| Run | Result | Checked replays | Checked payload bytes |
| --- | --- | ---: | ---: |
| Legacy, generic SRAM | PASS, existing full-depth suite | Existing suite | Existing suite |
| Legacy, macro model | PASS, existing full-depth suite | Existing suite | Existing suite |
| Extended, generic SRAM | PASS, 198 cases | 2922 | 1068672 |
| Extended, macro model | PASS, same 198 cases | 2922 | 1068672 |

These are 198 distinct extended cases repeated against two memory models, not
396 distinct shapes. Each run covers all twelve accepted profile/layout/M
tuples, K=1 and the tuple's capacity/maxK boundary, and initial beat lengths
2/4/6/8/10/12/14/16. Additional cases cover the three example shapes and refill
after abort/reset. There are 50 full-capacity cases, 17 maxK cases, and 3528
accepted beats with offset at least 2048 in each run. Sparse halfword updates
check that disabled byte enables preserve neighboring data. Scoreboarding uses
logical K/byte coordinates, not the DUT address helper.

Both models observe 50369 backpressured cycles, including 4481 last-beat stalls;
data, strobe, offset and last remain stable until acceptance. Reset is tested
during an incomplete fill and during a stalled replay. Abort is tested both
before and after all blocks arrive, before commit. Metadata mismatch and
replacement of a still-valid context are checked separately from release.

The extended simulation consumes about 1.8 seconds of VCS CPU per memory model;
this is simulator cost, not application latency. Gate 1 above is complete for
the admitted primitive inputs. Invalid descriptors, arithmetic, command faults,
real-model performance and gates 2 through 4 remain open.
