# Nonindexed masked translation: independent static review

Reviewed 2026-10-10 PDT (source/hash checkpoint 2026-10-11 03:20 UTC).
Read-only RTL/evidence inspection; this Markdown file is the only new artifact.
No RTL edits, builds, Linux boots, simulators, reference executions, or board runs.
No sealed inputs, helpers, or running-pipeline files were modified.

## Verdict and evidence level

The current source still has a reachable nonindexed translation/exception path
that does not inspect the architectural predicate. With a legal accepted
`vle16.v v24,(a0),v0.t`, VL=8, vstart=0, v0=0, aligned protected-page base,
translation enabled, queue space and AXI address readiness, AddrGen requests
translation. An MMU page-fault response is forwarded as an architectural
exception, not suppressed by the zero predicate.

This is a source-level counterexample with explicit interface assumptions,
consistent with a hash-bound historical board failure. It is NOT a newly
measured failure on the current RTL/image. Actual current request timing,
MMU response and trap/cleanup must be measured before claiming reproduction.

The existing fixes to FOF forwarding, internal terminal markers and VLDU beat
retirement do not implement nonindexed predicate suppression. Conversely,
their presence means the historical FOF/cleanup failures must not all be
reported as unchanged. Indexed inactive-element skip already exists and is
outside this nonindexed finding.

## Scope and source identities

Path abbreviations:

- I = `/home/wangwy/openproject/ara_dsa_signoff_integration`
- C = `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`
- R = `/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix`
- S = `C/rvv_small_exceptions01`
- E = `C/rvv_exception_symptoms02`

Scope authorities read: `I/verification/fpga/current_board_review/remaining_scope.md`
(section "Masked VLSU Translation and FOF") and
`R/repro/ALL_FAILURE_REVIEW.md:31,42,63`. The latter separates 8 protected-page/FOF
ELF records, 429 unit/strided/segmented replay records, and kernel cleanup
stalls. These counts are not counts of independent bugs. This review does not
close those families, indexed NF7, signal-handler replay or segment boundaries.

Worktree HEAD: `7d5d1829ff68baa223618a54807e6a2b4e2c9373`, with other agents'
changes present. References below are to the inspected current files, not the
FPGA source mirror. SHA256 values were recomputed, not copied from filenames.

| File relative to I | SHA256 at inspection |
|---|---|
| hardware/src/vlsu/addrgen.sv | a339e5fe0c96728e4e97e21139b03649121a6c37ba765a4ee62f261c7e14f988 |
| hardware/src/vlsu/vldu.sv | 5700da41de5b85998b3feba441a4bddda0645b4f0f00f04927baedeb0899f07c |
| hardware/src/vlsu/vstu.sv | 139b27c0784c867b7a6032665c1634bb4b843ec2d9be5c4a3c6cb6d8fd2919f2 |
| hardware/src/vlsu/vlsu.sv | 9e620fb98efe420ff01ff9919461565b3c65a53bc518dc2f6cdb5f8241cf3ba2 |
| hardware/src/ara_sequencer.sv | 601165e265b57fe8a42188e1f7d9c7bbcaa78b6c21f65c6fad09d0837563da2f |
| hardware/src/ara_dispatcher.sv | 4eda3df195e1a8ec319e51a14df1a051964cd08f6ee10335145a7c10cc89db4d |
| hardware/src/ara.sv | 1d190744249603d6c3d6e2c9c21cd5ac121fee2a9c65f5b227be239c320286da |
| hardware/src/masku/masku.sv | 1bc71bbb732a842d59fdcc48d4f44aa79f830f2bb11444923b15910b8d875f3d |
| verification/fpga/current_board_review/remaining_scope.md | 7c843a72b1b13dffe11caf29decfaa36306587bd77d913b8dc20a26c399665a5 |

`R/repro/ALL_FAILURE_REVIEW.md` SHA256:
`c72e20fc1f85d6ca670c9b182dac85bf366c141dbe79d890e57f71282a54caaf`.
This checkpoint is not a replacement for pipeline pins; mutable files must
be rehashed before an execution is attributed to this review.

## Request, predicate and completion reconstruction

1. **Decode does not inspect v0.** `ara_dispatcher.sv:4138` copies instruction
   vm and scalar address into the backend request; ordinary unit stride is
   decoded to VLE at 4196, FOF sets its separate bit at 4208. Architectural
   `vm=0` means predicated execution, not virtual-memory enable.
