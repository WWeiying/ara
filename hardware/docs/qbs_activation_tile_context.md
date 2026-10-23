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

The corrected `build-gnu-m4-pair-20261023-03` ELFs use 935014/935166 allocated
bytes and a 16 MiB simulation-only link bound. The SoC image must independently
use the same memory size; the runner checks `simulator.conf`. ELF hashes:

- DIRECT: `ebc3363158f73c181bd5644c74b25a23cc28a3e6548747fd972927b6c53471da`.
- Context: `bffc27137a9ff6ca952247f10b44a0130d350dedc488d7c4ca035abf4a3bd62f`.

SoC VCS worker: `qbs-context-projection-soc-20261023-02.service`.
Output: `verification/out/qbs-context-projection-soc-20261023-02/`.
It reuses the fresh source-manifest-gated image from worker 01, freezes both
corrected ELFs, and applies the existing independent UVM interface checks plus
strict application oracle/geometry/timing checks. Its scalar retirement trace
has reached the QBS command at `0x8000044a` and subsequent result stores. This
proves progress beyond initialization, not completion or a performance gain.
No completed SoC result or preparation-inclusive speedup is claimed.
Do not edit sealed helpers, RTL or inputs until their workers terminate.

### Native build failure and bounded repair

Worker 01 was stopped after its retirement trace proved a software build
failure, not a hardware stall. In its `build-gnu-m4-pair-20261023-02` ELF,
GNU loop recognition compiled the byte loop in bare-metal `memset` into a
call to `memset` itself. PC `0x80001954` called entry `0x80001934` repeatedly,
decrementing the stack by 16 bytes each iteration before reaching measured QBS
work. Keep that run as invalid software evidence; do not count it as an RTL
timeout or as a slow DIRECT baseline.

The private paired builder now compiles only `apps/common/string.c` with
`-ffreestanding -fno-builtin -fno-tree-loop-distribute-patterns`. It disassembles
that object before linking and rejects direct self-call relocations in
`memcpy` or `memset`. This guard is specific to the observed compiler failure,
not a proof of arbitrary libc control-flow correctness. All non-libc objects
in builds 02 and 03 are byte-identical. Neither the QBS algorithm, floating
point options nor RTL changed. Three host tests cover safe bodies, recursive
CALL/CALL_PLT/JAL relocations, and missing disassembly bodies.

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
and execution modes. Native SoC results are recorded below; default deployment
is not justified by the low-wait performance result. Checked log SHA256 values:

- gap0: `5f1605450e87b7fe3a8863d4d8eba51f0e3e846b572d079fa8b559d67d2ee193`.
- gap4: `4093408fb81cac4e8e5a29940bb27c500e17d9e9c1681552aec3c4feb50aba0b`.
- input rows 4..7, gap0: `c295a5f5b164c6f0449e4fc5e7bcc2d8ad322df9f5f7f8d552300d6562243787`.
- input rows 4..7, gap4: `f64de2d186873b4977191a1e87a7befe07edc350570bcf89f5fe86664e3468bf`.

Host validation at this checkpoint: seven context/projection checker tests,
eight SoC-runner tests, five isolation tests, and the earlier
`make -C verification/qbs check` pass. Long-K partial sums, production GGML
admission and new-capability Spike integration were separate gates. The
new-capability QEMU instruction contract and GGML native-QEMU integration have
since passed as described below; new-capability Spike integration remains open.

This closes the admitted engine/storage/runtime unit gates. Full-N native SoC
execution with preparation and matching QEMU/GGML integration have also
completed as recorded below. Long-K striped residency and
partial-output lifetime remain separate design work. No FPGA, synthesis or
physical result is claimed for this stage.

### Full-projection native SoC result

The corrected bare-metal pair uses the same VCS image, 16 MiB simulation L2,
M4/N896/K896 geometry and real capture input. Both executions check all 3584
outputs against the independent offline FP64 oracle and compare every
quantized input byte. Both pass, with identical output checksum
`0xa6e8082b37dbf573`.

| Application interval | DIRECT cycles | Context cycles |
|---|---:|---:|
| Quantization | 26056 | 26056 |
| Activation packing | 62462 | 62496 |
| Matmul including command setup | 168457 | 168632 |
| Total | 256975 | 257184 |
| Logical input reads, bytes | 974400 | 871584 |

