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

## Full-projection acceptance campaign

The next gate uses the real Qwen2.5-0.5B Q8_0 Prefill attention-Q capture,
K896/N896, with four input tokens per projection. The engine campaign takes
input rows 0..3 and 4..7 independently, not repetitions of one input row. Each
projection contains all 28 distinct N32 weight tiles and checks 3584 outputs.
The DIRECT control and FILL/26 REUSE/RELEASE sequence use identical arithmetic
and output regions. The engine test poisons external activation bytes before
each reuse and checks exact result bits, fflags, work counts and payload.

The generator's `--real-projection` mode advances output offsets through the
complete captured matrix. Its existing `--real` single-tile interface remains
unchanged. The checker verifies tile identities, common resident activations,
traffic conservation and exact lifecycle order, then reports performance
separately from functional PASS. A regression is retained as a valid negative
measurement, not discarded or marked as deployment approval.

Current engine campaign:

```sh
systemctl --user status qbs-context-projection-20261023-09.service
```

Evidence directory: `verification/out/qbs-context-projection-20261023-09/`.
Its `status.json` contains source/image/input hashes, per-case state and paired
cycle sums. Compilation succeeded; the deliberate unknown-counter injection
was rejected by VCS as required before normal tests were dispatched. Earlier
06/07/08 directories are compile/checker-development or interrupted runs, not
accepted projection results. The successor includes the synchronous AR-monitor
clear boundary and complete unknown-counter checks. No RTL changed in this
test-infrastructure stage.

Two native applications close the preparation-cost gap:

| Application | Command sequence | Runtime-timed work |
| --- | --- | --- |
| `llama_qwen25_q8_0_prefill_m4_direct_qbs` | 28 DIRECT | quantization, M4 packing, descriptors, command/fence overhead and result stores |
| `llama_qwen25_q8_0_prefill_m4_context_qbs` | FILL, 26 REUSE, RELEASE | the same work, including the first FILL and final RELEASE |

Both use the same shared benchmark helper and compact M4 interleaved layout.
Existing benchmark defaults are unchanged. Capability preflight verifies the
new byte budget and compares command geometry with the public runtime planner;
the application's explicit access/generation sequence is checked separately.
Preflight and validation are outside the timed region. Weight repacking is
offline for both paths and is not counted as activation preparation.

The offline generator also produces an independent scalar FP64 dot oracle
from original row-major weights and independently quantized activations. Its
maximum difference from this capture is 4.76837e-7. At execution, the apps must
check every quantized byte, every finite output against this oracle, and every
output against captured golden values. These are pending runtime gates, not
claims that a generated expected-output file proves hardware correctness.

Rebuild only these two applications, with GNU and private build artifacts:

```sh
python3 apps/llama_qwen25_q8_0_prefill_m4_direct_qbs/script/build_pair.py \
  --l2-mb 16 --build-name NEW_BUILD_NAME
```

The sealed `build-gnu-m4-pair-20261023-02` ELFs use 935034/935186 allocated
bytes and a 16 MiB simulation-only link bound. The SoC image must independently
use the same memory size; the runner checks `simulator.conf`. ELF hashes:

- DIRECT: `93a2f4fbe8f8d8c2351b7eb41e78f22e737cc43ba5387d14b77164442f82881d`.
- Context: `ab8891f1477705d88cfef4d28c4e95847d71c7e74649f55c2e1543f5d6fb0f9b`.

SoC VCS worker: `qbs-context-projection-soc-20261023-01.service`.
Output: `verification/out/qbs-context-projection-soc-20261023-01/`.
It builds a fresh source-manifest-gated image, freezes both ELFs, and runs the
DIRECT and context applications with the existing independent UVM interface
checks plus strict application oracle/geometry/timing checks. The fresh build
has completed and the DIRECT application is executing. No completed SoC result
or preparation-inclusive speedup is claimed.
Do not edit sealed helpers, RTL or inputs until their workers terminate.

Both input groups (capture rows 0..3 and 4..7) have completed both engine runs.
Each independently produces the following totals:

| Response gap | DIRECT command cycles | Context command cycles | Cycle reduction | DIRECT/context payload B |
| --- | ---: | ---: | ---: | ---: |
| 0 | 158536 | 158536 | 0.00% | 960064 / 857248 |
| 4 | 359100 | 328104 | 8.63% | 960064 / 857248 |

These totals cover all 28 tiles, including FILL and RELEASE. The 102816 B
reduction is 27 avoided 3808 B activation reads; descriptors are included in
the engine payload totals. At gap0 the first FILL costs 243 extra cycles,
exactly offset by 27 reuses saving nine cycles each. Thus zero total speedup
is an observed result, not rounding of a positive gain. Gap4 is a controlled
response stall, not measured DDR behavior. All four groups and their source,
image and input hashes were independently rechecked after the worker finished.
This covers 224 command executions (112 DIRECT and 112 context commands),
with 7168 distinct captured scalar outputs tested under both supply conditions
and execution modes. Native SoC execution is pending; deployment remains
unapproved. Checked log SHA256 values:

- gap0: `5f1605450e87b7fe3a8863d4d8eba51f0e3e846b572d079fa8b559d67d2ee193`.
- gap4: `4093408fb81cac4e8e5a29940bb27c500e17d9e9c1681552aec3c4feb50aba0b`.
- input rows 4..7, gap0: `c295a5f5b164c6f0449e4fc5e7bcc2d8ad322df9f5f7f8d552300d6562243787`.
- input rows 4..7, gap4: `f64de2d186873b4977191a1e87a7befe07edc350570bcf89f5fe86664e3468bf`.