2. **No-active-length is not all-mask-off.** At `ara_dispatcher.sv:5949`,
   `vstart>=vl`, mask-memory no-op, or null slide can suppress the backend
   request and generate a load/store completion. `mask_mem_noop` for `vlm/vsm`
   is a length condition, not an OR of v0. VL=8/vstart=0/v0=0 takes no such
   shortcut. Do not inject VL=0 directly into AddrGen to test a dispatcher
   contract: its length subtraction assumes an accepted body.
3. **Request acceptance waits for consumers, not predicate values.**
   `ara.sv:348` broadcasts masked requests when lane and MASKU requesters are
   ready. `ara_sequencer.sv:849` marks MASKU running when vm=0. Its
   `memory_mask_accepted` at 967 is instruction-request acceptance, not mask
   data availability and not any-active. This provides no all-zero filter.
4. **Mask data exists, but AddrGen only uses it for indexed requests.**
   `masku.sv:1178,1204,1248` expands predicate bits into byte strobes and sends
   target FU, owner ID, first element and per-lane validity. VLSU routes the
   load/store spill outputs back to AddrGen (`vlsu.sv:242`). VLDU's flushable
   spill (`vldu.sv:98`) and exports at 114 preserve those metadata; its
   input-valid test at 122 tests valid bits, not the predicate payload.
   Zero payload is therefore a valid mask word, not missing operands.
5. **Nonindexed descriptor is predicate-independent.** AddrGen accepts the
   request at `addrgen.sv:309`; ordinary/strided requests enter ADDRGEN. At
   370 it forms base plus vstart (or vstart*stride), remaining byte length,
   EEW, burst/type and FOF fields without consulting mask. With translation
   enabled it moves to WAIT_LAST_TRANSLATION at 405 while the AXI generator
   takes the descriptor. For the focused example len=16, not zero.
6. **Indexed protection is real but narrowly gated.** At `addrgen.sv:620`,
   predicate lookup requires ADDRGEN_IDX_OP, correct owner, covered element
   position, and selected lane valid. The element is `vl-(len>>vew)`; byte
   expansion and shuffle select its bit. At 920 an inactive indexed element
   emits an `is_skip` descriptor without MMU/AR/AW traffic and advances length.
   Nonindexed ADDRGEN/WAIT_LAST_TRANSLATION cannot take this path.
7. **Translation starts without a nonindexed predicate check.** At
   `addrgen.sv:939`, `state_q != ADDRGEN_IDX_OP` bypasses the predicate gate.
   Remaining conditions are compatible queued channel, queue not full and
   AR/AW ready. At 1135 it sets `mmu_req_d=1` for virtual translation, with
   `mmu_vaddr_o=axi_addrgen_q.addr`. The observable request is
   `mmu_req_o=mmu_req_d & ~mmu_valid_i` at 757. Thus count request episodes,
   not every asserted cycle, and do not infer absence from a response cycle.
8. **Permission failure is not hidden by downstream BE=0.** At 1213 an MMU
   exception is registered, an exception descriptor is queued, and address
   generation ends. At 525 WAIT_LAST_TRANSLATION acknowledges and forwards
   the exception/FOF status. Sequencer at 1010 waits for remembered AddrGen
   ack plus consumer acceptance before responding; dispatcher at 4356
   forwards ordinary exceptions and enters masked-load cleanup. There is
   no predicate check along this exception return path.
9. **Load/store predication occurs too late to protect translation.**
   `vldu.sv:350` consumes either actual R data or a skip descriptor; at 420
   it predicates VRF byte enables. `vstu.sv:448` predicates WSTRB after an
   address descriptor exists. Zero VRF BE or WSTRB cannot undo a page fault
   which prevented the address transaction. Nonindexed stores share the
   unguarded gate, but this review's historical matched example is a load.
10. **A no-access repair must also retire.** VLDU consumes skip descriptors
    without RVALID, but normal all-off nonindexed requests currently receive
    no skip token. Simply suppressing `mmu_req_o` would strand AddrGen and
    the load/store/mask consumers. Simply suppressing the architectural trap
    would also not establish correct length, VL, mask draining and completion.
    Terminal marker handling at `vldu.sv:606` drains results, acknowledges the
    marker and asserts load_complete/current-burst-exception at 631. Those
    are exception recovery actions, not an implemented all-off success path.

## Existing fixes versus remaining gap