Context saves 102816 logical bytes but increases total time by 209 cycles
(0.0813%). It is not a measured speedup in this low-wait SoC configuration.
Packing alone takes about 24.3% of DIRECT total time; it uses the shared
runtime's scalar byte-interleaving helper. This makes packing an independently
measured preparation target, rather than a reason to enlarge context storage.
The standalone M4 benchmark separates row quantization and packing; GGML's
M4 path instead invokes its four-row quantize-and-pack helper. Its wide-M path
does call the shared runtime packer after row quantization. Therefore the
24.3% is not a measured GGML M4 packing fraction: both production paths must
be evaluated before attributing a model-level preparation speedup.

The logical-read field includes 14336 bytes of FP32 quantization input,
448 descriptor bytes, 852992 weight bytes, and either 106624 or 3808
activation bytes. It excludes packing scratch reads and is not AXI bus traffic.
The initial host checker incorrectly omitted quantization input and descriptors;
its rejection is preserved in worker02's original status. Corrected checks
reject that old payload-only total, missing descriptors and missing input reads.
No simulator or application rerun was needed for the already passing DIRECT.

Evidence directories are `qbs-context-projection-soc-20261023-02` (DIRECT) and
`qbs-context-projection-soc-20261023-03` (context), under `verification/out/`.
The independent image/ELF/oracle re-audit is archived in
`verification/qbs/results/context-projection-soc-20261023.json`; reproduce it
using `verification/qbs/audit_projection_soc_pair.py` with a new output path.
The context worker finished normally, including its final source-manifest gate.

### GGML multirow native-QEMU integration

The independent sidecar `verification/qbs/ggml_tile_context/` builds the actual
external GGML sources with this worktree's runtime, without changing that
checkout. It executes 16 shapes, two changed-input epochs at the same allocation,
and six configurations: 192 checked MUL_MAT graphs. Every output is checked
against an independent scalar byte decoder and FP64 dot oracle; quantized bytes
are separately checked. Context-on/off pairs require exact output digests.

| Run | Context | Wide-M allowed | Threads | Graphs | Native commands | Context-eligible graphs |
|---:|---:|---:|---:|---:|---:|---:|
| 0 | 0 | 0 | 1 | 32 | 100 | 0 |
| 1 | 1 | 0 | 1 | 32 | 100 | 26 |
| 2 | 0 | 1 | 1 | 32 | 84 | 0 |
| 3 | 1 | 1 | 1 | 32 | 84 | 20 |
| 4 | 0 | 1 | 3 | 32 | 340 | 0 |
| 5 | 1 | 1 | 3 | 32 | 340 | 0 |

Each run checks 6216 outputs and 4354752 logical dot elements. No command uses
software QBS emulation. Width selection, output work, command sequence,
context FILL/REUSE/RELEASE, capacity fallback, input epochs and summary counts
are checked against the pinned runtime policy. The three-thread N37 schedule
partitions output into N4/N1 chunks, so it correctly uses DIRECT and does not
demonstrate concurrent resident-context reuse. All threads share one guest
hart; this does not validate migration or OS context save/restore.

The guest completed with exit zero. Initial host rejection was an EXEC trace
name mismatch (`Q4_K`/`Q8_0`, versus lowercase CALL/COMMAND names). The checker
now accepts only the two explicit production EXEC spellings; no dispatch,
lifecycle or numerical condition was relaxed. The original worker record is
preserved and the existing log re-audited without rerunning the guest. All
non-checker source/image pins remained unchanged. Evidence is
`verification/qbs/results/ggml-tile-context-20261023.json`; the corrected
checker passes 23 host tests, including real EXEC fixtures and mutations.

These results establish functional GGML integration, not a whole-model
speedup or RTL throughput measurement. The full-projection native result
above remains the performance decision for the low-wait configuration.

### Preparation optimization candidate

`verification/qbs/activation_pack_rvv_candidate.h` is an isolated experiment,
not the selected production packer. It changes only byte movement: vector
loads with strided byte stores for quantized elements, and aligned halfword
or unaligned byte operations for Q8_K block sums. It preserves scale bits,
quantized bytes, auxiliary sums, M8 padding, and short row-major tails. It
strip-mines by the actual returned VL instead of assuming VLEN=1024.

