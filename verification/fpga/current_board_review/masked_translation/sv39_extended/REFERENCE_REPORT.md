# Extended Sv39 Reference, 2026-10-10

Status: **HOST_SPIKE_PASS_NOT_DUT**. First software/reference run passed all
eight cases. No VCS, SoC image build/run, Linux launch, production RTL edit,
or sealed helper/input edit was performed. This does not close the outstanding
VLDU delayed-final-grant or cross-instruction fault-epoch questions.

## Selected Original Scenarios

All sources are under
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/`.
Every case is e16/m1, VL8, tu/mu, NF1, initially vstart=0. P=0x40001000.
`u0` selects protection rather than munmap. Stride is carried in t3, including
zero; it is not the x0 special encoding.

| ID | Handoff / selected original suffix | Instruction / setup | Required result |
|---|---|---|---|
| 0 | `rvv_fault_handoff_e16m1_01`, `rvv_small_fault_e16_m1_u0_s0_b3_m2` | `vle16.v v24,(a0),v0.t`; base P-6, mask24 | cause13 at P+4, vstart5; element2 prefix committed; unchanged-PC retry |
| 1 | same bundle, `rvv_small_fault_e16_m1_u0_s1_b3_m2` | `vse16.v v24,(a0),v0.t`; base P-6, mask24 | cause15 at P+4, vstart5; element2 store committed; retry cannot overwrite poisoned prefix |
| 2 | `rvv_strided_fault_handoff01`, `rvv_small_fault_strided_e16_m1_u0_s0_b3_m2_f0_g3` | `vlse16.v v24,(a0),t3,v0.t`; base P-24, stride+8, mask24 | cause13 at P+16, vstart5; element2 prefix at P-8 |
| 3 | `rvv_negative_stride_handoff01`, `rvv_small_fault_strided_negative_stride_e16_m1_u0_s1_b3_m2_f0_g1` | `vsse16.v v24,(a0),t3,v0.t`; base P+10, stride-4, mask24; first page denied | cause15 at P-10, vstart5; element2 prefix at P+2 |
| 4 | `rvv_zero_stride_handoff01`, `rvv_small_fault_strided_zero_stride_e16_m1_u0_s0_b0_m2_f0` | `vlse16.v v24,(a0),t3,v0.t`; base P, stride0, mask24 | cause13 at P, vstart2, not element0; retry reads P for elements2/5 |
| 5 | same bundle, `rvv_small_fault_strided_zero_stride_e16_m1_u0_s1_b0_m3_f0` | `vsse16.v v24,(a0),t3,v0.t`; base P, stride0, mask00 | no page fault, no target writes; PTE remains invalid; old source and all memory unchanged |
| 6 | `rvv_small_exceptions01/rvv_small_exceptions_e16_scenario0` | `vle16ff.v v24,(a0),v0.t`; base P-8, maskff | no architectural page-fault trap; VL4, vstart0, four-element prefix |
| 7 | same bundle, `rvv_small_exceptions_e16_scenario2` | same FOF instruction/base, mask0f | no page fault; VL8, vstart0; protected suffix including final element stays inactive |

Masks above are hexadecimal. Cases0-4 preserve the handoff's fault-address and
fault-vstart oracle, not the old board's incorrect observed context. For example,
case0's delivered trace faulted at boundary element3/P, whereas the required
first active denied access is element5/P+4. Cases0-3 also end with inactive
elements6/7, discriminating final-skip completion after active retry.

## Identity And Adaptation

- [linux_provenance.json](reference01/linux_provenance.json) records absolute
  original C/S, reduced Linux ELF, immutable original Linux ELF paths and SHA256,
  plus complete handoff metadata and per-case adaptation parameters. All declared
  source/reduced/original hashes were verified before and after reference execution.
- Replay handoffs explicitly say `original_rebuild_byte_identical=false` and
  `single_current_oracle_trial`. These are faithful derivatives of those selected
  delivered trials, not proof of old original per-trial equivalence.
- The two reduced FOF cases retain their manifest's byte-identical original
  rebuild identity. Their original Linux ELFs were hashed, never executed.
- mmap/mprotect/signal/ucontext are replaced by real Sv39 pages, S-mode MRET,
  exact M-mode trap records and PTE repair. Denied leaf PTE=0 models access denial,
  not Linux's exact PROT_NONE PTE encoding or SIGSEGV ABI.
- Code/stack are identity mapped at 0x80000000; test VA0x40000000 maps two separate
  physical data pages. Root/middle/leaf page tables are real. Leaf flags are 0xc7
  after repair. Negative stride denies the lower data page; others deny the upper.
- Replay data pattern `half*37+11`, source `101+13*i` (zero-stride store constant101),
  mask patterns, full capacity64 output and poison-xor0x5b are preserved. FOF keeps
  its original four readable values 11/48/85/122, output[130] initialized0x5b, and
  original VL8 post-target output store. Deterministic denied-page backing is an
  adaptation, not a claim about Linux's inaccessible data.

## Oracle And Completion

[fixture.h](fixture.h) defines the eight configurations. [fixture.S](fixture.S)
executes the targets in S-mode and preserves scalar context across traps.
[fixture.c](fixture.c) checks these invariants:

- Exact cause, target PC, tval, S-mode status, satp, VL, vtype, vstart, fcsr=117,
  vcsr=5, younger marker and denied PTE are checked before snapshot/repair.
  Unexpected, early, repeated or wrong-PC faults fail; they are not accepted as
  evidence that the intended active fault happened.
- Full128-byte v24 and both adjacent128-byte v23/v25 are stored at the fault and
  completion boundaries, with 64-byte guards before/after every snapshot. Seed
  buffers, output[130], all16 mask bytes, both complete data pages, all three page
  tables and external64-byte guards are checked. Only v23-v25 are the tested VRF
  region; this is not a claim that all32 vector registers were snapshotted.
- The fault checkpoint checks the complete prefix before any PTE repair or
  poison write. PTE repair plus addressed SFENCE precedes MRET. Original target
  PC is unchanged; the saved vstart is restored after diagnostic vector stores.
- The handler then poisons completed active memory locations, as the original
  replay source did. A load replay from element0 corrupts its old prefix; a store
  replay from element0 overwrites the poison. Both are rejected. Final memory
  comparison also rejects writes to masked addresses and surrounding stride gaps.
- Target-completion CSR state is recorded before diagnostic vsetvli. A younger
  scalar marker and exact S-mode ECALL must follow. All saved machine/vector/FP
  control CSRs are restored and checked before returning to the shared runtime.
- Data and page tables are initialized once. After each case, complete validation
  precedes cleanup of the few touched words; cleanup is disabled on failure.
  FOF's four readable words are changed only after previous cases pass.
- Full scans use 64-bit XOR/OR aggregation, not sampling or probabilistic hashes.
  Independent Python reconstructs committed memory and checks each byte at all
  13 checkpoints, including precise predicate-qualified target access lists.

FOF scenario0 retains the original oracle's exclusion of elements4-7 after
VL shortens. Those values are fully captured in the trace/snapshot, but are not
required to equal their old values. Elements0-3, elements8-63, all neighboring
registers, guards, memory and CSRs remain strict. Scenario2 checks every v24
element, including masked suffix4-7. This is not an exception-oracle relaxation.
The precise-fault snapshots additionally assert this Spike's unchanged
post-fault v24 suffix; do not generalize that stronger observation into a claim
about every implementation's permitted speculative register updates.

## Measured Reference

Evidence: [status.json](reference01/status.json),
[spike.trace](reference01/spike.trace),
[negative_oracle.json](reference01/negative_oracle.json),
[input_pins.json](reference01/input_pins.json).

- Host C versus independently specified Python: 35,840 rows PASS.
- Spike: 780,454 parsed commit events, 6,227 software checks, zero errors,
  completion magic `0x6d78737633390008`, tohost=1.
- Five expected page faults (three loads/two stores), five unchanged-PC retries,
  eight expected S-mode ECALLs; no other architectural exceptions.
- Fault/final checkpoints: 13; each independently checks 22,360-22,660 bytes.
- Per-case checks: 630/630/630/630/630/456/448/456, plus common and restore checks.
- Runtime including Python trace validation: 30.624 seconds. This is not an RTL
  cycle or SoC wall-time measurement. Eight cases share one ELF and initialization.
- Six injected oracle corruptions are rejected: oldvd tail, load prefix, replayed
  store prefix, masked-store side effect, wrong fault_vstart, FOF inactive suffix.

SOFTWARE ELF SHA256:

```text
soc.elf   a0219fef355612a36370851a6a4d3011bb30991afbc19459068c3728526ea982
spike.elf 7930df70a20a13f37683dc8d9556e189eca26dfbd2df6eae401be8619657430e
```

SoC ELF is only prepared, not executed or bound to a new image. Its BSS ends at
0x8000e160, within the sealed runtime's L2/stack layout. SoC target symbols are in
[soc.symbols.json](reference01/soc.symbols.json); Spike has separate symbols and
HTIF output. Do not run the Linux ELF or substitute HTIF ELF for the SoC ELF.

## Reproduction And Deferred Scope

From the integration worktree, software-only reference can be reproduced in a
fresh owned directory:

```sh
python3 verification/fpga/current_board_review/masked_translation/sv39_extended/reference.py --out verification/fpga/current_board_review/masked_translation/sv39_extended/reference02
```

The adapter has no VCS entry point. Before any later authorized SoC run, separately
pin the chosen frozen image, runner/interface, this SoC ELF and its own symbols.
Do not inherit the prior three-case candidate PASS or a full-system timeout from
this software result. The combined eight-case program may need a different bounded
SoC budget; no estimate here is a measured SoC runtime.

Not covered: NF>1/segment splits, indexed memory, e8/e32/e64, fractional/larger
LMUL, unaligned elements, munmap/remap, Linux signal ABI, arbitrary initial
vstart, multi-maskword VL, active zero-stride stores, negative-stride loads,
FOF first-element fault, injected AXI/grant backpressure, or cross-instruction
fault-epoch cleanup. Completion here proves reference architectural behavior,
not cycle-level VLDU/VSTU exception or queue ownership correctness.
