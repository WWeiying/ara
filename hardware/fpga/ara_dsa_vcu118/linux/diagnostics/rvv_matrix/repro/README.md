# RVV failure handoff and reduced test programs

This directory supplies twelve independent Linux RV64GCV tests for the
verification branch. Each ELF executes one target instruction, checks data
and relevant CSRs, and returns 0 (pass), 1 (mismatch), 2 (setup failure), or
77 (VLEN other than 1024). Every ELF passed QEMU VLEN1024 in
`rvv_repro_handoff01/reference_1024.json` on 2026-10-10.

**All twelve generic ELFs ran on the FPGA:** recovery 205 had eight
failures and a `large_slideup` pass; recovery 208 confirmed a no-retirement
stall in `mask_boundary`; recovery 209 passed `extension_overlap` and
`slidedown_zero_restart`. These three passing reductions do not reproduce the
original failures. A reduced candidate passing RTL simulation does
not invalidate a sequence-dependent original failure. Retain the original ELF
and its setup sequence when a standalone candidate does not reproduce.

## Build and execute

### Misaligned segment preparation traps

`audit_segment_setup.py` audits all nine original `rvv_segments_misaligned_*`
failures against their deployed ELF hashes and complete kernel trap records.
`rvv_segment_setup_audit01` confirms SIGBUS/cause4 at the first preparation
`vle16/32/64.v v24,(a6)`, with address misalignment of one byte. The preceding
`vsetvli` uses the nonzero capacity argument in a4; the later segment target's
VL argument in a3 is zero. Thus these records do not establish a zero-VL
segment-target exception: the program traps earlier in its unmasked staging
load. They also do not establish nine architectural RTL defects; the vector
specification permits address-misaligned exceptions for misaligned elements:
https://docs.riscv.org/reference/isa/unpriv/v-st-ext

The audit checks instruction decoding, prelude, registers, cause, address and
ELF identity; ambiguous/truncated records are rejected. It does not claim a
reduced-program board reproduction. Rebuilding the nine old programs with the
current generator in `rvv_segment_original_rebuild01` does not reproduce their
ELF hashes, so that build must not replace the immutable originals. A minimal
preparation-trap candidate still needs board execution and signature matching.
`reduce_segment_setup.py` now builds nine candidates in
`rvv_segment_setup_single01`, retaining each archived assembly's capacity
entry and complete first operation. Each calls that operation once with
misaligned input/output staging, target VL0 and preparation VL=capacity.
All18 reference executions pass at VLEN512/1024, and the candidates are
queued for board measurement. The small C wrapper is reconstructed; it is
not claimed to be the original C source. Audit02 additionally verifies that
the recorded trap belongs to the first operation, not a later similar one.
`audit_segment_single.py` rechecks original and candidate ELF/source hashes,
then compares trap opcode, preparation VL, target VL argument, signal/cause,
and alignment offset. It does not equate an exit status or absolute relocated
PC with equivalence. The real predeployment negative check in
`rvv_segment_setup_pending_audit01` reports0 confirmed/9 pending.

### Board comparison checkpoint (2026-10-10)

Recovery 203 executed all 243 single-stimulus floating-point candidates:
47 move candidates and 196 comparison candidates, all with exit status 1.
This is not by itself proof of equivalent failures.

Inventory reconciliation found41 additional failed comparison parents not
covered by that196-candidate batch:15 unmasked,15 unmasked destination-v8,
and11 unmasked destination-v16 shapes. `rvv_compare_uncovered01` supplies
their measured first-failure trials and raw result diagnostics. All82 reference
executions pass at VLEN512/1024. The three candidate manifests now cover all237
failed comparison parent identities exactly once, but the new41 are queued,
not board-confirmed. They retain archived assembly and fixture headers with
current reconstructed C; original source equivalence is not claimed.
`reduce_fp_compare.py --exclude-manifest` skips an existing candidate's parent
only after matching the original deployed ELF hash, and accepts frozen
supervisor reports without altering their measured outputs.

- 167 comparison candidates have the same measured trigger, expected flags,
  and actual flags as the original recovery-202 failure. `match_fp_compare.py`
  checks that explicit flag symptom; it does not certify vector data or an
  internal RTL cause.
- Detailed variants of the other 29 comparison candidates failed in recovery
  205 with explicit prestart-bit corruption. The originals lack raw output,
  so this does not establish exact original/reduced data equivalence.
- All 47 move candidates now have matching original/prefix/single-trial
  symptoms. Their 65-trial prefix variants ran in recovery 205; see
  `rvv_move_symptoms02/symptoms.json` for the three-way audit.
- The whole-register single-trial and 321-trial prefix variants both reproduced
  the original `op=16 mode=1 vstart=1 byte=33 expected=91 actual=40` symptom.
  `rvv_whole_symptoms01/symptoms.json` checks exact source and ELF hashes.
  This confirms that first symptom, not every whole-register failing variant.
- Nine generic candidates ran in recovery 205. Eight failed; `large_slideup`
  returned `RVV_REPRO_PASS errors=0` and exit 0. Its initial observer failure
  was a missing-`cases=` parser issue, not a hardware failure; see
  `rvv_generic_review01/review.json`. Mask-boundary subsequently stalled in
  recovery 208; extension-overlap and zero-offset slidedown both passed in
  recovery 209 and require further sequence-preserving reduction. These generic binaries
  have VLEN1024-only references, not dual-VLEN validation.
- Recovery 206 executed 38 mask first-failure prefix traces. All failed and
  captured the first wrong bit and its trigger. `reduce_masks.py` preserves
  their assembly/oracle and selects one measured configuration. All 38 in
  `rvv_small_masks02` passed QEMU VLEN512/1024. In recovery 208 all 38 failed
  with the same first-wrong-bit, trigger, returned-vstart, guard and error-count
  tuple as their prefix variants (`rvv_mask_symptoms02/symptoms.json`). Original
  uninstrumented source rebuilds were byte-identical to the original board
  ELFs. The original reports contain aggregate failures, not raw bit values;
  exact bit matching is between the detailed prefix and single-trial versions.
- `reduce_exceptions.py` selects one child trial for each of the five failing
  protected-page scenarios (0/1/2/3/5) at SEW8/16/32/64. All four original
  detail ELFs rebuilt byte-identically before reduction. All 20 candidates in
  `rvv_small_exceptions01` passed QEMU VLEN512/1024. Recovery 209 reproduced
  all 20 failures: scenario counters, unexpected child SIGSEGV, faulting ELF
  instruction, cause 13 and page-boundary offset match the originals. The
  audit is `rvv_exception_symptoms02/symptoms.json`. mmap/mprotect, mask setup, assembly and parent wait-status checks
  remain unchanged; only the round/scenario loop bounds change. These require
  a real translation/permission environment in RTL simulation.