Host validation covers 33264 layouts/input patterns and 14 rejected argument
cases, including M4/M5..24, short and long K, odd strides, misalignment,
canaries and unchanged input buffers. Native QEMU checks passed at VLEN128 and
VLEN1024, plus VLEN1024 with an artificial AVL ceiling of seven to exercise
repeated tails: 99792 layout/input checks in total, with 14 invalid-argument
checks per configuration. Source, ELF and completed-log hashes were rechecked
by `functional_gate` before VCS dispatch. Evidence is
`verification/qbs/results/activation-pack-native-20261023.json`.

`build_pack_projection_candidate.py` reuses all ten frozen object files of
the passing real M4/N896/K896 DIRECT application. It adds only a private
link-time wrapper around `qbs_pack_activation_m4`; baseline files, production
runtime and RTL remain unchanged. The ELF is not a different or smaller
workload. GNU disassembly checks the wrapper and strided vector stores.
The next performance gate uses the same manifest-gated VCS image and requires
the existing independent oracle, checksum and logical-read accounting.

Strided stores may issue many small VLSU transactions, so fewer scalar
instructions alone do not establish a speedup. Do not enable this candidate
globally without native cycle evidence and production-path validation. GGML
M4's fused quantization also has its own rounding/tie semantics; replacing it
with row quantization plus packing requires separate numerical checks.

In the audited GGML sources, Q8_0 M4 uses `roundf` (halfway away from zero),
whereas the RVV row quantizer uses a conversion affected by `frm` (normally
RNE). A block with maximum 127 and an element 0.5 therefore produces 1 versus
0. Q8_K M4 retains the first signed maximum-absolute input; the row RVV
implementation selects the negative extremum when positive/negative magnitudes
tie. A first +127 followed by -127 yields opposite scale and quant signs.
These are production software differences, not proven RTL bugs. Current
192-graph inputs avoid these ties, so that gate cannot certify substituting
one quantizer for the other. Any future fused preparation optimization must
test these boundaries against the selected production M4 contract, preserve
its scale arithmetic order, and retain an explicit fallback.

The private full-projection timing worker is launched by
`run_pack_projection.py`. It waits for all three native packing configurations
to pass, rechecks source/ELF/log hashes, then invokes the existing SoC runner.
Five host tests reject incomplete suites, input drift, ELF drift and a forged
PASS with a failure marker. The worker is owned directly by systemd; it does
not rebuild RTL or modify the archived DIRECT baseline.

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

## New-capability QEMU acceptance

The private QEMU 10.2.0 build in
`verification/out/qemu-context-20261023-01/` uses this worktree's current ABI
and reference model. Its build attestation hashes the executable, model sources,
configuration and successful build log. The original shared QEMU installation
is unchanged. `verification/qbs/results/tile-context-qemu-20261023.json` records
the test/source/executable identities and observed zero exit status.

The extended bare-metal instruction test passes all previous checks plus 155
commands covering seven shapes. Q8_0 covers M4 with 1/28/32 K blocks, M5 with
1/17 blocks, and M8 with 17 blocks. Q8_K covers M4 with four blocks, exactly
the 4672-byte payload limit. N tails, padded M5 source rows and inactive
destination registers are checked. Expected outputs are closed-form integers
converted exactly to FP32, independent of the QBS execution reference; the
Q4_K weights exercise nonzero affine correction.

Every shape checks distinct-input `FILL(A), DIRECT(B), REUSE(A)`, stale token
and metadata rejection, capacity rejection without loss of the old context,
REUSE/RELEASE weight access faults with unchanged destinations/flags, successful
retry, release invalidation and refill. Capability words are additionally
checked against literal expected bits, including reserved bits. M2/M3
row-major resident contexts must reject rather than silently change layout.

This is instruction-model functional evidence. It does not establish native
RTL performance, GGML admission, OS save/restore of resident state, or complete
model numerical accuracy. The separate native SoC projection and new-capability
GGML graph gates remain necessary.

## Production M4 preparation candidate (isolated numerical gate)

`verification/qbs/ggml_m4_prepare_candidate.h` experiments with Q8_0 four-row
preparation, not with the row quantizer or QBS RTL. It preserves the production
scalar maximum, scale and FP16 conversion, then uses VLA multiply, explicit
RMM integer conversion and interleaved byte stores. Non-RNE callers and guarded
exceptional/tiny inputs delegate to the actual compiled GGML generic function.
The pinned toolchain's `roundf` preserves exception flags for its conversion;
the candidate therefore restores conversion flags without discarding flags
from multiplication or scale computation. This contract must be revalidated
for a different compiler/libm, not inferred from byte agreement alone.