Direct deployed/current diffs were inspected. Deployed AddrGen comes from
`C/rvv_verification_handoff02/deployed_rtl/addrgen.sv`, SHA256
`abbdabe6a9d13cc81ad27ffa38f0149ec9c8f9f3b0383bf142b7d9987da5d2ac`.
Deployed sequencer and VLDU were read from the original project's FPGA mirror
only after their hashes matched `C/rvv_stall_archived_rtl/manifest.json`,
`source_hashes_before_integration`: sequencer
`acf333e10d5b143cddb5bf037e55067bde4f3d644cb01ea4a8e82525c0f97454`, VLDU
`2661d1d5bd22ad95825c38be679622d7bae987deae743e12d1fadfe7c3b0af0d`.

| Mechanism | Current source disposition |
|---|---|
| PE FOF bit | Fixed forwarding at ara_sequencer.sv:796; deployed omitted the field. |
| Nonfirst FOF terminal marker | Fixed at addrgen.sv:1234: always enqueue internal exception marker, even if dispatcher suppresses architectural trap. This is the ONLY deployed/current AddrGen diff. |
| VLDU descriptor retirement | Fixed at vldu.sv:481: compare consumed current beat index inside beat-consumption block, including skips without RVALID. |
| Nonfirst FOF architectural response | addrgen.sv:1238 uses `vl != len>>vew`; dispatcher.sv:4363 suppresses trap and changes VL. This is not a predicate test. |
| All-off ordinary/FOF first page | Still unguarded. At VL8/vstart0/len16/EEW16, `vl == len>>vew`; even with FOF set, no nonfirst suppression is selected. |
| Indexed inactive element | Existing owner/position-qualified skip path, not newly repaired by these FOF changes. |
| Linux replay/cleanup | Not closed by the above. Track marker drain, running IDs, flush and CSR acceptance independently. |

The frozen final02 AddrGen at
`/home/wangwy/fpga_runs/current_board_integration_final02/frozen/sources/hardware/src/vlsu/addrgen.sv`
rehashes identically to current AddrGen. This alone does not certify full image
equivalence or a current execution result.

## Real source and ELF provenance

Original source `R/exception_oracle.c` hashes to
`af36b5d8475b2949e09957ad742bbb863d0b5a59c5cf9cd959edc2dc6bc86794`, matching
`C/rvv_exception_detail01/manifest.json`. That manifest hashes to
`dbbdee659eb0b9820ef09d83d45e11c93bf721f6941d3f9ff3e957fc3beeb8bc`.
Original assembly `C/rvv_exception_detail01/rvv_exceptions_detail_e16.S`
is hash-identical to the reduced scenario.S below.

| Artifact | Recomputed SHA256 |
|---|---|
| C/rvv_recovery08_202/resume/binaries/rvv_exceptions_detail_e16 | d7f8507da5afaf4c4683bb5b35861f6f99cd71bcbf06f6622a791d9786c55923 |
| S/rvv_exceptions_detail_e16.original.elf | d7f8507da5afaf4c4683bb5b35861f6f99cd71bcbf06f6622a791d9786c55923 |
| S/binaries/rvv_small_exceptions_e16_scenario3 | 9de2343469ad5bd8d5c7ac817bed69ba2d9847bc29f2426a6b817f343b08651c |
| S/rvv_small_exceptions_e16_scenario3/scenario.c | 45a6c005b92933c0cf3315d7ae08dc27377ca51c54df30c291be79bb4495ed03 |
| S/rvv_small_exceptions_e16_scenario3/scenario.S | 2d75fc09a289e319c2e58fc812748f9030e6ccd2f864753b10d874535d489376 |
| S/manifest.json | c6d7c465085cf029c57136a7b09e79d3c232e3db2582dcfba3b2f4254b60b26c |
| R/repro/reduce_exceptions.py | 8083f974895d1401f4c8a3830f4565fe9a6415f941d3206250fa0ead7f2631ec |
| E/original_report.json | e788df451d0c97a9475fe1808a4685fcf1634cb0f387c9941c8a40a564b48163 |
| E/sampled_report.json | b0fd608dba2971b3ba65cb294b5e8754bd7add1f71b7cf69fc79d595197f39d0 |
| E/symptoms.json | 8d6d083b90db358d2de7b21537ff8c5f79c998da258da840357a4ea73059248d |

Actual `diff -u` of original oracle against scenario3 shows ONE change: the
16-round, six-scenario loop becomes one round of scenario3. Setup/oracle,
mmap/mprotect, child creation, real wait-status check and assembly are retained.
The reducer records original byte-identical rebuilds; this audit rehashed
those existing ELFs and did not rebuild them. Its build recipe is rv64gcv,
lp64d, static/nostdlib, no compiler vectorization, SEW=16, DETAIL_SCENARIOS=1.
These are Linux syscall ELFs, NOT bare-metal programs that can be loaded into
the integration runtime unchanged.