Host validation at this checkpoint: seven context/projection checker tests,
eight SoC-runner tests, five isolation tests, and the earlier
`make -C verification/qbs check` pass. Long-K partial sums, production GGML
admission and new-capability QEMU/Spike integration remain separate gates.

This closes the admitted engine/storage/runtime unit gates, not native SoC or
GGML deployment. Remaining checks include full-N real projection execution
with preparation, a freshly built SoC
regression, and matching QEMU/GGML integration. Long-K striped residency and
partial-output lifetime remain separate design work. No FPGA, synthesis or
physical result is claimed for this stage.

## Distinct-input DIRECT isolation gate

`verification/qbs/run_context_isolation.py` creates a private successor of the
sealed engine bench instead of editing the source used by running campaigns.
It requires the original projection manifest to contain both vector hashes and
checks them before deriving any test. Its own five host tests include rejection
of changed or unsealed vectors; current hashes cannot replace historical pins.

The resident command uses capture input rows 0..3 and the intervening DIRECT
uses rows 4..7, with identical first-N32 weights and M4/K896 geometry. The two
inputs differ in 3733 activation bytes and all 128 expected output words.
DIRECT must produce the second input's outputs/flags and external read traffic
without filling, reusing or invalidating the saved context. The original
scoreboard is then restored, external activation bytes are poisoned, and the
existing REUSE, fault/retry and RELEASE checks must still produce the first
input's outputs. This closes a stronger condition than checking a valid bit or
inserting DIRECT with byte-identical inputs.

Worker: `qbs-context-isolation-20261023-01.service`.
Evidence: `verification/out/qbs-context-isolation-20261023-01/`.
The private VCS run passed and the worker exited with status zero. It also
passed all three next-block read fault classes, active reset recovery, six
REUSE/RELEASE weight-fault retries, and the final context lifecycle checks.
The log SHA256 is
`4d3f34c04e730b1ca04e7df748c6266a0ff87e4018603e6447e8d25c80cf5404`.
This establishes this real M4/Q8_0 isolation case, not all possible profile and
shape combinations. No RTL or source pinned by the projection workers changed.

## Long-K continuation design decision (not implemented)

The existing 4672-byte context cannot retain all multirow activations of long
FFN projections. The next candidate is a bounded panel of output tiles, with
one K stripe resident and independent FP32 checkpoints for each output tile.
A single retained M4/N32 accumulator is not sufficient for cross-N reuse: at
least two output tiles must consume the same resident activation stripe.

The proposed minimum panel is two M4/N32 tiles. Each tile needs 128 raw FP32
checkpoint words (512 B); two tiles need 1024 B backing storage, in addition
to the existing 512 B working accumulator. This is a storage requirement, not
a macro/area result. Full M4/N896 checkpoints would need 14336 B, so full-N
residency is not the default proposal. Metadata, validity, ownership and flags
are additional to these payload capacities.

The maximum full M4 stripe in the current context is four Q8_K blocks
(1024 elements, 4672 B) or 32 Q8_0 blocks (1024 elements, 4352 B). A shorter
tail stripe uses its actual block count. Global R4 packing currently derives
row-group stride from command K; simply shrinking descriptor K misaddresses
subsequent row groups. Striped execution therefore needs matching segment-major
packing, or explicitly validated full-storage stride semantics.

### Numerical and fault contract

Current `QBS_INIT` clears working accumulator validity and flags; the integer
engine marks local K=0 as the first block. A continuation must instead restore
raw FP32 values, retain accumulated flags, and initialize from zero only at
global K=0. Preserve the existing scale multiplication and ordered FMADD
updates, including the second affine correction. Drain both integer and FP
pipelines before taking a checkpoint, not merely `integer_done`.

Software split-K is not an exact substitute: it computes each stripe from zero
and adds stripe totals afterward. For example, sequential FP32 contributions
`2^25, -2^25, 1` yield 1, whereas grouping the last two before adding the first
can yield 0. Current `qbs_runtime.c` explicitly uses `*element += value` for
split-K. A raw-bit checkpoint continuation must not introduce that extra sum.

Use a separate BEGIN/UPDATE/FINALIZE lifecycle for partial outputs; activation
FILL/REUSE/RELEASE alone cannot represent it. Record owner/generation, output
tile identity, geometry/profile/layout, expected next global K and flags.
Reject reordered, duplicated or mismatched updates before side effects.

During a stripe, the last successful checkpoint remains unchanged while the
working accumulator advances. A fault discards working state, drains outstanding
transactions and retains the checkpoint/K cursor for retry. Publish a new
checkpoint only after all data and arithmetic complete; no partially copied
checkpoint may become visible. Reset invalidates the entire hidden lifecycle.
DIRECT can use working storage but must not replace checkpoints. Only FINALIZE
publishes that tile's architectural result and accumulated flags. This promises
per-tile atomicity, not all-or-nothing commit of an entire projection. OS/context
ownership and the new intermediate-completion ABI must be specified before
this becomes a production command path.

### Cost gate before RTL extension

For a two-tile N64 panel, ideal external activation reads fall from twice to
once per K stripe; weights and arithmetic do not decrease. With S stripes,
checkpoint payload transfers are `2 tiles * (S-1) * 512 B * 2` for saves and
restores, excluding metadata. These are local transfers, not external AXI
payload, and must be timed independently. Stripe boundaries also increase
command count from two to `2*S`. Additional overlap may hide some costs, but
the fixed 32-product arithmetic floor is unchanged.

The implementation gate is a real long-K, equal-output projection comparison
including preparation, local checkpoint traffic, command costs and numerical
order. If these costs erase the avoided activation transfers, do not deploy
the panel merely because a reuse counter improves. Expansion to more tiles
requires a new capacity/benefit evaluation; this decision does not claim the
long-K requirement has been completed.