`run_ggml_m4_prepare_candidate.py` reuses the completed private GGML static
libraries. It verifies their original source manifest, pins headers, libraries,
compiler, guest ELF and model activation bytes, and runs one ELF at VLEN128
and VLEN1024. Each run checks 3375 boundary configurations (585 vector-path,
2790 fallback), plus 45 configurations of the real M4/K896 Qwen activation.
Checks include all output bytes, guards, unchanged inputs, five rounding modes,
sticky flags, `vcsr`, and forced strip-mining limits 1/7/32. The oracle is the
production `ggml_quantize_mat_q8_0_4x1_generic`, not the different row quantizer.

The first worker stopped at compilation because unused static functions in
external GGML headers were promoted to errors. The successor uses system
include paths for those headers, matching the existing sidecar convention;
candidate warnings remain errors. Native results and RTL performance must be
recorded separately. The conservative scalar preflight still reads the input
before quantization, so neither successful compilation nor functional agreement
establishes a speedup. No production dispatch selects this candidate yet.

The successor completed both VLENs successfully: 6750 boundary configurations
and 90 real-capture configurations (6840 total), with exact output bytes and
FP environment agreement. Both guests exited zero and all source/library/ELF
pins remained unchanged. Evidence is
`verification/qbs/results/ggml-m4-prepare-native-20261023.json`. This clears
the numerical gate for Q8_0 M4; Q8_K, production selection and paired native
RTL timing remain open.

## Byte-packing full-projection RTL result

The separate row-quantize/pack candidate completed on the unchanged SoC image.
`audit_pack_projection.py` rechecks the original simulator, frozen ELF/object
identities, protocol result, independent numerical oracle and matching work.

| Interval | Scalar packing | VLA packing |
| --- | ---: | ---: |
| Quantization | 26056 | 26063 |
| Packing | 62462 | 16409 |
| Matmul and command setup | 168457 | 168451 |
| Complete projection | 256975 | 210923 |

Both runs produce checksum `0xa6e8082b37dbf573`, zero oracle mismatches and zero
quantized-byte mismatches for all 3584 outputs of the real M4/N896/K896 input.
All ten original objects are reused; the candidate adds only a private packer
wrapper. Total cycles fall 17.9208% (1.21834x speedup); packing itself improves
3.80657x. The few-cycle changes in other intervals do not support an arithmetic
throughput claim. Logical input reads remain 974400 bytes under the existing
definition, which excludes scratch packing traffic.

Evidence: `verification/qbs/results/pack-projection-soc-20261023.json`. This is
not a fused-GGML-M4 or whole-model speedup. It validates improving the separate
packing path; production wide-M selection and other shapes still require their
own integration/performance gates. The fused-M4 candidate above follows a
different baseline and must not inherit this speedup.

### Fused-M4 RTL timing gate

`export_m4_prepare_oracle.py` exports 3808 packed bytes from the actual Linux
GGML generic object using the same real activation capture. Its successful
export records `fcsr=1`, `vcsr=5`, and SHA256
`2802b758f22508c566d1a69f450eb7bc19daac55b94f90062f6a77069dacdd28`.
The full source/tool/library/log evidence is in
`verification/out/qbs-m4-oracle-20261023-01/golden.json`.

`build_m4_prepare_soc.py` extracts the exact production Q8_0 M4 function body
from pinned `repack.cpp` rather than transcribing it. A private bare-metal
build links that oracle, the same candidate header and the captured inputs;
it does not rebuild GGML or RTL. It uses rv64gcv, without optional half-precision
instructions, to match the Linux oracle's conversion choice. The final ELF
binds newlib `roundf`; its finite-input implementation uses integer bit handling
without adding flags. Independent Linux bytes and FP state are checked again
on RTL, rather than assuming the two toolchains are interchangeable.

`run_m4_prepare_soc.py` runs four calls in generic/vector/vector/generic order.
Every call resets the same FP environment and checks all bytes against the
independently exported golden, with exact FP/vcsr agreement. Quantization,
preflight, interleaving and FP/write completion are inside timing; checking
and printing are outside. This is a preparation-only ABBA comparison, not a
whole-projection or model speedup. Worker `qbs-m4-prepare-soc-20261023-01`
has been dispatched on the existing SoC image; no result is claimed here.