Exact scenario3 source contract (`scenario.c:28,32,34,37,40,44`): allocate two
4-KiB pages; initialize the last four e16 values of the first; PROT_NONE the
second; set all mask bytes to zero; call ordinary masked load at second-page
base with VL8. Child expects VL8/vstart0, all eight destination elements still
0x005b and intact guards; parent expects normal exit, not SIGSEGV.
Assembly first stages v24 and v0 from readable addresses (lines 10/11), then
executes the target at line 12, reads VL/vstart and stores the destination.

Independent read-only objdump of the actual reduced ELF:

```text
1044c: 0086f2d7  vsetvli t0,a3,e16,m1,tu,mu
10450: 0205dc07  vle16.v v24,(a1)
10454: 02b60007  vlm.v v0,(a2)
10458: 00055c07  vle16.v v24,(a0),v0.t
1045c: c2002573  csrr a0,vl
```

Original board ELF PC `0x1054e` independently decodes to the same `00055c07`.
`E/symptoms.json` binds reduced PC0x10458 and original PC0x1054e to cause13,
signal11 and tval-base=0. Historical output reports signal code0x2 and one
unexpected child signal in reduced scenario3; original scenario3 reports16.
The fault is at the target load, not the destination or mask preparation.
The audit explicitly claims symptom equivalence, NOT internal RTL causality.

`S/reference_512.json` and `reference_1024.json` report QEMU PASS for this
ELF (exit0); their scope is "QEMU reference, not FPGA result". They are not
Spike checks and not newly executed here. `S/manifest.json` still carries its
pre-board `board_reproduction_confirmed=false`; the later E audit carries
the matched board evidence. Preserve that chronology rather than silently
rewriting the sealed manifest.

Keep scenario identities distinct:

| Scenario | Predicate/address/op | Original oracle |
|---|---|---|
| 0 | all-on, four readable elements then protected page, FOF | no signal; VL4 and readable prefix |
| 1 | mask0x0f across same boundary, ordinary load | no signal; VL8 and only four changed elements |
| 2 | mask0x0f across same boundary, FOF | no signal; VL8 and only four changed elements |
| 3 | mask0, protected-page base, ordinary load | no signal; VL8 and unchanged destination |
| 4 | all-on, protected-page base, FOF | intentional SIGSEGV control |
| 5 | mask0, protected-page base, FOF | no signal; VL8 and unchanged destination |

The reduced bundle deliberately includes only 0/1/2/3/5, not scenario4.
Do not claim an existing standalone scenario4 ELF. Its source branch is in
the original oracle; any future isolated control must be a separately owned
derivative with explicit provenance.

## Minimal discriminating tests, NOT executed

### A. First measure the local request contract

Use a separately owned AddrGen fixture with the real module/types and a
deterministic MMU responder, or an already available compatible local harness.
No existing compatible executable was established in this audit. A new fixture
build requires later authorization; nothing in this plan authorizes one now.
Keep NrLanes=4, EEW16, NF1, VL8/vstart0, aligned base P, empty descriptor queue,
no scalar stores pending, AR/AW ready. Drive mask **valid**, owner=current ID,
first_element=0, payload zero; do not equate all-off with invalid mask.

After one observed `mmu_req_o` for P, return a single well-formed delayed
MMU response (`mmu_valid_i=1`, exception.valid=1, cause13, tval=P). Never inject
an unsolicited exception: otherwise the test merely exercises recovery.
Always drain generated descriptors and wait for AddrGen ack/idle; a fixture
that only instantiates AddrGen cannot certify actual VLDU retirement.

One small batch with resets between transactions is sufficient:

| Case | Required distinction |
|---|---|
| A0: ordinary VLE, vm0, all-off, VM enabled | Under the hypothesis a P translation occurs and fault is forwarded; correct all-off behavior must complete without architectural fault. |
| A1: same, bit0 active | Must request P and propagate cause13: checks the responder/address/exception oracle. |
| A2: all-off indexed VLXE, zero indices | Existing path should produce 8 skip descriptors, no P translation, and ack; validates mask owner/window/valid stimulus. |