Frozen evidence is under the campaign directory
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_reduced_symptoms04`.
The symptom audit checks parent/deployed ELF hashes and generated-source
hashes. It keeps 119 current-source reconstructions explicitly separate from
the 77 candidates with verified original oracle/generator hashes.
`rvv_retest_identity01` holds the original-image programming and Linux boot
records for both recoveries. Neither QEMU success nor matching board symptoms
should be promoted to internal cycle-level causality.

Recovery 203 initially executed zero cases because the launch command's
external `cut` process faulted in the Linux loader. That UART/report scene is
retained in `rvv_recovery08_203/preparation_failure01`. The resumed observer
uses shell parameter expansion for the hash string and still refuses execution
on a failed hash command or mismatching digest. This avoids the launch failure;
it is not a fix or root-cause explanation for the scalar instruction-page fault.

`reduce_fp_moves.py` additionally extracts one actually reported failing stimulus
per FP-move ELF. It verifies the original generator/oracle hashes, retains the
original assembly and scalar oracle, and removes the outer trial loops. Its
manifest links each candidate to the original ELF hash, board report hash and
exact failure-detail line. The generated `scenario.c`, `scenario.S` and
`scenario.dis` are retained per candidate. Removing preceding trials is an
explicit semantic change to the experiment; only a matching board failure
establishes successful reduction.

On 2026-10-10, `rvv_small_fp_moves01` supplied 47 such candidates, each with one
configuration, and all passed reference validation at VLEN512 and VLEN1024.
They subsequently failed in recovery 203; the original-prefix/single-trial
symptom comparison was confirmed after recovery 205, as recorded above.
Use `--report`, `--original-build`, `--cross` and `--out` to build this supplement;
the original build directory must contain the `op0` through `op7` manifests.

From the repository root:

```bash
python3 hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/repro/build.py \
  --cross /path/to/riscv64-buildroot-linux-gnu- \
  --out /path/to/new-reproducer-output
