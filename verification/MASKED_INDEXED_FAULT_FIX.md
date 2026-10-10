# Masked indexed memory fault: diagnosis and fix contract

## Final-source AXI B error directed regression (2026-09-25)

`apps/riscv-tests/isa/rv64uv/vstore_axi_error.c` now isolates one aligned
`vse64.v` to unmapped address `0xe0000000`. The address is outside the SoC's
DRAM (`0x80000000..0xbfffffff`), UART (`0xc0000000..0xc0000fff`) and control
(`0xd0000000..0xd0000fff`) windows. The test requires one store-access-fault
trap (`mcause=7`), `mtval=0xe0000000`, `mepc=store_fault`, and `vstart=0`.
The program is compiled twice from the same test source: the normal RTL ELF
uses the existing SoC runtime, while `SPIKE_REFERENCE` supplies a fixed 2 MiB
stack and a `tohost` exit because standalone Spike has no SoC control block.
The reference run used `--isa=rv64gcv_zvl1024b` and the matching 1 GiB DRAM
map `-m0x80000000:0x40000000`; it exited with code zero. Its frozen ELF is
`out/integrated-store-b-error/spike_input.elf` (SHA-256
`f495f895dcb7f898769f874ab4412e8e1409c14fd068c2ff7b3eecdea3b02630`).

The final integrated VCS image ran frozen RTL ELF
`out/integrated-store-b-error/rtl_input.elf` (SHA-256
`d1eae39a59c186911f18b8637dafcb2057437580a4fc73b1564cdd6806cebc70`)
in `out/integrated-store-b-error/rtl_run_01/`. It emitted one AXI AW/W/B
transaction, zero accelerator exceptions, and no architectural trap. The
program reported four failed checks (trap count, cause, address, PC); its
`vstart=0` check happened to pass because the register stayed at zero.
`out/integrated-store-b-error/independent_audit.json` correctly reports
`FAIL` (0/1), not a differential PASS. The failure stops normal trace
validation, so the current directed run does not independently prove B's
response code; the earlier bounded AXI probe below measured B=`DECERR`
reaching VSTU. This is now a reproducible final-source signoff blocker.