Do not count "no MMU request" as PASS unless the request was accepted and
completed. Wrong owner, absent masks, full queues, ARREADY=0 or no instruction
acceptance are distinct stalls. A local result can establish unwanted requests
and propagated exception, not a real Linux permission/signal failure.

Bound the fixture to 256 cycles per transaction with a fixed MMU response
latency. A failed bound is a diagnostic result, not permission to extend it
or alter RTL. Capture only from acceptance to ack/drain. Add an all-off FOF
case only after A0 identifies the path; predicted first-page behavior is the
same exception because `vl == len>>vew`.

### B. Minimal real-translation privileged program

After local discrimination, use a separately owned tiny program on an
already built, hash-verified OSSupport/MMU-enabled integration image, without
booting Linux. Program compilation/execution is future work, not done here.
The inspected final02 AddrGen matches current source, but complete image
configuration/support must still be checked before reuse.

Enter S mode with Sv39, identity-mapped code/stack/data/page tables as needed,
appropriate PMP permissions, vector state enabled, and a mapped trap handler.
Use a 4-KiB inaccessible target P (invalid leaf for the basic mechanism;
this is not a byte-identical Linux PROT_NONE PTE representation). Make all
setup buffers readable/writable and set A/D on valid mappings to avoid
unrelated faults; SFENCE.VMA after page-table changes. Check both read-back
SATP/privilege and **actual `acc_mmu_en_q=1` at target admission**.

Do NOT substitute ordinary M-mode bare metal or assume MPRV is sufficient:
`ara.sv:591` disables MMU entirely without OSSupport; `ara.sv:617` registers
the supplied enable. In this tree `hardware/deps/cva6/core/cva6.sv:1642`
feeds the accelerator from `enable_translation_csr_ex`, whereas the scalar
data MPRV logic is separately handled in `csr_regfile.sv:2330`. A scalar
protected-load control passing alone is not proof Ara translation is on.

Preserve the scenario3 assembly sequence and e16/m1/tu/mu data oracle. Run
all-off ordinary target first, then an ordinary bit0-active control at P.
Use a scalar-only trap handler which logs cause, EPC, tval and progress to
mapped memory; skip only the known target PC, never silently accept a setup
fault. Follow with a readable ordinary vector load/store and CSR read to
distinguish correct target semantics from uncleared backend state. In the
all-off case require no trap, VL8/vstart0, unchanged destination/guards and
completion; in the active case require cause13 at the exact target PC/P.

Separate next step: scenario0 FOF prefix, then scenario5 all-off FOF and
scenario4 intentional first fault. This separates lost FOF metadata, missing
terminal retirement and missing predicate suppression. Do not fan out to
SEW/stride/segment variants before the first observation distinguishes them.

Target one run bounded to 90 seconds wall time, with a short acceptance-
triggered waveform (about 400ns for the local path; explicitly stop/report
if real page walking extends beyond it). Never infer a missing fault from a
capture that ends before the MMU response. Reuse a sealed capture helper only
through a new adapter/profile; do not edit the helper or pipeline inputs.

### Focused signals and falsification

Observe AddrGen `pe_req_valid_i`, accepted ID/op/vm/vl/vstart/FOF, both FSMs,
`addrgen_req_valid/ready`, `axi_addrgen_q.addr/len/vew`, queue full/push/pop,
mask payload/valid/owner/first element, `idx_predicate_valid/active`,
`en_ld_st_translation_i`, `mmu_req_d/o`, MMU vaddr/valid/exception,
AR/AW valid/ready, descriptor is_skip/is_exception, ack/exception_vstart/FOF,
and last_translation_completed. For the integrated test add VLDU exception
state/descriptor acceptance/load_complete, MASKU owner/running ID, sequencer
response, dispatcher flush state, trap EPC/cause/tval, and CSR VALID/READY.

Interpret in order:

1. Accepted all-off request + correct valid mask + P translation + returned
   cause13 + forwarded exception establishes the proposed mechanism locally.
2. No P translation + successful completion contradicts the current-source
   prediction: first check RTL/image pins and an upstream suppression path.
3. P translation without architectural exception does not by itself prove
   the Linux bug. Check MMU permissions/responder and any exception suppression.
4. No translation without completion is not a successful suppression repair.
5. Correct target response followed by stuck idle/CSR is a separate cleanup
   failure; retain the first exception/token rather than blaming the CSR PC.

Linux acceptance remains a later, separately authorized run of the genuine
ELF with mmap/mprotect, child wait-status and kernel-health checks. Neither
the local model nor a privileged derivative closes original signal/replay
behavior or the full 429-record family.