```

The output contains twelve static ELFs in `overlay/opt/ara-tests`, generated
assembly, disassembly, `manifest.json` and `overlay.cpio`. The compiler is
invoked with auto-vectorization disabled, so scalar checks do not exercise
additional vector operations. Linux syscalls implement printing, exit and
the two protected-page setups; no C library is linked.

Use the existing `../reference.py` with `--vlen 1024`, a QEMU virt Linux
kernel/initramfs and OpenSBI. The reference command does not access FPGA
hardware. It generates a transfer archive only after all checks pass.

On an already prepared Linux target, run one ELF at a time, for example:

```sh
/opt/ara-tests/rvv_repro_gather_restart
echo $?
```

`RVV_REPRO_BEGIN` is printed before vector setup. `RVV_REPRO_RETURNED` is
printed only after the target, CSR reads and result store return. Missing
RETURNED alone does not identify the stopped instruction. Generated assembly
exports `repro_target`, `repro_after_target`, `repro_after_vstart`; use these
symbols with a valid instruction-retirement trace. A stalled core may not
respond to a Linux timeout or signal. These tests do not reset the board.

For bare-metal RTL simulation, reuse the generated `run_case` wrapper with
the same initialized buffers. Arguments a0..a5 are source, second source,
output, predicate, VLENB, and a three-word CSR result buffer. The wrapper
clobbers caller-saved temporaries and vector state. The simulator must enable
VS/FS and provide address translation and protected pages for cases 8/9.
Inspect scalar expected-data initialization in `scenario.c` when porting.

## Short scenarios

All tests use tu/mu and VLEN=1024. Source/destination groups are disjoint
except the deliberately overlapping extension case. Every setup starts with
vstart=0; the intended restart value is written immediately before the target.

| ELF suffix | Trigger | Required result | Original board evidence |
|---|---|---|---|
| `whole_restart` | Load source at EEW8; SEW16/m1; vstart=1; `vmv1r.v v24,v8` | Preserve destination bytes 0/1; copy source bytes 2..127; clear vstart | RVV-03, additions07: byte 1 changed despite being prestart |
| `fpwide_m8` | e32/m8, VL1; source 1.0f, seed 2.0; `vfwredosum.vs` | Legal instruction; scalar FP64 result 3.0 | RVV-05: original instruction 0xcc881c57 traps with SIGILL |
| `mask_boundary` | e8/m4, VL512, vstart256, all-on; `vxor.vv` | Preserve elements 0..255, compute 256..511, complete | RVV-02: drained first failure at VL512/vstart256 |
| `gather_restart` | e16/m1, VL2, vstart1, all-on; `vrgather.vx`, index0 | Destination [91,1000]; tail preserved | RVV-19: prestart sentinel is overwritten |
| `slideup_restart` | Same shape, `vslide1up.vx`, scalar0 | Destination [91,1000]; tail preserved | Recovery199: element0 expected91, actual0 before later stall |
| `slidedown_restart` | Same shape, `vslide1down.vx`, scalar0 | Destination [91,0]; tail preserved | Recovery200: element0 expected91, actual538 before later stall |
| `fp_masked_nv` | e32/m1, VL4, all-off; sNaN0x7f800001; `vmfeq.vv` | fflags remains0; low4 destination bits preserved | RVV-09: masked-off sNaN contributes NV=16 |
| `protected_mask` | e8/m1, VL8, all-off; `vle8.v` at PROT_NONE page | No signal; destination unchanged | RVV-04: scenario3 gives16 unexpected signals per SEW |
| `fof_page` | e8/m1, VL8, all-on; `vle8ff.v` across page boundary after4 mapped bytes | No signal; VL4; first4 values loaded | RVV-04: scenario0 gives unexpected signals |
| `extension_overlap` | e16/m2, VL2; source v25 at EEW8, destination v24..v25; `vzext.vf2` | First2 destination values17/18; complete | RVV-06: legal high-end overlap partitions stall; ordinary ones pass |
| `large_slideup` | e8/m4, VL512, offset511, all-on; `vslideup.vx` | Only element511 changes from91 to17 | RVV-08: original all-on/sparse cases show reversed destination enable |
| `slidedown_zero_restart` | e16/m1, VL2, vstart1; `vslidedown.vi ...,0` | Destination [91,1001]; tail preserved | Recovery197: completion stall; no retained numerical detail |

The last printed mismatch identifies an earlier completed trial, not necessarily
the later stalled trial. Cases 3/10/11 and the slide cases may require the
original preceding sequence to reproduce the board stall or mask inversion.
Case10 checks the two active extension results only, not overlap-tail policy.
Case7 deliberately ignores mask-result tail bits, which may be agnostic.
Case9 ignores output beyond shortened VL, as permitted for fault-only-first.

Because the generic extension-overlap candidate passed in recovery 209,
`trace_extension.py` retains the original e16/m2/vf2 sequence and prints
seed/op/VL/mask/capacity before each target wrapper, plus a return marker.
The original uninstrumented source rebuilt byte-identically first.
`rvv_extension_trace01` passed QEMU VLEN512/1024 and is queued for board
testing. Printing/draining UART can affect timing and kernel context switches;
the instrumented trace must reproduce the stall before its last marker is
used to derive a single trial. No failing configuration is inferred merely
from the original target PC or from the generic VL=2 program passing.

## Source attribution

Attribution uses the deployed source archive, not today's working tree. The
collector checks source hashes against the archived manifest and includes the
relevant source files in the handoff bundle. Line numbers below refer to those
files. Snapshot cycles/PCs prove no retirement only when both samples have no
debug/watchdog halt; the head-PC probe has no validity bit.
The bundle also contains the complete `ISSUES.md` and `COVERAGE_GAPS.md` logs.

### 1. Widening FP reduction rejected: concrete decode path

Recovery 202's original ELF and recovery 205's generic reproducer both trap
on ELF instruction `0xcc881c57` (`vfwredosum.vs v24,v8,v16,v0.t`) with
cause 2 and matching instruction-valued tval. The original trap has `a3=0`
and its disassembly sets VL from a3; the generic case sets VL=1. Thus this
confirms the same illegal-instruction symptom, not identical input settings.
`rvv_fpwide_trap_symptoms01/symptoms.json` freezes both reports, verifies the
deployed ELF hashes, and maps each EPC to the instruction. An exact original
VL=0 single-configuration reduction (`reduce_fpwide.py`, release
`rvv_small_fpwide01`) passed QEMU VLEN512/1024 and failed in recovery 208.
Its unmodified original source/assembly rebuilt to the identical original
ELF before loop reduction. `rvv_fpwide_trap_symptoms02/symptoms.json` verifies
the original and reduced EPCs against their deployed ELFs: both fault on
`0xcc881c57` with cause 2 and VL=0. This confirms the same first-trial trap
symptom; it is not an internal waveform-level root-cause proof.

`ara_dispatcher.sv:3654,3672,3766`: VFWREDUSUM/VFWREDOSUM set
`ara_req.emul = next_lmul(csr_vtype_q.vlmul)`. At m8 this is LMUL_RSVD.
The FP destination check unconditionally sets illegal_insn for LMUL_RSVD,
although reduction seeds/results occupy one register. This matches the exact
board instruction and cause2 trap. Check the effective LMUL carried downstream
as well as decode legality; simply disabling the error is not a verified fix.

Capture: decoded op, vtype, ara_req.emul, lmul_vs1/lmul_vs2, illegal_insn,
request acceptance, exception valid/cause/tval. Acceptance: case2 completes
with3.0 and no NV; also exercise unordered reduction and m4 controls.

### 2. Whole-register restart uses source EEW: byte-level confirmation

`ara_dispatcher.sv:2417..2464` selects the source's stored EEW for internal
move width and length, while leaving architectural vstart unchanged. Loading
the source as bytes then selecting SEW16 makes internal byte offset1 instead
of architectural byte offset2. Original board details show precisely this
one-byte restart position, including the output guard offset.

Capture architectural SEW/vstart, stored source EEW, dispatched width/vstart,
and destination write byte enables. Check SEW16/32/64 and vmv1r/2r/4r/8r;
preserve the correct byte prefix when normalizing source layout.

### 3. Mask producer/consumer disagreement: static contract plus board boundary

Recovery 208's `rvv_repro_mask_boundary` also has a confirmed live no-retirement
stall: cycles increased by 529716351 while retired/trap counts and PCs were
unchanged. last_pc=0x103b0 maps to its target `vxor.vv`; head_pc=0x103b4 maps
to the following vstart read. The head-PC probe has no validity bit, and this
does not prove which internal handshake is blocked. The initial 30-second
observer expiry had no snapshots because its diagnostic threshold was 120
seconds. A separate read-only review captured the two snapshots and no UART
bytes, without reset or serial writes. Both reports are preserved under
`rvv_recovery08_208/terminal_scene` and `short_expiry_diagnosis01`.
The observer now diagnoses short cases at their existing expiry deadline;
progressing cases remain incomplete rather than being declared stalled.

`lane_sequencer.sv:1212..1220` trims MaskM to packed words beginning at
`vstart/(NrLanes*ELEN)`. At four lanes, ELEN64, VL512/vstart256 this supplies
one word at offset1. `masku.sv:1760..1778,1884..1891` keeps read/commit counts
at512 and pointer0 for VFU_Alu, VFU_MFpu and VFU_MaskUnit. The consumers can
therefore require two words while only one is supplied. The original drained
board trace stops at this exact boundary. Internal FIFO contents were not
captured on the board, so verify this causal path in simulation.

Capture MaskM request vl/vstart/push, requester valid/ready/pop, MASKU
read_cnt/commit_cnt/mask_pnt, per-lane mask ready, instruction done and running
IDs. Start with case3, then vstart255/256/257 and VL511/512, and compare m4/m8.
Do not classify every small-VL slide stall as this same word-boundary problem.

### 4. Gather prestart write: explicit missing write suppression

`masku.sv:1754..1763,1876` initializes output/index state at zero;
`masku.sv:940..961` builds gather byte enables only from vm/predicate, without
an element>=vstart test. The generic mask-result preservation path applies to
mask destinations; gather writes ordinary vector elements. At VL2/vstart1,
the first result word can therefore enable element0. This matches the board's
prestart corruption. It does not by itself establish the later completion stall.

Capture vrgat_cnt, output/index FIFO positions, out_valid_cnt, be_vrgat_seq,
result-queue address/BE/data and final lane write grants. Case4 must preserve
element0 even with an all-on predicate. Include vv/vi and ei16 variants later.

### 5. Slide prestart write: normal operations miss the prefix guard

Archived `sldu.sv:624..658` starts normal slidedown output at zero.
At717..740 the prefix-byte guard is conditional on an internal
`partial_reshuffle` operation (`scale_vl`, zero stride), rather than every
architectural slide. Scalar insertion at804..829 uses vm/predicate without
vstart. These are concrete source-level candidates for the observed prestart
changes in recovery199/200; downstream acceptance and exact running sequence
still need a cycle trace to attribute the completion stall.

Capture dispatched scale_vl/stride/vstart, out_pnt/vrf_pnt, out_en_seq,
partial_reshuffle, scalar insertion state, result BE and mask consumption.
Cases5/6/12 independently test the data symptom; compare vstart0/1/2.

### 6. Masked memory translation: mask check exists only for indexed operations

`addrgen.sv:362..405` creates unit/strided requests regardless of predicate.
At917..940 only ADDRGEN_IDX_OP can take the masked-element skip path;
at1135..1139 other operations request translation without checking mask.
At1213..1244 MMU faults are forwarded without an inactive-element check.
This supplies a concrete path explaining all-off protected-page faults.
It does not explain all FOF shortening or segment replay errors.

Capture request op/vm, mask ownership/first-element/valid/bits, generated
element address, mmu_req/valid/exception, fault index/vstart and skip tokens.
In case8 an all-off protected address must not generate an architectural page
fault. Case9 separately checks active first-page load and nontrapping later
FOF fault; do not merge its root cause with case8 without evidence.

### Remaining causes requiring discriminating traces

Gather restart reduction: `reduce_gather.py` uses the83 original numerical
failures recorded in recovery202 (80 operation partitions and three full
fractional-LMUL matrices). It checks each original ELF by byte-identical
rebuild, retains the original PRNG/index/mask/load/oracle code, and selects
seed0/scalar0/VL2/mask0/vstart1 with the measured gather operation. Release
`rvv_small_gather02` contains83 candidates, not83 independent bugs or proven
board reproductions. `audit_slide.py` also accepts this release layout;
`match_slide.py` requires matching vstart when the original reports it.
The earlier generic gather case cannot replace these per-ELF comparisons.

Recovery215 partial checkpoint: `rvv_gather_symptoms02` verified37 matching
single-call failures, with46 still pending at that sample. For example,
e16/mf4 op0, VL2/vstart1 corrupts prestart element0 from expected91 to61881,
exactly matching the original. This is partial evidence, not83 completed
reproductions; later immutable audit snapshots supersede these counts.
The completed recovery215 checkpoint `rvv_gather_symptoms04` now confirms
all83 single-call failures with the original trigger/vstart/element/value.
Both reference VLENs passed all83 exact ELFs. This covers the83 selected
originals, not all remaining RVV fault families or independent RTL causes.

Fault-replay diagnostic preparation: `trace_fault.py` adds read-only
signal-context fields and per-trial error counters, leaving recovery/checks
unchanged. Its initial `rvv_fault_trace01` build was rejected because current
source did not reconstruct the archived e8/mf8 ELF byte-identically. It has
not been released or board tested. Do not use its draft source as a proven
original reproducer until the source/ELF lineage discrepancy is resolved.
`--compare-current-oracle` creates a separate three-way diagnostic package:
the immutable archived original ELF, current uninstrumented oracle, and
instrumented oracle. It explicitly records source equivalence as unproven,
and does not override the default byte-identity requirement. All three in
`rvv_fault_controls01` pass both QEMU VLENs; board results remain pending.
Agreement of aggregate counts alone must not be called exact trial-level
equivalence or proof of an RTL cause.

Large-offset slide reduction: `reduce_slide.py` reconstructs the legacy
nonrestart seven-argument interface and removes later restart/partition
control flow, then requires byte-identical reconstruction of all three
original ELFs before producing candidates. The original archived assembly
and header are reused. Release `rvv_small_slide04` contains27 individual
calls (three shapes, three seeds, masks0/2/3) tied to all27 recorded error
lines, plus three original prefixes ending after seed0/mask3. The reducer preserves the
original PRNG, index loads, destination sentinel and expected-value oracle.

Recovery214 measured all30: the nine all-on single calls failed with the
exact original wrong element/value; all18 sparse/all-off single calls
passed. Each of the three2772-trial prefixes reproduced all three seed0
mask discrepancies. `rvv_slide_symptoms01` verifies12 matching candidate
results (nine singles and three prefixes), not30 successful reductions.
Therefore sparse/all-off failures still need preceding operations; their
passing isolated calls do not invalidate the original board failures.
`reduce_slide.py --mask-sequence` creates18 candidates retaining only the
three/four consecutive original mask modes at the failing offset/VL for
each shape/seed. This tests whether that local mask sequence is sufficient;
it is not yet proof of a stale-mask RTL mechanism.
Recovery215 completed all18 short-sequence candidates: each reproduces its
original selected sparse/all-off discrepancy, verified by
`rvv_slide_sequence_symptoms03`. For e8/m4 seed0, four calls in original
mask order produce three original errors: mask0 expects185/gets91;
mask2 and mask3 expect91/get185 at element511, VL512/offset511. This removes
the2772-call prefix but retains a demonstrated sequence dependency. Combined
with the nine isolated all-on failures, all27 recorded original slide
discrepancy tuples now have measured reduced reproductions.

Extension trace checkpoint (2026-10-10, recovery211): the instrumented
original sequence stopped after `seed=0 op=2 vl=127 mask=0 cap=128`, with
no matching RETURN marker. Two snapshots recorded cycles increasing from
11597139723 to 12136632755 and retired fixed at 1710203450. Last/head PCs
were 0x1053c/0x10540; the latter disassembles to
`vzext.vf2 v24,v25,v0.t`. This locates the call, not an internal RTL cause;
the probes do not establish head validity or the blocked queue.

`trace_extension.py --single-trial --trace-report <recovery211-report>`
retains the original fixture, assembly, and oracle but selects only seed0,
op2, length=cap-1, mask0. The unmodified original ELF is rebuilt and hash
checked first. Release `rvv_extension_single01` passed QEMU VLEN512/1024
and reproduced the no-retirement stall on board recovery213. Its final
marker is the same tuple; cycles advanced583823180 while retired remained
1688870403. ELF-decoded last/head PCs0x104fe/0x10502 contain the same
`vsetvli`/`vzext.vf2` opcodes as original204 and trace211. The audit is
`rvv_extension_symptoms01/symptoms.json` in the campaign evidence directory.
The original uninstrumented run did not print its trigger, so exact VL
equivalence is proven between trace and single, not independently for204.
The original preceding trial sequence is not required for this reproduction.
The earlier generic
VL2 overlap test passed and is not a reproducer for this VL127 observation.

The single extension scene uses VLEN1024, SEW16/LMUL2 destination v24/v25,
SEW8/LMUL1 source v25, VL127, tu/mu, and an all-on mask. It fills the
destination with0x5b using the original whole-register EEW8 load, loads128
source bytes `((i*73)^0x85)&255` into v25, loads the mask, and issues
`vzext.vf2 v24,v25,v0.t`. Keep these setup instructions for RTL replay;
replacing the whole-register load or running only the target is not yet a
validated reproduction. No Linux boot or original full trial matrix is
intrinsically part of the extracted stimulus, but bare-metal/VCS replay
has not been measured yet.

Zero-offset slidedown: `trace_permute.py` retains the original
`rvv_permute_restart_e16_m1_ops16` partition and adds drained BEGIN/RETURN
markers with seed/scalar/VL/mask/vstart/capacity. Original ELF reconstruction
is byte-identical; `rvv_permute_trace01` passed both QEMU VLENs and stalled
in recovery214 at seed0/op16/scalar0/VL32/mask0/vstart16/cap64. Cycles advanced
13379803799 to13903753158 while retired stayed2166292721; last/head PCs
0x109c4/0x109c8 decode as `vslidedown.vi v24,v8,0,v0.t` and `csrr a0,vstart`.
The original197 PC-only stall did not record its exact active trial.
`trace_permute.py --single-trial --trace-report <214-report>` extracts this
call with VL=cap/2 and vstart=VL/2. `rvv_permute_single01` passed both QEMU
VLENs; board equivalence is still pending. The earlier VL2/vstart1 generic
pass does not establish correctness at this measured restart condition.

Missing-NV ordered FP reduction: `reduce_redspecial.py` selects scenario3,
ordered-sum op0, VL=cap/2, sparse mask0x24, frm0 and initial flags0 for each
of11 original failing shapes. Original ELFs must rebuild byte-identically;
the archived SoftFloat tables and their indexing are retained unchanged.
Reference runs containing FP16 require `--cpu-feature zfh=true` and
`--cpu-feature zvfh=true`, matching the original FP16 reference setup.
The default-CPU attempt in `rvv_small_redspecial01` is retained as a failed
reference configuration (FP16 illegal instruction), not a board finding.
With those extensions, `rvv_small_redspecial02` passed all11 candidates at
both VLEN512/1024. Board reproduction remains unconfirmed.

* FP excess NV: case7. Inspect issue_be, fpnew simd_mask_i, per-slice status,
  pipeline tag/handshake alignment and scalar fflags commit. Archived vmfpu
  already computes a predicate mask, so the failing board result alone does
  not prove that masking is missing there.
* Legal extension overlap: case10. Compare ordinary `vzext.vf2 v24,v8` with
  high-end overlap `v24,v25`; capture dispatcher overlap state, source lifetime
  hazards, operand requests and writeback dependency. First exclude a
  maintenance/reshuffle instruction preceding the target.
* Large-offset slide mask inversion: case11. Run all-on, alternating, all-off
  after isolated reset and after the original sequence. Inspect mask owner,
  pointer and stale queued mask. No specific internal pointer bug is proven.
* Sparse FP ordered-reduction missing NV, indexed overlap after faults,
  comparison-result restart/alias, mask-logical alias, zero-stride kernel CSR
  stalls and the single NF7/e32/mf2 replay mismatch retain separate RVV IDs
  in `../ISSUES.md`; these twelve programs do not cover every outstanding ID.
* Misaligned setup SIGBUS occurs before the segment target in the original
  tests. It is a capability/setup issue until an aligned-staging target case
  proves otherwise; QEMU success does not mandate vector misalignment support.

## Failure inventory and priorities

`trace_fault.py --compare-current-oracle` deliberately retains three distinct
controls: the immutable original ELF, a current-source baseline and its
instrumented derivative. The original e8/mf8 replay ELF has not been rebuilt
byte-identically from the available current source, so aggregate agreement
alone cannot establish original per-trial equivalence. `classify_fault.py`
parses ordered BEGIN/CONTEXT/RETURN/CHECK records, preserving incomplete
trials and separating fault-count mismatches from raw context differences.
A segmented fault's address difference is not automatically an error.
Both archived VLEN512/1024 QEMU traces parse as48 complete trials with no
per-trial errors. Board evidence remains necessary for reproduction claims.
`audit_fault_controls.py` verifies the deployed binary and source hashes,
compares each control's aggregate result with the original report, and checks
that the instrumented per-trial counts/errors agree with its final summary.
It deliberately does not promote matching totals to per-trial original
equivalence. Missing or unfinished controls remain explicitly incomplete.

Recovery217 three-way e8/mf8 controls all report48 cases,48 signals,32 errors,
matching original202's aggregate. The instrumented current source locates
20 failing trials:12 all-off-mask trials unexpectedly fault (two checks each),
and8 sparse-mask trials report an earlier masked element's address/vstart
(one handler error each). For boundary1/mask0x24, observed vstart1 versus
expected2; for boundary3/mask0x24, observed3 versus expected5. Signal PCs match
the intended vector memory instruction. This describes the traced program's
actual failure; original per-trial equivalence and internal cause remain open.

`reduce_fault.py` extracts each completed, measured failing current-oracle
trial from the audited three-way controls. It checks a byte-identical current
baseline rebuild, selects before mmap/protection setup, and preserves the
signal handler, recovery, poisoning and replay oracle. Each resulting Linux
program executes one trial, including its actual page-fault recovery. These
are not bare-metal instruction-only tests: translating them to VCS requires
equivalent page mappings, exception/restart handling and saved-vector state.
The manifest retains `original_failure_equivalence_proven=false` until old
per-trial evidence is available; do not use the three matching totals alone
to close the original issue.

`export_verified.py` reaudits numerical evidence before exporting confirmed
cases only. `rvv_verified_handoff03` contains124 cases (83 gather,18 short
slide sequences,12 slide single/prefix cases,11 reductions), with source,
assembly, reduced/original ELFs, raw reports and hashes. It is incremental,
not complete historical coverage. Linux ELFs need the existing Linux-capable
harness, or a faithful setup/target/oracle port for bare-metal VCS simulation.

`audit_redspecial.py` validates original-report hashes, rebuilt original ELF,
candidate sources and deployed ELF before comparing scenario, operation, VL,
mask, rounding mode and actual/expected flags. Both original and candidate
must fail with exit1 and the identical discrepancy tuple. This proves only
the recorded flags symptom: the original log has no raw reduction result
bits, and neither full data equivalence nor an internal RTL cause is claimed.

Board recovery216 confirms all11 single ordered-reduction cases against
recovery202 (`rvv_redspecial_symptoms02/symptoms.json` in the campaign).
The smallest measured examples use VLEN1024, e16/mf4 or e32/mf2, VL8:
seed v16[0]=+infinity; v8 alternates +infinity and -infinity; mask bytes
are 0x24, selecting elements2 and5; frm=0 and initial fflags=0.
`vfredosum.vs v24,v8,v16,v0.t` reports fflags=0, whereas the archived
SoftFloat fixture and both QEMU reference runs expect NV=16. In e16 the
input encodings are 0x7c00/0xfc00; in e32 they are 0x7f800000/0xff800000.
Preserve the original assembly's m1 seed/destination setup and subsequent
fractional-LMUL source setup when transferring this case into simulation.
This is an infinity-cancellation stimulus, not a signaling-NaN input test.

`audit_permute_stall.py` checks original/trace/single zero-offset slidedown
ELFs, source hashes, final unreturned trigger and two live no-retirement
snapshots. The target and following CSR-read encodings must also match.
It rejects progressed, frozen, mismatched-run and wrong-trial evidence.
The original uninstrumented run did not print the exact trial; only the
trace and single run can establish that input equivalence.

Recovery216 confirms the single-trial e16/m1 slidedown stall. Preserve
VLEN1024, VL32, vstart16, all-on mask and the original input/setup sequence
from `rvv_permute_single01/rvv_trace_permute_single_restart_e16_m1_ops16`.
The target is `vslidedown.vi v24,v8,0,v0.t` (0x3c803c57), followed by
`csrr a0,vstart` (0x00802573). Original197, full trace214 and single216
all show live no-retirement at these same instruction encodings;
`rvv_permute_stall_symptoms01/symptoms.json` records hashes and snapshots.
The previously passing generic VL2/vstart1 example is not this stimulus.

`trace_fp_moves.py` checks an original stalled e16/mf2 FP-move ELF identity
and requires a byte-identical rebuild before adding drained BEGIN/RETURN
markers around the first seed/scalar/valid-box masked slide-up sequence.
The complete original loop order, assembly, inputs and oracle are retained.
This is a trace, not a single-trial reduction: serial output changes timing,
and the exact blocked trial must be measured before selecting a reproducer.
Recovery215 captured no retirement at ELF PC0x107b6 (`vfslide1up.vf`), with
head PC0x107ba (`csrr vstart`). Neither the head-valid state nor an internal
queue root cause is established by those PCs. Later tuple families are not
instrumented; a stall outside the traced family needs additional evidence.

Recovery217's traced FP-move run stops at seed0/scalar0/valid-box/op2,
requested VL32, vstart16, all-on mask, initial fflags0, capacity32.
PC0x108fc decodes as `vfslide1up.vf v24,v8,ft0,v0.t` (0x38805c57),
followed by `csrr a0,vstart`; two live snapshots add530704738 cycles
with unchanged retired1907223999. `--trace-root` and `--trace-report`
enable a single-trial extraction only after hash and no-retirement gates.
`rvv_move_single01` passes QEMU at VLEN1024. Recovery219 confirms the same
single-trial external stall: PC0x1062a is opcode0x38805c57, followed at0x1062e
by `csrr a0,vstart`. Live snapshots add593816000 cycles with retired1694972232
unchanged. `rvv_fp_move_stall_symptoms01` archives and verifies original215,
trace217 and single219 reports, ELF identities, sources and matching trace/
single triggers. Original215's exact unprinted trigger remains unproven.
Its VLEN512 pass is a portability check only: e16/mf2 capacity16 clamps the
requested VL32, so that reference point is not the same effective stimulus.

Recovery218 also captured a stall in `rvv_fp_move_restart_e32_m1`.
`trace_fp_moves.py --shape e32_m1` requires the same byte-identical original
rebuild gate. `rvv_move_trace32_01` passes QEMU VLEN512/1024. Recovery220
measures its stall at seed0/scalar0/valid-box/op2/VL16/vstart8/mask0/sticky0,
capacity32, completed578. Two live samples add528800731 cycles with retired
1913268093 unchanged. `rvv_move_single32_01` extracts this measured call,
passes QEMU512/1024 and is queued for board comparison. Its board reproduction
is not yet confirmed. Do not assume it shares the e16/mf2 internal cause.

`trace_fp_moves.py --shape` also accepts other legal FP SEW/LMUL shapes.
It checks the original live no-retirement evidence and decodes the deployed
ELF PCs as opcode0x38805c57 followed by `csrr a0,vstart` before tracing.
Measured capacity must match the selected shape at VLEN1024; reserved shapes
are rejected. The e16/mf2 single rebuild remains byte-identical after this
generalization. Recovery221 captures e32/m2 no retirement (532534207 cycles,
retired1770131293 unchanged); `rvv_move_trace32m2_01` passes both QEMU references
and is queued to locate that shape's exact trial. Its trigger remains unknown.

`audit_fp_move_stall.py` checks original/trace/single ELF lineage, live
no-retirement snapshots and decoded `vfslide1up.vf` followed by `csrr vstart`.
The trace and single final BEGIN fields must agree except for the count of
prior completed calls. Original unprinted trigger values remain unproven;
matching external stalls do not identify an internal RTL queue defect.

Static investigation lead (not a proven board root cause): the current FPGA
copy of `masku.sv` shortens read/commit counts by aligned architectural
vstart for masked non-lane operations. The current `sldu.sv` slide-up setup
starts at the slide offset, initializes issue bytes from VL minus stride,
and later suppresses prestart byte enables. For a four-lane configuration,
the measured e16/VL32/vstart16 and e32/VL16/vstart8 trace triggers both
start at a32-byte mask-word boundary while covering64 destination bytes.
Check whether the mask producer emits one word while SLDU consumes two.
First match these source versions and lane parameters to the built image.
Then capture request op/vfu/vm/VL/vstart, MASKU read/commit counters and
mask valid/ready, plus SLDU issue/commit counters, input/output/VRF pointers,
operand valid/ready and result-queue occupancy. The hypothesis is falsified
if all required masks reach SLDU or it blocks on a different missing resource.
Do not fix this by suppressing a wait or extending a timeout without that
cycle-level evidence; neither board PCs nor these source excerpts suffice.

`audit_fault_single.py --root RELEASE --report BOARD_REPORT --out NEW_DIR`
checks the20 single current-oracle replay trials against the frozen measured
sequence. It verifies local/deployed ELF and scenario-source hashes, exactly
one completed trial, failure exit and summary, trigger, signal/code, VL/vtype,
vstart, expected start, fault counts, handler errors and returned status.
Only page-aligned address relocation and equal actual/expected PC relocation
are normalized; page offsets and actual-minus-expected differences must match.
The output distinguishes pending cases from confirmed current-oracle matches.
It does not establish original old-source per-trial equivalence or an internal
RTL root cause. Recovery220 completes all20 single trials, and
`rvv_fault_single_symptoms02` confirms20/20 matching current-oracle signatures:
12 all-off-mask unexpected faults and8 sparse-mask earlier fault-address/
vstart mismatches. Both load/store and mprotect/unmapped cases are included.
This does not upgrade the original old-source equivalence claim.

`trace_fault.py --case rvv_fault_replay_e64_m8` supports additional legal
SEW/LMUL single-field unit-stride shapes, deriving compiler settings from
the archived case. Indexed, segmented, strided and negative-control families
are rejected rather than silently using the unit-stride oracle. The
`rvv_fault_controls64_01` original/current/trace controls pass QEMU512/1024.
Recovery221 confirms all three aggregate failures (48 cases,48 signals,32
errors). Its measured trace contains12 all-off unexpected faults and8 sparse
mask mismatches. `rvv_fault_single64_01` extracts those20 calls for separate
board verification; this is not yet a confirmed single-trial board result.
The archived original remains immutable;
its source equivalence to the current oracle is still unproven.

Original e8/mf8 disassembly at0x1030c..0x10324 shows a direct si_addr versus
expected_address comparison. `trace_fault.py --restore-unit-handler` creates
only a diagnostic source candidate with that old check; it disallows the
aggregate-control bypass and requires the complete rebuilt ELF hash to match.
The first candidate `rvv_fault_original_trace01` failed this identity gate:
original text2679 bytes versus candidate2671 bytes. It was not deployed and
does not prove that the handler check is the only source difference.
Further reconstruction requires additional source/disassembly evidence, not
repeated speculative edits. The existing20 single-trial claims remain scoped
to the measured current-oracle trace.

`batch_fault_controls.py` validates original failed ELF identities and legal
unit shapes before building independent three-way groups. Each child retains
its own source/manifest for `audit_fault_controls.py`; the parent release
shares one reference boot per VLEN and one board transfer. Explicit exclusions
must name existing shapes; duplicates and nonfailed parents are rejected.
`rvv_fault_controls_batch01` covers the20 remaining unit shapes (60 ELFs),
with120/120 QEMU runs passing. Recovery223 control results are recorded below.

Recovery223 first confirmed the e8/m1 and e16/m1 three-way aggregate controls;
the frozen `board_sample223_01.json` records these six completed cases. Other
groups in that sample are not yet complete. Per-trial reduction and board
comparison remain separate requirements.

The e8/m1 and e16/m1 reductions contain40 single trials, with80/80 reference
runs passing at VLEN512/1024. Recovery224 confirmed all40 measured signatures
against their full traces (`rvv_fault_e8m1_single_symptoms01` and
`rvv_fault_e16m1_single_symptoms01`). Reaudited exports are
`rvv_fault_handoff_e8m1_01` and `rvv_fault_handoff_e16m1_01`. This preserves
the old-original aggregate-only limitation. `batch_fault_singles.py` reduces remaining
groups only after three-way agreement, retaining each child manifest and its
frozen measured report. One parent release shares reference boots and board
transfer; `audit_fault_single.py` still checks each child independently.

`export_fault.py` reaudits both three-way controls and single-trial signatures
before exporting confirmed singles, immutable original/control ELFs, source,
reports and a complete file hash inventory. `rvv_fault_handoff01` contains the
20 confirmed e8/mf8 singles. Old-original per-trial/source equivalence remains
unproven. These Linux programs need page protection and signal recovery;
bare-metal VCS adaptation must preserve that environment, not just the vector
instruction. The exporter does not claim a proven internal RTL root cause.

Recovery223 completed all60 controls for the20 remaining unit shapes. The
frozen `rvv_fault_controls_batch01/board_sample223_02.json` preserves their
three-way aggregate agreement and20 measured bad trials per shape. Reduction
of the remaining18 groups is in `rvv_fault_single_batch01`; reference and
single-trial board acceptance must be checked separately. Its360 singles
passed720/720 reference runs at VLEN512/1024. Recovery225 confirmed360/360
matching single-trial signatures (`rvv_fault_batch_symptoms04`, frozen
`board_sample225_04.json`), with no pending or mismatched cases in this batch.
`rvv_fault_batch_handoff01` exports all18 groups after reauditing each one.
Together with e8/mf8, e64/m8, e8/m1 and e16/m1, this confirms440 singles
across22 legal unit-stride shapes, not440 independent RTL bugs. The equivalence
is to the measured current full trace; the old-original aggregate-only limit
still applies, and other historical families remain open.
`audit_fault_batch.py` validates the parent/child membership, manifest and ELF
hashes, then runs the single-trial signature audit for every child. It freezes
one board report and emits per-shape proofs suitable for `export_fault.py`.
Using the recovery223 report before these singles execute yields0 confirmed
and360 pending (`rvv_fault_batch_pending_audit01`), not a reproduction pass.

The e64/m8 singles completed in recovery223:20/20 signatures match the
measured full trace (`rvv_fault_single64_symptoms01`). The reaudited export
`rvv_fault_handoff64_01` contains these20 cases and their three-way controls.
As with e8/mf8, exact old-original per-trial equivalence is not proven.

The e32/m2 FP-move trace stalled in recovery223 at the same38805c57 slide-up
and00802573 vstart-read pair: VL32, vstart16, cap64, seed/scalar/invalid_box/
mask/sticky all0, op2. Live cycles advanced527162575 with retirement unchanged.
`rvv_move_single32m2_01` isolates that measured trial and passes both reference
VLENs. Recovery225 confirmed its no-retirement stall; the three-way audit is
`rvv_fp_move_stall32m2_symptoms01`, and the reaudited source/ELF/report export
is `rvv_stall_handoff_move32m2_01`. Trace and single triggers agree exactly
apart from the intentionally reduced completed-call count. The uninstrumented
original trigger and internal mask-queue state remain unproven.

Recovery224 confirmed the original e32/m4 FP-move no-retirement stall at
PC107b4/107b8, with38805c57/00802573 and529625684 additional cycles while
retirement stayed2028048145. `rvv_move_trace32m4_01` rebuilds that original
ELF byte-identically and passes VLEN512/1024 reference runs. Recovery226
confirmed the traced stall at VL64, vstart32, cap128, op2, with seed/scalar/
invalid_box/mask/sticky all0. `rvv_move_single32m4_01` isolates that measured
trial and passes both reference VLENs. Recovery228 confirmed its no-retirement
stall at10624/10628 with539927092 additional cycles and unchanged retirement
1704515673. `rvv_fp_move_stall32m4_symptoms01` passes the three-run audit;
`rvv_stall_handoff_move32m4_01` exports reaudited source, ELF and reports.
The unprinted original VL/vstart is unknown; do not substitute the e32/m2 trigger.

Recovery227 confirmed the original e32/mf2 move stall at107b4/107b8,
38805c57/00802573, with522238214 additional cycles and unchanged retirement
20373720470. `rvv_move_trace32mf2_01` rebuilds its original ELF byte-identically
and passes both reference VLENs. The trace is queued to measure the exact
VL/vstart/input combination; no single-trial or internal queue explanation is
yet established for this shape. Recovery228 deploys the previously queued
63 diagnostics plus183 remaining original cases, retaining every case.
Future efficient-order batches place measured-stall FP-move/extension/permute
traces after the other short diagnostics, but before long originals. The
already deployed recovery228 order is unchanged. Reordering its246 case
objects as a check preserves every object and moves the stall candidate behind
62 other diagnostics. This is risk-based scheduling, not a new passing verdict
or a change to any ELF, stimulus or timeout.
Recovery229 actually deploys that ordering:62 other short diagnostics precede
the e32/mf2 full trace, followed by183 remaining originals (246 unique cases).

`trace_fault.py --segment-controls --compare-current-oracle` supports separate
unit-stride NF2..NF8 controls with legal SEW/LMUL/register groups. It retains
the archived original ELF, recompiles the segment-aware baseline, and adds
read-only context diagnostics. Indexed/strided layouts and negative controls
remain rejected. A raw fault-address offset is not automatically a segment
error: any protected field within the expected segment may fault. The reducer
and single-trial auditor recognize the explicit segment layout, retain its
field count and split selector, and reject unsupported addressing modes.
They still require measured three-way agreement before constructing singles;
unit-stride single-field results cannot stand in for segment evidence.
The e16/m1 NF2 pilot is
`rvv_segment_fault_controls01`; its baseline rebuild is byte-identical to the
original, unlike the older unit-stride examples. This proves source/build
identity, not board behavior or trace noninterference.
All three pilot ELFs pass both reference VLENs (six reference executions).
The predeployment negative audit `rvv_segment_fault_pending_audit01` correctly
reports all three as not started, not as matching board failures.

`trace_fault.py --strided-controls --compare-current-oracle` separately
collects positive, negative and zero-stride replay controls. It validates the
field count, direction and canonical case name, preserves the archived
assembly, and records the gap selector for nonzero strides. Zero stride has
no gap loop; its uniform duplicate-store inputs remain unchanged. Indexed
and deliberately invalid restart/skip controls remain rejected. The pilots
`rvv_strided_fault_controls01`, `rvv_negative_stride_controls01`, and
`rvv_zero_stride_controls01` each rebuild their e16/m1 NF1 original exactly.
These are three-way controls, not yet board-confirmed reduced scenarios.
All nine pilot ELFs pass VLEN512/1024 (18 reference executions). Parsed trace
outputs contain96 unique complete trials for each nonzero direction and16
for zero stride at each VLEN, with zero errors. They are queued for board
measurement; reference success does not establish board reproduction.
The current reducer intentionally rejects strided layouts until their measured
trials and address semantics have been reviewed.

After recovery224, the204 unattempted originals comprise184 historically
stalled and20 mixed-outcome memory-restart cases. Future `efficient_order`
batches retain short diagnostics first, then prioritize memory-restart
originals to resolve those mixed outcomes before repeated known stall families.
This changes scheduling only, not ELF bytes, case membership or timeouts.
The already deployed recovery225 order is unchanged; all565 case objects were
checked to remain identical under the future ordering.

History audit `rvv_memory_observation_history01.json` checks80 report records
for all20 memory-restart mixed outcomes. Every incomplete record explicitly
reports a UART observation gap, and every later passed record has exit0 and
the pass marker for the identical ELF hash. These are mixed observations,
not20 established RTL failures or confirmed intermittent numerical failures.
Fresh retests remain queued; this historical audit does not substitute for
them or prove that every other memory configuration is correct.
Recovery227 subsequently completed all20 identical original ELFs with exit0
and their pass markers. Frozen `rvv_memory_retest227_01.json` records80352
executed configurations,13728 explicitly skipped configurations and0 errors.
The oracle increments skips before `continue`, separately from executed cases;
the skipped configurations are not passes. These20 historical observation-gap
cases did not reproduce a correctness failure in this run; this does not close
other memory-fault, segmented, indexed or stalled families.

Original2767 inventory:1889 passed,744 failed,87 stalled,47 mixed outcomes.
Mixed outcomes and failed exits are not automatically distinct RTL defects.
The176 FP-move/extension children:72 passed,47 numerical failures,57 stalls.
Permutation children through recovery200:140 passed,80 numerical failures,
54 stalls,124 without a terminal result. Recovery201 was interrupted by the
user and is not a new confirmed stall. Child counts must not be added to the
original counts as independent bugs.

`collect.py` exports every original/child nonpass or pending record with its
original name, SHA256, status and evidence references. It also includes the
deployed source snapshot and representative board results. Repair priority:
decode and whole-register offset first; then mask stream contract and prestart
write suppression; then memory fault suppression and remaining flag/overlap
issues. Re-run original full ELFs after each focused fix and representative
regression. A passing minimal scenario alone cannot close its parent finding.

Recovery229 measured follow-up (2026-10-10):

- `rvv_segment_fault_controls_proof01` checks the immutable NF2/e16/m1
  original, rebuilt baseline and traced sequence: each reports96 cases,
  96 signals and64 errors. The trace contains40 failing trials. Matching
  totals do not prove the uninstrumented original's per-trial equivalence.
- `rvv_segment_fault_single01` isolates those40 measured triggers, including
  both segment split positions. All80 QEMU checks at VLEN512/1024 pass;
  board singles are queued, not yet confirmed. Frozen control evidence is
  `rvv_segment_board229_01.json` in the campaign directory.
- Positive, negative and zero-stride controls each reproduce their original
  aggregate summary, audited in `rvv_strided_fault_controls_proof01`,
  `rvv_negative_stride_controls_proof01`, and
  `rvv_zero_stride_controls_proof01`. This is not a single-trial proof.
- `rvv_segment_setup_single_proof01` confirms all9 preparation-alignment
  singles against their archived originals: same opcode, signal/cause,
  misalignment, preparation VL and later unexecuted target instruction.
  Evidence is frozen in `rvv_finite_board229_01.json`. These are preparation
  alignment exceptions, not evidence of9 segment-target RTL defects;
  original C-source equivalence remains unproven.
- `audit_fp_compare.py` verifies frozen reports, deployed ELF hashes and
  scenario sources before comparing explicit stimulus/fflags tuples.
  `rvv_compare_uncovered_proof01` confirms40 of41 new singles against the
  archived original failures. This does not prove internal RTL causality.
  `rvv_detail_fp_compare_unmasked_alias_v8_e16_m8` passes in isolation:
  its measured original first failure was op0/seed0/VL512/mask0/sticky1,
  expected_flags=actual_flags=17 with64 data errors. The isolated result has
  flags17 and zero errors. Keep that original data failure open; do not
  substitute a later flag failure or count this passing single as a repro.
- The stride-aware reducer preserves the exact baseline except for a selector
  before mmap. Nonzero strides retain gap1/3; zero stride retains boundary0.
  `rvv_strided_fault_single01`, `rvv_negative_stride_single01` and
  `rvv_zero_stride_single01` contain40/40/12 measured failing trials.
  All184 reference executions at VLEN512/1024 pass. These singles are queued
  for board reproduction, not yet confirmed. `audit_fault_single.py` also
  compares the stride/gap trigger and the complete fault/recovery signature.
- Recovery229's e32/mf2 FP-move trace stops after642 completed calls at
  seed0/scalar0/invalid_box0/op2/VL16/mask0/sticky0/vstart8/cap16.
  Its terminal no-retirement evidence is in
  `rvv_failure_retest01/supervisor41/terminal_recovery229.json`.
  `rvv_move_single32mf2_01` is generated from that measured trigger, with
  byte-identical original rebuild and passing VLEN512/1024 references;
  single-case board reproduction remains pending.
- Recovery230 completes all40 NF2/e16/m1 fault singles. Frozen evidence
  `rvv_segment_single_board230_01.json` and `rvv_segment_single_proof01`
  confirm40 exact full-trace/single signatures, with zero pending. This
  checks trigger, SIGSEGV code, page-relative address and address delta,
  vstart/VL/vtype, fault-PC delta, return/fault counts and error count.
  `rvv_segment_fault_handoff01` exports40 cases plus three-way controls;
  all180 archived file hashes verify (3960350 bytes, excluding hashes.json).
  This supersedes the earlier pending NF2 single status only. Original
  uninstrumented per-trial equivalence and internal RTL cause remain
  unproven; the other stride and FP-move singles are still queued.
- `export_fp_compare.py` reaudits measured flag matches and resolves the
  unique archived build manifest by SHA256 before copying original ELFs.
  `rvv_compare_uncovered_handoff01` exports40 confirmed singles and records
  the one passing e16/m8 data-failure reduction as unresolved. All326
  file hashes verify. The reconstructed C oracle is explicitly distinguished
  from the immutable original ELF; these artifacts are not a claim of
  original C-source equivalence or an internal RTL root-cause proof.
- Recovery230's original `rvv_fp_move_restart_e64_m1` has a terminal live
  no-retirement interval of525003779 cycles with retired2053075959 unchanged.
  Exact deployed-ELF disassembly maps last_pc0x1077c to38805c57
  (`vfslide1up.vf v24,v8,ft0,v0.t`) and head_pc0x10780 to00802573
  (`csrr a0,vstart`). Original input at the stall is not printed.
  `rvv_move_trace64m1_01` preserves the full sequence and has a byte-identical
  original rebuild plus passing VLEN512/1024 references. It is queued for
  board tracing; no e64/m1 single-trigger equivalence is claimed yet.
- To investigate the nonreproducing unmasked-v8 e16/m8 data failure,
  `reduce_fp_compare.py --prefix-full-alias --reconstructed-only --data-detail`
  retains the first50 original-loop calls through op0/seed0/full-capacity
  VL/mask0/sticky1. Only the final call emits raw destination bytes.
  `rvv_compare_alias_prefix01` passes both reference widths with exactly50
  calls and flags17 (capacity256 at VLEN512, capacity512 at board VLEN1024).
  It is queued as a discriminating prefix, not a confirmed reproduction.
  Prior state dependency remains a hypothesis; current C reconstruction and
  added diagnostics mean this does not establish original source identity.
- Recovery231 completes all92 stride singles with matching measured full-trace
  signatures: positive40 (`rvv_strided_single_proof01`), negative40
  (`rvv_negative_stride_single_proof02`) and zero12
  (`rvv_zero_stride_single_proof02`). The frozen reports are
  `rvv_stride_single_board231_01.json` and `rvv_stride_single_board231_03.json`.
  Earlier partial proofs remain archived; their pending counts are not new
  failures. `rvv_strided_fault_handoff01`, `rvv_negative_stride_handoff01`,
  and `rvv_zero_stride_handoff01` export40/40/12 cases, with all180/180/68
  file hashes verified. This supersedes pending status for these singles.
  Original full-program aggregate reproduction, full-trace exact signatures,
  and single-case signatures remain distinct evidence levels; no internal
  RTL cause is proven solely by this agreement.
- Recovery231 confirms the e32/mf2 FP-move single stall. Audit
  `rvv_fp_move_stall32mf2_symptoms01` matches the original227, trace229 and
  single231 opcode pair38805c57/00802573. Trace and single share
  seed0/scalar0/invalid_box0/op2/VL16/mask0/sticky0/vstart8/cap16.
  The single has517638182 additional cycles with retired2475060306 unchanged,
  at PCs0x10618/0x1061c. `rvv_stall_handoff_move32mf2_01` exports the sources,
  original rebuild, trace/single ELFs and snapshots; all21 file hashes verify.
  This supersedes the pending e32/mf2 single status, but original unprinted
  input and blocked internal-unit identity remain unknown.
- Recovery232's first50-call e16/m8 comparison prefix passes on the board:
  `rvv_compare_prefix_board232_01.json` records exit0, cases50/errors0,
  capacity512, returned_vstart0, fflags17 and both guards91. Exact deployed
  ELF identity and all64 raw bytes match its VLEN1024 reference result.
  Both the isolated call and this reconstructed prefix therefore fail to
  reproduce the original64-data-error observation. Restoring these49 prior
  calls is not sufficient in this experiment. Keep the original finding
  unresolved; do not claim an intermittent RTL cause, an oracle bug, or a
  repair without further evidence. No matching archived C source was found
  in the campaign by filename; original ELF and source hashes remain intact.