The [RVV 1.0 precise-trap rules](https://docs.riscv.org/reference/isa/unpriv/v-st-ext)
require `vstart` to identify a restartable element. Writes at or after that
element may have occurred in idempotent memory only when replay still produces
the correct final state; non-idempotent regions may not have been updated at
or after the faulting element. The standard extensions do not define an
imprecise vector-trap mode that can be used to waive this contract. An AXI B
error identifies a write *burst*, not the beat or vector element that failed.
Therefore a repair must define burst-to-element ownership and preserve the
original virtual address, and must prevent a younger architectural success
response before the B outcome is known. The current dispatcher forwards a
store exception only with the sequencer's response to the resident CVX
request. Simply latching `b.resp` in VSTU after that response cannot report
the fault. No B-error RTL repair has been accepted yet; the one-element test
is a necessary discriminator, not proof of multi-beat or non-idempotent
restart correctness.

Status: the B-error gap is reproduced on the final integrated VCS image; no
B-error RTL fix has passed review. The separate masked-indexed functional
fix was developed in `/home/wangwy/openproject/ara_dsa_masked_indexed_fix`
and is already present in the final integrated RTL. Its focused VCS/Spike
and three-case UVM evidence does not close the B-error fault contract.

## Latest-image UVM protocol closure (2026-09-24)

The separate candidate ten-seed load/store/slide replay is **not** a PASS.
Seed 71 (`.../tests/ara_dsa_rvv1_load_store_slide_0/result.json`) reports
PASS. The next frozen input reached `vsoxei32.v v4,(a5),v17` at PC
`0x80000a0a`; the VCS testbench stopped at `hardware/tb/ara_tb.sv:1273`
because its AXI write address `0x99f65a64` fell in the architectural DRAM
window but outside the 2 MiB behavioral L2 backing store. The preceding
retirement and Spike log give `a5=0x80018aba`; Spike's `v17` data contains
index `0x19f4cfaa`, whose sum is exactly `0x99f65a64`. Thus the reported
address is consistent with a generated indexed-store operand, not evidence
of an arbitrary AddrGen arithmetic error. Spike's default 2 GiB memory map
differs from the testbench's backed L2: its commit log records a partial
store at this PC (`mem 0xdd399ea8`, `vstart=1`) followed by a trap, and its
run then hits the 30-second Spike limit. The case result is `SPIKE_FAIL`
with only a 695-instruction matched prefix; it is **not** a strict
differential PASS or a classified RTL failure. The ten-seed runner and its
audit waiter were stopped after this definitive environment mismatch, with
the frozen input and traces retained. A focused replay must align Spike and
RTL memory regions or bound generated indexed addresses while retaining a
separate exception test; do not enlarge L2 or disable the guard merely to
obtain a passing run. The exception and AXI behavior still need cycle-level
comparison before claiming hardware correctness for this seed.

A bounded reference-only replay used the same frozen ELF with Spike memory
regions `0x80000000:0x200000,0xbfe00000:0x200000` and an instruction limit
of 1,000. Its independent log is
`out/masked-indexed-seed72-spike-map-probe-20260924-01/spike_commit.log`.
At PC `0x80000a0a`, it records `vstart=0` and no committed memory write,
whereas default-memory Spike recorded `vstart=1` and one write. This
isolates a reference-memory-map effect; it does not by itself explain why
the RTL reached a later middle-window AXI request. The next discriminating
probe must capture each index element's effective address, AXI response,
VSTU exception state and `vstart` on the existing candidate image.

Static VSTU review narrows the likely hardware-side gap: `vlsu.sv` connects
both `normal_axi_resp.b` and `normal_axi_resp.b_valid` to VSTU, so the B
response code **is available at the interface**. However, `vstu.sv` currently
consumes a B response by decrementing `pending_b` without consulting
`axi_b_i.resp`. Thus an AXI write error is not presently converted into a
store exception by this block. This explains how an out-of-range element
*could* be followed by later indexed elements, but the actual first
element's B code has not yet been captured. A bounded B-channel/AddrGen
probe is required before changing exception propagation; default-XBar
behavior alone is not cycle-level proof of the observed response.
The SoC routes `0x80000000..0xbfffffff` to L2. The AXI crossbar's unrouted
branch uses `axi_err_slv` with `RESP_DECERR=2'b11`, so the first generated
index outside that range has a concrete expected response. The isolated
probe worktree records normal-VLSU and system-level AW/B handshakes,
`b.resp`, AddrGen exception indication and VSTU exception state over cycles
7750..7900 of the frozen seed. If the first out-of-range AW receives B=`11`
and VSTU advances without exception, the missing response-code check is
measured; if not, routing or request association must be investigated.

The first isolated probe image compiled with a 450-source manifest check
PASS and replayed the byte-identical frozen seed-72 ELF (SHA-256
`4775cacdc48dc592fdc3df5ac7e2a28409360385c4a5258ab2c953281952dc2e`).
Its `out/masked-indexed-seed72-b-probe-20260924-01/run/console.log`
records system-level B handshakes with `resp=3` at cycles 7822, 7828 and
7834 for out-of-range indexed-store addresses. **The corresponding normal
VLSU/VSTU B handshakes occur at cycles 7824, 7830 and 7836, also with
`resp=3`.** The VSTU exception indicator remains zero, and subsequent AWs
are issued. The prior verbal reading that B-valid was still zero at VSTU
was incorrect; both the original and the independent continued replay show
the same internal handshakes. The continued replay at
`out/masked-indexed-seed72-b-probe-continue-20260924-01/` suppresses the
L2-hole fatal only under the probe plusarg and stops at cycle 7900; it
confirms more B=`3` handshakes with no VSTU exception. It is diagnostic, not
a correctness PASS, because middle-window writes may alias simulation SRAM.
The unmodified candidate testbench still rejects such accesses. These data
establish that VSTU acknowledges an AXI write error as a successful B
completion; a correct fix must preserve the failing instruction's element,
address and queue ownership when reporting the exception, not merely set an
unqualified error bit.

The second probe image independently passes its 450-source manifest recheck
and uses the same frozen ELF hash. In its continued trace, the first
out-of-range system AW at cycle 7820 receives B=`DECERR` at 7822; the
corresponding VSTU-side `b_valid/b_ready=1/1, resp=3` occurs at 7824.
Further VSTU-side B=`3` handshakes occur at 7830 and 7836, with
`vstu_exc=0` throughout. The testbench's middle-L2-hole AW at 7838 is
therefore not merely an in-flight request ahead of the first B error: the
first error has already reached and been consumed by VSTU. The second
diagnostic run allows the hole temporarily and exits at cycle 7900; it
cannot sign off the program or memory effects.

Before an RTL change, the bus-fault contract needs two parts: associate
each B response with the originating instruction and element/address, and
define how indexed-store requests already accepted by AXI are accounted for
while the faulting `vstart`/`tval` is reported. The RVV precise-trap rule
permits elements after the fault to have been written in an idempotent memory
region if restart yields the correct final state; it forbids such post-fault
updates in non-idempotent regions. Thus later AWs in this DRAM-oriented
diagnostic are not, by themselves, a specification violation. The current
`addrgen_axi_req_t` carries address, size and length to VSTU but no element
index; VSTU tracks per-instruction `pending_b` rather than per-burst fault
metadata. A one-bit `exception_pending` assignment alone cannot meet this
contract. Regular successful stores and QBS/AKV AXI ownership must remain
unchanged during any eventual fix.

The exception path also crosses a sequencer boundary: in
`ara_sequencer.sv`, the memory response to the upstream requester is formed
when `addrgen_ack_i` (or its saved acknowledgment) and operand-side accepts
are complete. That condition does not wait for the corresponding store B
responses. Consequently, merely checking `axi_b_i.resp` in VSTU would not
reliably deliver a late bus fault to the upstream request. A proper design
must retain the faulting store's request identity until B completion and
hold or separately reconcile the architectural response. This may change
store latency; it needs focused correctness and representative performance
regression, not an unmeasured one-line fix.

The accelerator response type in `hardware/include/ara/intf_typedef.svh`
places `exception` alongside `resp_valid`; its separate `store_complete`
bit has no late-exception payload. The dispatcher forwards
`ara_resp.exception` when `ara_resp_valid` is asserted. In this interface,
a store bus fault cannot be reported architecturally after an earlier
successful response has already been accepted. A bus-fault-capable design
must therefore delay that store's response until its relevant B results are
known, or change the CVA6/Ara response contract explicitly. The existing
early-response optimization and its performance effect must be measured
against that correctness requirement.

RVV precise-trap source: RISC-V Vector Specification, section 17.1,
`https://docs.riscv.org/reference/isa/extensions/vector/_attachments/riscv-v-spec.pdf`.

`out/masked-indexed-latest-uvm-closure-20260924-01/` contains a single
AXI-delay-enabled VCS image with a 454-file source manifest and three frozen
runs: real Qwen2.5 combined QBS+AKV, read reset-abort, and write reset-abort.
All three `uvm_result.json` files report `PASS` with no issues. The formal
`signoff/signoff.json` reports UVM `PASS`: all 24 required protocol bins are
covered on the same image, including AR/AW backpressure and both reset-abort
directions. The two explicitly excluded, unreachable bins remain listed in
`signoff/uvm.json`. Both `INPUT_SHA256SUMS` and `RUN_SHA256SUMS` were checked
from each case directory and passed. This closes the candidate's specified
three-case UVM protocol gate, not the whole-project Linux, random, code
coverage, or post-merge regression gates.

The frozen real-model AKV-v2 ELF (SHA-256
`b6a2503eb1ee63bad30dea3743f846be4f170fbd5ee61860aa4be35fd7981f8c`)
was also replayed on that same latest candidate VCS image at
`out/masked-indexed-latest-akv-real-20260924-01/`. Program self-check and UVM
both PASS: 2,792/2,792 CVXIF requests/responses, 2,646/2,646 backend
allocations/completions, zero protocol issues. The output `gold_results.txt`
is byte-identical to the previously passing real-model AKV-v2 run; both
frozen-input and run-artifact SHA-256 manifests recheck successfully. This
is candidate-version functional evidence for the real AKV data, but not
Verilator code coverage or full-model Linux signoff. A separate instrumented
2 MiB candidate Verilator image is being built for that coverage step.

On the same candidate VCS image, the `rvv-corners` suite at
`out/masked-indexed-latest-rvv-corners-run-20260924-02/` completed 35/35
self-checking directed cases. Its separate
`verification_audit_directed.json` reports PASS for all 35 frozen inputs and
commit traces, with zero failed cases or audit errors. The first launch at
`out/masked-indexed-latest-rvv-corners-run-20260924-01/` lacked 34 ELF files
and did not exercise those cases; it is retained as an input-preparation
failure, not an RTL failure. These directed self-checks do not constitute a
Spike full-state comparison or replace the pending random-profile regression.
All 35 frozen corner ELFs independently passed the 2 MiB Verilator RAM-fit
preflight. `verification/coverage/run_directed_coverage.py` rechecks the
suite's independent VCS audit, per-ELF input hashes and self-check markers
before replaying them on the candidate Verilator image. The independent
`ara-dsa-masked-indexed-rvv-corners-coverage-20260924-01.service` job is
queued behind that image build; its 35-case merge, uncovered-point review
and coverage-integrity signoff are not yet results.

## Frozen seed 71: segmented-store exception follow-up

The original defined-source load/store/slide seed 71 stalled at
`vsoxseg2ei32.v v25,(s6),v31,v0.t` (PC `0x800005a6`). A focused cycle-level
probe distinguished two independent causes. At the faulting store's
misaligned-address response, VSTu completed its current micro-op without a W
beat but retained buffered source and predicate data; the next micro-op could
not consume a predicate word still owned by the previous instruction ID.
The candidate VSTu exception path now drains the faulting operands and its
owned predicate word. On an isolated VCS image, the same frozen ELF then
self-checked to completion, but strict Spike replay exposed a second cause:
`segment_sequencer` discarded the micro-op's exception response and let the
architectural segmented store continue. The candidate now captures that
response, stops injecting micro-ops, waits for backend idle and returns the
exception to CVA6. The old ten-seed background run was stopped after its
definitive seed-71 failure; its output remains preserved.

On the new isolated image, the exact frozen seed-71 ELF reaches a Store
Address Misaligned trap (cause 6, `tval=0xdd38e24e`) at the same PC as Spike.
The strict scalar comparison reports `TERMINAL_MATCH` across 2,621 matched
instructions. The initial vector comparison reported `PREFIX`: 74 vector
instructions matched, but the trapped store (arch_seq 120) had 12 SLDU VRF
write events. An offline comparison of all 256 enabled bytes against the
known Spike state immediately before the fault found zero differences. The
checker now accepts such a trapped *store* only if every byte is known and
identical to that prior state; it reports the request separately rather than
pretending it retired. An independent replay of the frozen seed-71 RTL trace
against a fresh Spike trace reports vector `PASS` (74 retired requests plus
one verified identity-write trap), and strict `verify.py audit --require-trace
--require-vector --require-full-match` reports `PASS`. This proves the observed
VRF writes did not change the architectural register state. It does not by
itself prove all memory side effects of that exact faulting store; the
directed fault-source test below checks a representative partial store.

Evidence: `out/masked-indexed-fix-seed71-ucli-20260924-01/` contains the
cycle-level probe; `out/masked-indexed-fix-vstu-drain-seed71-20260924-01/`
contains the post-drain self-check;
`out/masked-indexed-fix-seg-ex-seed71-strict-20260924-01/` contains frozen
input/image hashes, strict comparison JSON and both traces;
`out/masked-indexed-fix-seg-ex-seed71-identity-recompare-20260924-03/` contains
the independent recompare and PASS audit. The source for these images is an
isolated, still-dirty candidate worktree, not the main verification image.
Complete memory-side-effect and wider QBS/AKV regressions remain open.

As a normal-path regression on that same new image, the separately frozen
load/store/slide seed 72 passed RTL self-check, Spike scalar comparison
(`TERMINAL_MATCH`) and vector writeback comparison (`PASS`):
`out/masked-indexed-fix-seg-ex-seed72-regress-20260924-02/`. This is one
representative check, not the full ten-seed or QBS/AKV regression.

A new `rvv:vseg_indexed_fault_source` directed program checks an indexed
segmented store with a fault at element 1 after source registers `v25/v26`
have been loaded in a different EEW layout. Its trap handler records
`mcause`, `mtval` and `vstart`; the program checks the preceding element's
two fields, the untouched later memory, and all 16 logical source values
after the trap. The first draft used `vmset.m` on an uninitialized `v0` and
stalled before the fault. A bounded UCLI probe at 1000 ns measured
`idx_predicate_valid=1`, `idx_predicate_active=X`, and an unknown low byte
of the VSTu mask word; that run is a separate unresolved mask-initialization
observation, not evidence about segmented exception side effects. With a
known all-ones `v0` initialized by `vmv.v.i`, the frozen directed test passed
in 16.96 s on the same candidate image, and `verify.py audit --require-trace`
reported PASS: `out/masked-indexed-fix-seg-fault-source-directed-20260924-02/`.
This self-check does not add a full Spike state comparison; the rv64uv ELF
uses `EXIT_CHECK` and has no `tohost` symbol required by the strict random
replayer. Do not reinterpret its initial, never-started strict-replay
attempt as a functional result.

The eight-seed frozen load/store/slide replay under
`out/masked-indexed-fix-seg-ex-slide-seeds73-80-20260924-01/` finished with
seven `PASS` cases. Seed 76 is `INCOMPLETE_PREFIX`: `vmv.x.s a3,v11` reads an
architecturally unknown element, so that case is not a full-match pass or a
demonstrated RTL mismatch. The frozen source has this read at line 1085 and a
masked `vredxor.vs` targeting `v11` at line 1067; the first unobservable
write recorded by the comparator occurs still earlier, so the reduction
cannot be identified as the root cause from this trace. The comparator stops
at PC `0x80001160` after 1,197 matched scalar commits. Additional
defined-source seeds require their own frozen inputs and audit; this replay
does not replace the outstanding
real-model QBS/AKV and Linux checks.

A separately generated **defined-source** seed 76 ELF (SHA-256
`d04011508848dcadbf90da38729e9d1192a3ababe91b0c467e1cbf8fa428dc3a`)
was replayed on the candidate VCS image and patched Spike under
`out/masked-indexed-fix-seed76-current-checker-20260924-01/`. The replay
completed in 21.72 seconds with `TERMINAL_MATCH` and vector `PASS`; the
independent `independent_strict_audit.json` reports PASS with frozen input,
trace, complete vector and terminal checks. Its 202 vector-destination
requests consist of 201 compared retired requests plus one verified
zero-write trapped request. This is not a retroactive PASS for the different
original seed 76 ELF, whose unknown source value remains unobservable.

That replay used the 15:55 candidate VCS image, while `vstu.sv` changed at
18:21. The two frozen representative ELFs were therefore re-run on the 19:50
probe-bound image built from the latest candidate RTL. Seed 71 and the
defined-source seed 76 both report `PASS`, `TERMINAL_MATCH`, vector `PASS`,
and independent strict audits PASS under
`out/masked-indexed-latest-seed71-20260924-01/` and
`out/masked-indexed-latest-seed76-20260924-01/`, respectively. The original
unobservable seed 76 remains a separate incomplete case. The older real-model
QBS/AKV image also predates the latest VSTu edit, so it is not inherited as
latest-RTL evidence.

That latest 2 MiB QBS+AKV-v2 image has now compiled with a 454-file source
manifest whose drift check PASSes. The frozen real Qwen2.5 combined program
under `out/masked-indexed-latest-qwen-gate-20260924-01/real_qwen/` completed
with UVM `PASS`, 3,532/3,532 CVXIF requests/responses, 3,155/3,155 backend
allocations/completions, and zero re-audit issues. The input and run hashes
check from the artifact directory. The first wrapper exit was a relative-path
hash-check setup error, not a simulation or DUT failure; the wrapper has been
corrected without rerunning VCS. A single Qwen program does **not** close the
full UVM protocol plan: the formal gate remains `INCOMPLETE` for AR/AW
backpressure and read/write reset-abort bins. Those need the planned delayed
and reset cases on a common latest-RTL image before UVM signoff.

The fresh delayed-AXI image under
`out/masked-indexed-latest-uvm-closure-20260924-01/` also passed its 454-file
source-manifest drift check. Two independent directed runs on this same image,
`out/masked-indexed-latest-delay-load-20260924-01/` and
`out/masked-indexed-latest-delay-store-20260924-01/`, completed their
self-checks with `tohost=0`, UVM `PASS` and zero issues. Both input and run
hash lists independently rechecked. These cases cover the programmed
all-masked, mixed active/inactive, nonzero-`vstart`, ordered-store and
fault-followed-by-store scenarios under AXI delay. They do not exhaust all
possible outstanding B-response interleavings; the delayed three-case
protocol closure is a separate running gate.

## Isolated candidate and measured checks

MASKU now records the producing instruction ID and absolute first element
with each queued predicate word. VLDu/VSTu carry those tags through the same
flushable spill register as the mask bits. AddrGen waits for a matching
instruction ID and word range before classifying an indexed element. For an
inactive element, it consumes the index and emits an ordered skip descriptor
without MMU translation or AXI AR/AW. VLDu consumes a skip as a zero-byte-enable
synthetic result without AXI R; VSTu advances its source/mask position without
AXI W. VSTu tracks WLAST/B counts per queued instruction so a zero-write
store cannot retire on an older store's B response. Early store exceptions
are retained with the faulting queue slot while older B responses drain.

The candidate elaborated with Verilator full-design lint (exit 0) and compiled
as an isolated VCS image under
`out/masked-indexed-fix-vcs-20260924-01/` (compile exit 0). On that same image,
the current masked indexed load and store directed programs both self-check
PASS and pass the independent trace-integrity audit under
`out/masked-indexed-fix-load-20260924-02/` and
`out/masked-indexed-fix-store-20260924-01/`. The unmasked indexed load/store
fault-restart test also PASSes under
`out/masked-indexed-fix-unmasked-fault-20260924-01/` with trace integrity.
These directed tests do not supply a matching Spike full-state transcript;
the attempt to apply that stricter audit failed for missing reference artifacts
and must not be reported as a full-state PASS. A replay of the original frozen
random seed 76 and the three-point RVV/QBS/AKV quick gate are running in
independent background directories; their results remain open.

The candidate still needs proof across wider predicate word/flush alignments,
including downstream W/B accounting with mixed active/inactive stores.
Representative randomized and real-model regressions are also required before
merging or replacing the original failing-image evidence.

A focused VCS probe on the candidate RTL now closes the **AddrGen-side** part
of the skip question for two directed programs. The isolated run at
`out/masked-indexed-skip-probe-20260924-01/` compiled the probe-bound image,
froze the simulator, probe, relevant VLSU sources and both ELFs with SHA-256,
and ran the masked-indexed load and store alignment tests. Both self-checks
PASSed. The cycle log records 11 load and 13 store skip descriptors; on every
observed skip-push cycle, the predicate was valid/inactive and AddrGen's
MMU-request, AR-valid, AW-valid and exception signals were zero. A probe
assertion enforced this condition throughout both runs, including the
nonzero-`vstart` and mixed active/inactive cases. This evidence is local to
AddrGen's request-generation cycle: it does not establish that all earlier
AXI W/B traffic had drained, that every possible partial mask-word/flush
alignment is covered, or that the full random and real-model regressions pass.

## Evidence

- Frozen random seed 76 reaches a masked `vloxei16.v` with `vl=2`,
  `vstart=1`, e64 data and e16 offsets. Element 1 is masked off. Its offset
  is `0x13ee`, so adding the frozen base `0x80009a18` produces a misaligned
  address. Spike retires the instruction; RTL raises load-address-misaligned.
- The directed `rvv:vmasked_indexed_alignment` case under
  `out/rvv-masked-indexed-alignment-prefx-20260924-01/` records one unexpected
  trap for a masked misaligned element. Its following unmasked, aligned
  control does not add another trap. The directed ELF lacks an HTIF `tohost`,
  so its standalone Spike timeout is not reference evidence; the frozen
  random Spike trace is the reference for the masked case.
- `hardware/src/vlsu/addrgen.sv` checks `is_addr_error` on every indexed
  address before request issue and has an explicit TODO for masked-element
  misalignment and page faults. Its port list has index operands but no mask.
  `hardware/src/vlsu/vlsu.sv` routes mask data only to VLDu/VSTu. VLDu
  applies it to result byte enables after receiving memory data, too late to
  prevent an address exception or an AXI read.
- `hardware/src/masku/masku.sv` expands each predicate bit into the lane/byte
  mask presented to the target VFU. Its queue entry is retired when VLDu or
  VSTu acknowledges the beat. Indexed operands take a separate AddrGen spill
  register, so the currently visible mask beat and index beat are not
  inherently synchronized. This rules out simply wiring `mask_i` into the
  existing `is_addr_error` condition.
- The MASKU queue entry currently records mask data, per-lane validity and
  target VFU, but not the producing instruction ID or mask-word ordinal.
  MASKU accepts a new predicated instruction only when this queue is empty,
  which prevents overlap of two instructions' queued mask words; it does not
  make the later MASKU issue-head ID a stable tag for words already queued.
  MASKU has no LSU exception-flush input for this queue: queued words are
  removed by the target unit's ready handshake. The VLDu/VSTu early-exception
  completion paths do not themselves acknowledge all remaining mask words.
  A fault followed by another predicated indexed instruction therefore needs
  explicit queue-drain/flush evidence; ID tagging alone does not solve stale
  predicate recovery.
  Observing that AddrGen and VLDu/VSTu happen to carry the same ID in the
  first failing examples does not prove that a MASKU queue head belongs to
  them when several instructions are buffered or after a flush. Reliable
  predicate pairing needs explicit ownership and position metadata (or an
  equivalently proved single-instruction lockstep invariant).
- `hardware/src/vlsu/vldu.sv` advances its indexed result-byte and instruction
  counters only while accepting an AXI R beat and its AddrGen descriptor;
  it applies `mask_q` to the VRF byte enables after that beat. Therefore
  suppressing an inactive element's AR in AddrGen alone would strand VLDu
  waiting for a response. A correct skip path needs an explicit aligned
  element-completion token (or an equivalent synthetic result) that advances
  VLDu without an external transaction. The VSTu side needs the analogous
  no-write completion; neither can be inferred from an absent AXI response.
- VSTu currently consumes source bytes, advances its word/instruction issue
  counters and acknowledges the mask only inside its W-beat issue path, which
  requires an AddrGen descriptor and `axi_w_ready_i`. An inactive indexed
  store therefore needs an explicit path that drains the corresponding source
  element and advances these counters without AW/W/B. The existing VSTu code
  also carries a TODO around mask validity for nonzero `vstart`; that boundary
  must be tested before claiming masked-store correctness.
- Store retirement is separately tied to the AXI B-response path: `commit_cnt`
  and `pe_resp_d.vinsn_done` advance when a prior issue is complete and a B beat
  arrives. An all-inactive indexed store can have no B beat, so a skip-token
  design must also generate exactly one internal instruction-completion event
  once its last element is consumed. It must not borrow a B beat belonging to
  an earlier store or complete before that store's ordered response.
  `store_pending_o` only reports whether the VSTu commit queue is nonempty;
  it does not identify which instruction owns an outstanding B response and
  cannot by itself authorize that internal completion.
  Specifically, the current `axi_b_valid_i` branch accepts every B and marks
  `vinsn_commit` done whenever `commit_cnt > issue_cnt`; the descriptor has no
  instruction ID and there is no per-instruction AW/B balance. An all-inactive
  instruction behind an older active store must therefore not use this branch
  as its completion trigger. A repair needs ordered response ownership (for
  example, AW/B credits associated with the instruction in the issue queue)
  before permitting a zero-AW instruction to retire. The directed
  `run_ordered_store_pair` case exercises precisely this older-B/newer-skip
  boundary, in addition to the all-inactive standalone cases.
- The repository-local `vmasked_indexed_store_alignment.c` was linked with
  the project RVV LLVM toolchain and run on the probe VCS image with a frozen
  ELF and complete VCS image hash check under
  `out/rvv-masked-indexed-store-probe-run-20260924-01/`. Its first masked-off
  misaligned store raised an exception at probe cycle 466. AddrGen then held
  the same indexed address without `idx_ready`, AR/AW or descriptor push, and
  the bounded diagnostic stopped at 120 seconds. This is a failing RTL
  diagnostic, not a passing directed test; the later active-store checks in
  that program were not reached.
- The updated store ELF (SHA-256
  `7338364e8a15ef3549c3f9dd4ecb45448ad84fea92070d5ef67f3af4e652771d`)
  adds an all-inactive `vstart=0` case before the `vstart=1` case. A bounded
  current-image run at `out/rvv-masked-indexed-store-vstart0-current-20260924-01/`
  reached PC `0x800001aa` (`vsoxei16.v v16, (s4), v8, v0.t`) and raised Store
  Address Misaligned with `tval=0x80001306` although `v0` was all zero. The
  run timed out after 120 seconds without completing the trap handler. Its
  frozen `input.elf`, VCS image-file hashes, command, console and commit trace
  are recorded under the run directory. This proves the fault also occurs
  without nonzero `vstart`; later cases in that ELF were not reached.
- A new isolated VCS image with both AddrGen and VSTu mask/issue-ID probes
  ran the same frozen ELF for 25 seconds at
  `out/rvv-masked-indexed-store-id-probe-20260924-01/`. In this run both
  units carried instruction ID 0. At probe cycle 473, AddrGen issued AW and
  a descriptor for the first all-inactive element at `0x80001300` while the
  VSTu mask input was not yet valid. At cycle 475, AddrGen raised the
  misaligned exception for the second element at `0x80001306`, exactly when
  VSTu first saw a valid all-zero mask input (`0011:00000000`); its mask
  spill register was still invalid. Therefore a fix must suppress both the
  premature masked AW and the fault, not just the exception signal. The
  timed-out run is diagnostic evidence, not a passing test.
- The same probe image ran the updated directed load ELF (SHA-256
  `2fbd54b8cf612f93f69ffda2cf59dcc01e6287c0fe485f965c15d305c9b0f502`)
  at `out/rvv-masked-indexed-load-id-probe-20260924-01/`. For the all-inactive
  `vstart=0` case, AddrGen issued AR for the first element at cycle 459 before
  VLDu had a mask. At cycle 461 it raised a load-address-misaligned exception
  for the second element just as VLDu received an all-zero mask input. The
  directed test reported a trap where none was allowed and terminated FAIL
  (`tohost=3`). The same run also recorded a false exception in its
  `vstart=1` masked case. Both read and write paths need pre-address predicate
  pairing and a no-memory completion path.
- A separate 120-second bounded MASKU queue probe used the frozen store ELF
  (SHA-256 `7338364e8a15ef3549c3f9dd4ecb45448ad84fea92070d5ef67f3af4e652771d`)
  under `out/rvv-masked-indexed-mask-queue-probe-20260924-01/`. At cycle 473,
  AddrGen issued AW for the first all-inactive element at `0x80001300`; at
  cycle 475, it raised a misaligned exception for the next all-inactive
  element at `0x80001306`. The MASKU queue trace shows one valid store mask
  word at the fault, but does not show it persisting afterward. This run
  timed out and did not reach a following predicated instruction. It confirms
  premature AW and false fault, not stale-mask reuse after recovery.
- The focused bound probe in
  `out/rvv-masked-indexed-probe-run-20260924-02/probe.log` reproduced the
  masked fault with a frozen ELF and complete copied VCS image hashes. At
  probe cycle 459 AddrGen held the misaligned indexed address
  `0x80001206`; at cycle 460 it asserted the exception. The corresponding
  VLDu mask beat appeared on its input at cycle 461 and in its spill register
  at cycle 462. In the aligned active control, AR and descriptor push occurred
  at cycle 3819, while its VLDu mask arrived at cycles 3821-3822. Both cases
  show the address decision precedes mask availability by approximately two
  cycles. A direct connection to either the raw MASKU signal or the VLDu mask
  spill output cannot provide a valid predicate at the current AddrGen
  decision cycle.
- A separate unmasked indexed-store test isolates exception restart position
  without using the still-broken masked path. On the pre-fix VCS image,
  `vindexed_fault_vstart` traps at the correct address with cause 6, but
  reports `vstart=2` for element 1 when starting at 0 and `vstart=0` for
  element 1 when starting at 1. The expected restart element is 1 in both
  cases. Frozen evidence is under
  `out/rvv-indexed-fault-vstart-before-20260924-01/`. The misaligned-address
  calculation in `addrgen.sv` used `>> axi_addrgen_q.vew - 1` without adding
  the initial `vstart`; this is a separate precise-exception bug, not a fix
  for masked-off access suppression.
  The earlier `out/rvv-masked-indexed-probe-run-20260924-01/` is excluded:
  its wrapper copied `simv` without `simv.daidir`, so the simulator did not
  start. The corrected run freezes and checks both the launcher and image.

The separate unmasked indexed `vstart` defect is now fixed in `addrgen.sv`:
the exception restart element is computed from the original `vl` and the
remaining indexed element count, matching the existing MMU exception path.
The exact directed ELF (SHA-256
`6434f4763600555ab5f9d59df4ddbedf3c73b7068a65f53cbc906ce1b73b5f7c`)
reported restart positions 2 and 0 on the old image, then 1 and 1 on the
new isolated VCS/UVM image. Independent trace audits PASS for the directed
case (`out/rvv-indexed-fault-vstart-after-20260924-01/`) and existing indexed
and unit-stride `vstart` edges. Representative frozen QBS/AKV runs also PASS
their UVM self-checks on the new image. This does not repair the masked-off
indexed load/store fault described in this document.

The store-only check did not cover an earlier active indexed *load* element
followed by a misaligned element. After adding both load restart cases to the
same test, the first load trapped with `vstart=1` but retained its original
element 0, and a subsequent load observed a stale R beat. The bounded
`ARA_PROBE_VLDU_FAULT_ORDER` run under
`out/rvv-indexed-load-fault-order-probe-20260924-01/` recorded a valid
descriptor for the first AR at `t=10080000`, `addrgen_illegal_load=1` at
`t=10090000` while R was absent, and VLDu exception states 1/2/3 at
`t=10100000/10110000/10130000`. The descriptor was popped in state 3
without its R beat. This is distinct from the masked-off fault: it violates
the [RVV precise-trap requirement](https://github.com/riscv/riscv-isa-manual/blob/main/src/unpriv/v-st-ext.adoc)
that result elements preceding `vstart` have committed.

VLDu now latches the early AddrGen illegal/misaligned-load indication and
delays its exception-drain FSM until earlier AddrGen descriptors have been
consumed with their R responses. Normal load issue is unchanged. The expanded
four-scenario test (indexed load/store, initial `vstart` 0/1) has ELF SHA-256
`4aeb6dc0b948413468910c00f2337af14f42162662e58fe31f858509851d5e69`.
It PASSes on the isolated new VCS image at
`out/rvv-indexed-fault-load-store-fixed-20260924-01/`, with an independent
trace audit. The same image PASSes indexed and unit-stride `vstart` edges and
frozen QBS/AKV UVM representative runs. This is focused evidence for precise
unmasked faults, not signoff for masked indexed accesses or all fault orders.
The subsequent six-scenario version also checks load and store faults at
element 0, where no earlier AXI response exists. Its frozen ELF SHA-256 is
`94e3f5b686fbc6977d7b17c2c8b3eff26b7baa5a159869b14937b6182a1ecce7`;
`out/rvv-indexed-fault-sixscenario-fixed-20260924-01/` PASSes with independent
trace audit on the same fixed image.
The seven-scenario version adds an indexed load whose first two elements are
valid and whose third element faults. It checks that both prior results commit,
the third destination remains unchanged, and the trap reports `vstart=2`.
The frozen ELF SHA-256 is
`fb131ae7741ef3757b6eff8ea011c98539c643277d72ccebdd2b7b8af943b1ad`;
`out/rvv-indexed-fault-seven-scenario-20260924-01/` PASSes on the same image
with an independent trace audit. This strengthens the outstanding-response
ordering evidence but does not cover masked-off indexed accesses.

## Required behavior

For an indexed load/store, each element's predicate must be known before
address alignment checking, MMU translation and AXI request issue. An
inactive element must consume its index position without generating an MMU
request, AXI request or exception. A masked store must not update memory; a
masked load's destination must obey mask-undisturbed/agnostic policy. Active
elements retain current ordering and exception
behavior; unmasked instructions must retain their existing fast path.

`vstart` is part of the alignment contract. The first predicate consumed
must correspond to the first element that AddrGen processes, not blindly to
element zero. A mask beat may cover several elements; consuming one index
must not prematurely acknowledge the whole mask beat. Instruction flush and
exception recovery must discard only this instruction's pending predicates,
so a following indexed instruction cannot inherit stale mask bits.

## Implementation boundaries to check before RTL edit

1. Trace the sequencer's mask production and ready/valid handshake through
   `ara.sv`, `vlsu.sv`, and the VLDu/VSTu spill registers. Determine whether
   an indexed instruction's mask beat arrives before or after its index beat.
2. If AddrGen receives a predicate stream, preserve atomic multicast to
   AddrGen and VLDu/VSTu: one consumer must not accept the same MASKU queue
   beat twice while waiting for the other. The existing MASKU acknowledgment
   is controlled by VLDu/VSTu alone. A private AddrGen predicate FIFO needs
   explicit acceptance accounting, backpressure and flush handling. A
   combinational tap on `mask_i` alone is not sufficient because index and
   mask beats are independently buffered.
   A narrower candidate is to expose the VLDu/VSTu mask spill-register output
   and its issuing instruction ID to AddrGen, but the measured two-cycle lag
   requires AddrGen to wait for the matching beat before deciding each indexed
   element. This avoids consuming a raw MASKU beat twice; it still requires
   proof that flush cannot make the ID or position stale. Static inspection
   shows MASKU retires a load/store mask queue beat on the corresponding
   VLDu/VSTu ready handshake. That handshake can mean acceptance into the
   downstream mask spill register, before the result/source word completes.
   Thus the MASKU queue head is not held until AddrGen classifies every
   element and cannot serve as an untagged predicate lookup.
3. Use the data EEW and existing lane shuffle convention to select a mask
   element, including nonzero `vstart`. Confirm this against the load/store
   result-byte mask mapping before using it for address suppression.
4. For inactive elements, advance the indexed remaining-length, lane/element
   pointers and completion bookkeeping exactly once without enqueueing an
   external AXI transaction. Deliver an explicit skip/completion indication
   to VLDu/VSTu so their own issue and commit counters advance without
   waiting for a response that will never arrive. Prove that a masked load
   preserves the destination policy and a masked store does not write memory.
5. Test both translated and untranslated accesses. The existing MMU request
   condition uses `idx_vaddr_valid_q`; it must also exclude inactive elements,
   including same-cycle DTLB hits and later page-fault responses.

## Candidate handshake contract (not yet implemented)

The smallest coherent interface is one predicate decision per indexed element,
not one global `vm` bit per instruction. AddrGen may consume an index only
after the predicate for the same instruction ID and absolute element number is
available. MASKU currently lacks ID/word tags on its output queue, so adding
those tags is part of this candidate, not an existing property. The
mask-producing side must retain its current word until all
elements of that word required by AddrGen are classified; the VLDu/VSTu side
must still receive that word exactly once. A word counter or equivalent token
is necessary because the mask and index streams have independent buffering.
The current probe proves matching issue IDs in the first failing load/store
examples, not in every queued or flush scenario.

The VLDu and VSTu spill registers hold a mask word until their corresponding
result/source word completes. This is a possible predicate source for AddrGen,
but only if its ownership and absolute word position are latched when the
spill accepts the MASKU beat. The issue-head ID alone is not an ownership
tag: the spill can accept the next word while the previous word is released,
and a flush can invalidate one side of the pairing. The selected predicate
must be checked against AddrGen's absolute element index (derived from `vl`
and remaining indexed length) before alignment or MMU work. The first
partial word after nonzero `vstart` and an index EEW different from data SEW
must be explicit pairing tests.

For ordinary predicated memory instructions, MASKU initializes `read_cnt` to
`vl - aligned(vstart)` and decrements it by one cross-lane data word each time
it enqueues a predicate word. Consequently, at enqueue the expression
`vinsn_issue.vl - read_cnt_q` identifies that word's absolute first element,
including a nonzero `vstart`. Pairing this value with `vinsn_issue.id` is a
candidate ownership tag for the mask queue entry; it must be latched with the
entry, not recomputed from the later commit counter. This relation is specific
to the predicated memory path and still needs cycle-level checks for partial
first/last words, queue backpressure, ID reuse and exception flush.

For an active element, keep the existing alignment, MMU, AR/AW, descriptor,
R/W/B, and exception paths. For an inactive element, consume one index and
one predicate bit, advance the remaining length once, and enqueue an ordered
internal skip token rather than an AXI request. That token must identify the
instruction and element so VLDu/VSTu can advance their result/source and mask
word counters without waiting for a nonexistent R/W beat. A load skip cannot
write a masked-undisturbed destination byte; a store skip cannot assert AW/W,
including an all-zero-strobe W beat. Translation and fault checks must be
guarded by the same active predicate before they observe the address.
The current AXI request FSM enters its per-element body only when the AXI
AR/AW ready input is asserted. A skip must bypass this ready gate while still
respecting descriptor-FIFO capacity and older-operation ordering; otherwise
an all-inactive operation could stall indefinitely behind an unrelated AXI
backpressure condition. VLDu must not consume an AXI R beat against a skip
descriptor. VSTu may still need to accept a B beat for an older active store;
that response must be attributed to the older store, not to the skip token.

The final skip token of an all-inactive store needs one ordered internal
completion after older stores' B responses, not an invented B response or a
completion triggered by an older store's B. Flush must cancel unmatched
predicate and skip tokens for the faulting instruction while preserving older
transactions. Assertions should enforce: no MMU/AR/AW/exception for a skipped
element; exactly one index and completion advance per element; no instruction
ID/word-index mismatch; and no store completion ahead of an older B response.
VSTu's current commit path is entered on `axi_b_valid_i` and tests only whether
an instruction has finished issuing (`commit_cnt > issue_cnt`); it does not
carry an AW/B count per instruction. Consequently, the skip path must not
reuse this condition to complete an all-inactive store: an older B beat could
otherwise retire the wrong instruction. A safe implementation needs an
explicit ordered completion marker or equivalent per-instruction outstanding
write accounting, validated with an older active store followed by an
all-inactive indexed store.
At the skip handshake, VSTu must consume one element's source position and
decrement its issue-byte budget, yet acknowledge the lane source and mask
words only at the same word boundary used by an active element. Its current
source-consumption block is gated by a valid AddrGen descriptor and AXI W
readiness, so both gates need a distinct internal skip path. A skip must not
become an all-zero-strobe W: that would still create an external write and a
B response. For stores with both active and inactive elements, retirement
must wait for all actual writes of that instruction; an all-inactive store
needs an ordered internal retirement after older B responses, exactly once.
Because MASKU's queue has finite depth, a later mask word may be unavailable
until VLDu/VSTu consumes an earlier one. For an inactive earlier element, its
skip token must make that consumer advance without waiting for AXI. Otherwise
stalling AddrGen for the later predicate can itself create a circular wait.

## Discriminating probes and regression

Capture a bounded window of: current vector instruction ID, `vm`, `vstart`,
index beat valid/ready, mask beat valid/ready, selected predicate and element
number, `idx_final_vaddr_q`, `idx_op_cnt_q`, `axi_addrgen_q.len`,
`idx_op_error_d`, `mmu_req_d`, AR/AW valid/ready,
`axi_addrgen_queue_push`, `addrgen_exception_o`, and VLDu/VSTu completion.
The masked element must advance once with no translation/request/exception;
the following active element must still issue and finish.
The bound probe source includes AddrGen instruction ID plus the VSTu issue ID,
predicate input, spill-register valid/data and mask-ready handshake. Its
updated VCS image was compiled in an isolated `sim_dir` and produced the
store-side timing evidence above. The older probe image predates these fields.

After the focused seed and directed case pass, run masked indexed load and
store with active/masked misalignment, page faults, `vstart=0/1`, mask-word
boundaries, multiple lanes and an exception flush followed by a new indexed
instruction. Then rerun representative unmasked indexed, unit-stride,
segmented and QBS/AKV real-model cases on the same candidate image. Keep
each result and simulator/input hashes in an independent output directory.
The repository-local load and store tests cover masked-off misaligned accesses
with `vstart=0` and `vstart=1`, plus a mixed two-element instruction with an
active aligned element followed by a masked-off misaligned element. The store
test also covers an active aligned store and an active misaligned store with
cause/address checks. It now additionally places an ordinary active `vse64.v`
immediately before an all-inactive `vsoxei16.v`, with no intervening fence,
then waits for Ara idle and checks both destination words. The project LLVM
disassembly shows these stores at adjacent vector-operation sites
(`0x800003ae` and `0x800003b6`, separated only by mask setup). Both updated
programs compile with the project LLVM;
their mixed cases are not yet functional passes on the unfixed RTL. The frozen
failing load and store ELFs above predate these added cases.
Masked cases must pass before the later cases can be treated as measured.
Both directed programs now also exercise `vl=8, vstart=4`: one all-inactive
indexed instruction and one with only element 4 active. The other index
offsets are deliberately misaligned. This distinguishes an off-by-one or
first-word-only predicate pairing from a correct cross-word implementation.
The updated programs compile with the project LLVM toolchain. Their ELF
SHA-256 values are `c529532c202c4b1fbcfad81b3408122c225356cbb1ada5a93699f607f475d93a`
(load) and `8e26f403e5136aeb7f499ab1989928681d2a7f0b18ba4e7cc35c8cc205fab5f0`
(store). Disassembly contains the intended `vsetvli`/`csrw vstart`/indexed
operation sequences.

## Isolated candidate evidence (2026-09-24)

The candidate is confined to `ara_dsa_masked_indexed_fix`; it has not been
merged into the verification branch. Its VCS image passed the directed
`vmasked_indexed_alignment`, `vmasked_indexed_store_alignment`, and
`vindexed_fault_vstart` tests. The first two include the cross-word and
older-active-store cases described above. Their independent trace-integrity
audits passed. Full architectural-state comparison is not implied by these
directed tests.

The frozen random seed-76 replay moved its first scalar mismatch from index
401 (`0x800005c2`, masked indexed load) to index 949 (`0x80000dac`, unmasked
indexed load). The former now retires in the RTL trace. At index 949, Spike
logs the faulting vector instruction with `vstart=1` before entering the trap
handler; RTL reports a CVX exception and enters the handler without a retire
row for that instruction. The handler reads `mepc=0x80000dac` and `mcause=4`.
The old commit comparator therefore reported `pc_or_instruction` against the
first handler instruction. An exception-aware comparison now requires the
explicit RTL exception PC, a vector instruction without a logged architectural
write, and agreement between Spike's next PC and the RTL handler PC before
aligning one fault record. The handler's `mepc` and `mcause` reads and all
following scalar commits remain subject to normal exact comparison. On the
saved seed-76 logs this yields `TERMINAL_MATCH` for all 3175 non-trap RTL
commits and the expected terminal `ecall`, without rerunning simulation.
The trapped load has four VRF write events, but every event has byte-enable
zero, so it changes no architectural vector byte. The vector comparator now
accepts a trapped request as a verified zero-write exception only when the
scalar comparison has independently aligned its fault record, all its uops
complete, and every VRF write strobe is zero. A nonzero-strobe trapped write
still leaves the comparison at `PREFIX`. The exception-alignment rules have
unit tests for missing proof, wrong handler PC, wrong `mepc`, and nonzero VRF
strobe. On the saved logs, vector comparison covers 201 destination requests
and 13,787 bytes with no mismatch. A fresh replay of the frozen seed-76 ELF
using the same candidate VCS image reports `PASS`, and the independent audit
with `--require-trace --require-vector` reports `PASS` at
`verification/out/masked-indexed-fix-seed76-signoff-audit-20260924-03.json`.
This is a strict destination-write check, not an all-register checkpoint after
every vector instruction; the stronger `--require-full-match` policy remains
unsatisfied by this test profile.
The separate ten-case replay at
`verification/out/masked-indexed-fix-slide-10seed-real-20260924-01/`
uses a different seed-76 ELF: its SHA-256 is
`0191c44b139f51cb31ab48434746e9b5b112c401860d2f0a7aea4b5a1e2c5d93`,
whereas the standalone signoff ELF hashes to
`d04011508848dcadbf90da38729e9d1192a3ababe91b0c467e1cbf8fa428dc3a`.
The batch seed-76 case stops at `INCOMPLETE_PREFIX` after 1197 matched
instructions because a vector-to-scalar result is architecturally
unobservable to its checker. The standalone `PASS` does not sign off the
batch ELF or turn that prefix into a terminal match.
The visible one-bit scalar difference is propagated by `vmv.x.s` from v11.
Walking backward through the archived vector writes finds the same bit in
v18, v31, v13, v3, v27, and v19; the `vmsbc.vvm` at `0x80000cca` already
sees a divergent v7 source. Therefore the later reduction and register
moves are not evidence that their arithmetic is faulty. The accepted-write
comparator had stopped even earlier, at an unobservable write at
`0x8000082a`, so this trace does not establish the first defined-state
divergence. A separate known-input e64/m1 `vmsbc.vvm` test explicitly sets
v8=3, v7=-18 and v0 bit 0=1, checks the borrow result and all tail bits,
and passes VCS plus independent trace audit at
`verification/out/masked-indexed-fix-vmsbc-e64-known-audit-20260924-01.json`.
This narrows the investigation but does not turn the batch case into a PASS.
The completed ten-case replay has nine `TERMINAL_MATCH` and vector-write
`PASS` cases (seeds 71-75 and 77-80). Seed 76 remains
`INCOMPLETE_PREFIX`; the independent batch audit at
`verification/out/masked-indexed-fix-slide-10seed-audit-20260924-01.json`
reports 9 passed, 1 failed for exactly that result status. It found no
additional evidence-integrity failure. This profile's original frozen batch
is therefore 9/10, not 10/10.
After adding an explicit frozen-input replay option and including the active
indexed-fault test in the masked-indexed suite, the candidate verification
Python suite passes as a whole: 829 tests passed and 53 were skipped in the
isolated worktree. The replay selector rejects an empty case set instead of
reporting a vacuous PASS.

A further store test places a faulting active `vsoxei16.v` immediately before
`vse64.v` in the instruction stream. The rebuilt ELF hash is
`d6424c66d72d9c85b42dbe56aa40ef4a8ce90ac306c6231924d39e3893115a0b`;
the two instructions are adjacent at `0x80000412` and `0x80000416`.
The independent VCS run and trace audit passed, including the expected store
fault and the memory effect of the following store. Cycle evidence shows that
the second store was accepted after the handler returned, not while the first
store was still faulting. Thus this test verifies exception recovery but does
not establish the behavior of an already-queued younger store. Static
inspection of `ara_sequencer.sv` shows that a memory request enters `WAIT`,
holds `ara_req_ready_o` low, and returns to `IDLE` only after AddrGen and the
operand/mask consumers have acknowledged that same request. Thus the normal
sequencer cannot accept a younger store while the faulting store is awaiting
AddrGen; older stores may still occupy VSTu, and its `commit_cnt == 1` gate
waits for those predecessors to drain. This is an interface-level ordering
argument, not a standalone VSTu test against an adversarial producer that
queues a younger store. That case must be tested separately if VSTu is reused
behind a producer with a different acceptance contract.

The three-case fast UVM gate was accidentally run with the ordinary VCS image,
which does not emit the UVM/contract summaries required by that gate. All
three checks failed for missing summaries; they are not functional failures
of the RVV, QBS, or AKV programs. Rebuild with `verify_uvm_cvxif=1` and the
UVM monitor sources before using this gate as regression evidence.
That corrected 1 MiB UVM image has since been built. The ordinary RVV
`vfredmax_boundary`, Qwen2.5 QBS `decode_attn_q_qbs_direct2`, and AKV handoff
smoke cases all report `PASS` with zero UVM issues under
`verification/out/masked-indexed-fix-uvm-gate-20260924-01/`. This is a
three-case representative gate, not a complete RVV or model-level regression.

The combined Qwen2.5 QBS+AKV capture exceeds the standard 1 MiB simulated
L2 by about 989 KiB. It links with the existing simulation-only 2 MiB L2
setting; the frozen ELF is
`verification/out/masked-indexed-fix-real-qwen25-2mb-20260924-01/input/llama_qwen25_small_qbs_akv.elf`
with SHA-256 `201b2ef8720f1cecb9e7e1dac405079e98a6798c8cc56e40db0bf57931f585d3`.
A matching 2 MiB UVM/VCS image and real-data replay completed. The real
Qwen2.5 QBS+AKV result at
`verification/out/masked-indexed-fix-real-qwen25-2mb-20260924-01/uvm/uvm_result.json`
is `PASS` with no UVM issues. It records 3,532 CVXIF requests and responses,
3,155 backend allocations and completions, 278 completed AXI reads, and 191
completed AXI writes. The input ELF SHA-256 is
`201b2ef8720f1cecb9e7e1dac405079e98a6798c8cc56e40db0bf57931f585d3`;
the UVM simulation image SHA-256 is
`e585e12e35d80ac0c45d3437a1fc5b7c4c787809011efd4728f0d5ce10dae4ff`.
This validates one real-data combined path, not the complete model or all
QBS/AKV shape and format cases. The 2 MiB setting is simulation-only and is
not used by synthesis.
The archived `INPUT_SHA256SUMS` and `RUN_SHA256SUMS` both verify. Rerunning
the UVM checker on the archived VCS log and vector trace, without rerunning
simulation, writes
`verification/out/masked-indexed-fix-real-qwen25-2mb-20260924-01/uvm_reaudit.json`
and again reports `PASS`. All result fields match the original report after
normalizing the absolute versus relative paths used as keys in the simulator
image-hash map; the image-hash values themselves match exactly.

The independent real-DUT UVM bin collector accepted the three 1 MiB
representative runs and the 2 MiB real-data run without evidence errors, but
reported `INCOMPLETE` at
`verification/out/masked-indexed-fix-uvm-diagnostic-20260924-01.json`.
The best single image covers 20 of 24 defined bins. The remaining bins are
AXI AR/AW backpressure and reset aborts of in-flight reads/writes. Existing
ordinary runs do not inject those conditions; they must be exercised on the
same final RTL/image configuration with explicit AXI delay and reset stimuli.
The 2 MiB real-data run does cover allocation and completion of QBS and all
four AKV instruction classes. No UVM coverage-closure claim is made yet.

A new 2 MiB UVM image enables the three-cycle AXI input delay on the same
candidate RTL. Its compile-time source manifest covers 454 files and passes
the post-compile hash check at
`verification/out/masked-indexed-fix-uvm-delay2m-20260924-01/sim/vcs_source_manifest.json`.
Three frozen-ELF runs on that one VCS image passed independent log/trace
rechecks: the Qwen2.5 QBS+AKV case, a read-in-flight reset, and a
write-in-flight reset. The reset cases each observed one aborted transaction
of the requested kind. Their archived run hashes verify. The independent
collector reports `PASS`, 24/24 planned UVM protocol/activity bins, one
common simulator image, and zero evidence errors at
`verification/out/masked-indexed-fix-delay2m-uvm-3case-20260924-01.json`.
The repository's independent `uvm` signoff gate also reports `PASS` at
`verification/out/masked-indexed-fix-delay2m-uvm-signoff-20260924-01/signoff.json`.
This supersedes the 20/24 diagnostic above for UVM protocol coverage only;
it does not close DUT code coverage, all RVV instruction cases, or Linux boot.
