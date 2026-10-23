# Capacity-bounded multirow activation context

## Purpose and integration boundary

This is capacity-bounded cross-N activation reuse, not a completed matrix
optimization. The candidate engine explicitly enables
`qbs_activation_context.ExtendedShapes`; its standalone default remains the
legacy storage mode for compatibility tests. Capability words, descriptor
validation, reference model and runtime share the byte budget below. Software
must query capability, not infer support from the module parameter. Changes
remain in the verification worktree; main and FPGA are not changed here.

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
untrusted descriptors: engine admission checks the same budget after descriptor
fetch and before any payload request or compute side effect.

## Capability and command ownership

The instruction encodings, descriptor v2 and numerical contract do not change.
Capability word 2 expands the supported profiles, layouts and maximum M/K tags.
Word 3 explicitly returns 4672 in bits 31:0, storage-contract version 1 in bits
39:32, and zero in the upper bits. Byte capacity and the tag limit are both
necessary: M8/Q8_K permits only two blocks; M8/Q8_0 permits 17; M1/Q8_0 is
tag-limited to 32 even though more bytes would fit.

New runtime code accepts the exact old word-2 contract when word 3 is zero.
It does not admit new shapes on old RTL/QEMU. An old runtime that strictly
checks word 2 may reject the new device and fall back; binary compatibility
does not imply that an old runtime automatically uses the new capability.

The OPERATION scope fills and releases separately for each input tile. Identical
M/K metadata is insufficient to reuse data from different token rows. KEEP
scopes spanning operators require exactly one input tile and explicit external
ownership/generation, preserving the existing alias barriers. All commands are
checked before the first submission; split-K, gather, row-major M2/M3 and any
over-budget or singleton-N tile make the complete plan ineligible. Failure
does not imply RELEASE happened: recovery must not blindly retry REUSE.

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

## Integration fault audit: interrupted replay

The first command-level fault audit reproduced an incomplete replay on the
pre-repair integration RTL. After FILL, a REUSE command starts local activation
replay and weight reads concurrently. A weight MMU fault was reported while
the replay offset was 48 and its final beat had not arrived. Compute disabled
activation acceptance, and the engine left RUN for its fault-drain state.
Replay ready was restricted to RUN, so the context retained `replay_busy=1`
even after the fault was acknowledged. This occurred for M1 already; extending
M is not the underlying cause. The archived sources and VCS failure are in
`verification/out/qbs-tile-integration-20261023-04-repro/`.

The repair adds an explicit replay cancellation input, driven in the engine's
compute-fault-drain state. Cancellation stops SRAM replay requests and discards
the unconsumed response and transient beat state. It does not write SRAM,
invalidate a committed context, emit replay completion, or perform RELEASE.
Compute still drains its own in-flight work before reporting the terminal
fault, and a terminal assertion checks that no replay remains. A later REUSE
begins at byte zero. A failed replacement FILL retains its existing invalidation
semantics; cancellation does not restore the replaced context.

This preserves the normal-path schedule and memory capacity. It is not an
asynchronous command extension or a relaxation of fault atomicity. The tests
inject MMU, PMA and AXI weight faults for both REUSE and RELEASE, check that no
VRF writes escape, and retry against the original independent numerical
reference after poisoning the original activation memory. Primitive tests
cancel a stalled first or last beat and then verify every byte on replay,
with both generic and functional macro SRAM models.

The integration runner is `verification/qbs/run_tile_context_engine.py`. It
uses independent simulator working directories, checks command geometry against
the supplied vectors, requires every fault/retry marker, and pins source,
image, dynamic-library and input hashes for the run. Hash stability alone does
not prove build provenance: retain the fresh compile log and source snapshot
alongside the acceptance output. Failed runs are not included as passing data.

## Integration acceptance (2026-10-23)

The fresh VCS build and runner in
`verification/out/qbs-tile-integration-20261023-05/` completed successfully.
The checked summary, source identities and log hashes are archived in
`verification/qbs/results/tile-context-integration-20261023.json`. No source,
image, input or dynamic-library drift was detected during engine acceptance.

- The 12 capacity/maxK boundary shapes passed arithmetic, flags, exact
  FILL/REUSE/RELEASE traffic, validation rejection and fault/retry checks.
  They cover M1/M4/M5/M6/M7/M8 with Q8_K and Q8_0 activations.
- The original 36 functional vectors and four atomic-fault classes passed.
- The real Q8_0 M4/N32/K896 input passed with zero and four idle R-response
  cycles. The gap is a controlled supply condition, not calibrated DDR timing.
- There were 90 successful weight-fault/retry checks: 72 across the capacity
  matrix, six in the original suite and six in each real-input run. These
  repeat three fault types and two access modes; they are not 90 independent
  root causes. Faulting commands performed no architectural VRF writes.
- Generic SRAM and the functional macro model each passed the same 198
  primitive cases, now including 396 replay cancellations and 3318 complete
  byte-checked replays (1464884 bytes). Legacy tests passed on both models.
- Host reference tests, generated ABI checks, runtime capability/preflight/
  lifetime checks, 56 format-conversion combinations, 1530 segmented shapes,
  1809 storage views and 160 planner traffic combinations passed.

All normal DIRECT, FILL and REUSE cycle values match the pre-repair integration
run exactly. The real command results are:

| Supply gap | DIRECT cycles | FILL cycles | REUSE cycles | Activation bytes avoided per REUSE |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 5662 | 5905 | 5653 | 3808 |
| 4 | 12825 | 12933 | 11673 | 3808 |

At gap zero, the 243-cycle initial FILL cost is significant relative to the
nine-cycle saving per repeated command. At gap four, REUSE takes about 8.98%
fewer cycles than DIRECT. Neither row includes activation preparation or proves
a full projection gain: these runs repeat the same output tile rather than
walking distinct N tiles. The next acceptance must use the complete output
region and amortize the first FILL explicitly.

This closes the admitted engine/storage/runtime unit gates, not native SoC or
GGML deployment. Remaining checks include a distinct-data DIRECT preservation
case, full-N real projection execution with preparation, a freshly built SoC
regression, and matching QEMU/GGML integration. Long-K striped residency and
partial-output lifetime remain separate design work. No FPGA, synthesis or
physical result is claimed for this stage.
