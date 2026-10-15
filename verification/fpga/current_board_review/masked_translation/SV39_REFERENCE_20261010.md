# Sv39 Scenario3 Reference Preparation

Result: **HOST_SPIKE_PASS_NOT_DUT**, all three cases. No VCS launch, no RTL
build/edit, no Linux launch, and no edits to sealed helpers or measurement01-04.
The parent's new `REPAIR_CONTRACT.md` is not modified.

## Files and Reproduction

Independent sources: `sv39_fixture.c`, `sv39_fixture.S`, `sv39_adapter.py`.
Negative checker tests: `test_sv39_oracle.py`.
Completed reference evidence: `sv39_reference02/status.json`,
`sv39_reference02/{alloff_fault,active_fault_retry,alloff_valid}/validation.json`,
each case's full `spike.trace`, and `sv39_reference02/{soc,spike}/programs.json`.
Every compiler/reference command and disassembly is retained. `input_pins.json`
binds the source, runtime, original Linux inputs, compiler and Spike. The final
status pins all output evidence and records VCS_launched=false.

From the worktree, with a FRESH output directory under masked_translation:

```sh
python3 verification/fpga/current_board_review/masked_translation/sv39_adapter.py reference --out verification/fpga/current_board_review/masked_translation/sv39_reference03
```

This command builds software only and runs host/Spike, never VCS. Existing
reference01/02 directories are not overwritten. Each Spike is bounded to 60s;
the entire reference preparation, including Python full-trace checking, takes
roughly a minute on this host. No simulator timeout was increased during bringup.

## Exact Software Contract

The original reduced scenario3 `load_0` sequence is preserved in the S body:
vset e16/m1/tu/mu VL8; vle16 v24 from out+1; vlm v0; masked vle16 v24;
read VL/vstart; vset VL8; store v24 to out+1. Old-vd is **uint16_t 0x005b**,
not a repeated byte 0x5b. All 130 original output elements are checked,
including original out[0]/out[9] guards and all unused output elements.

Additional initialization defines all 128 bytes of v24 before the original
VL8 load, plus v23/v25 neighbors and v8 recovery register. Full-register
snapshots cover all four registers, not just the eight active destination
elements. Each snapshot also has 64-byte guards on each side. The v0 tail
after VLM is not assigned a unique oracle because mask-load tail is agnostic;
all 16 input-mask bytes and every architecturally specified old-vd/guard byte
remain checked. No full-v0-tail or all-32-register VRF claim is made.

The program enters TRUE S-mode by MRET with Sv39 SATP. Code/stack/test data
at 0x80000000 are identity mapped; target 0x40001000 uses a 4-KiB leaf PTE.
Readable page 0x40000000 is separately mapped. A/D bits are preset for valid
mappings. The protected target's leaf is V=0, not a claim of Linux's exact
PROT_NONE PTE encoding. Scalar MPRV-only is not substituted for S mode.

| Case | Predicate/PTE | Strict expected events |
| --- | --- | --- |
| alloff_fault | mask0, target leaf0 | No target page fault or target memory access, no PTE repair; only the final S-ECALL. |
| active_fault_retry | bit0, same leaf0 | Exactly one cause13 at target PC, tval=0x40001000, vstart=0, marker=0, original PTE=0; repair one PTE, addressed SFENCE, same-PC MRET; e0 loaded and remaining old-vd preserved; final S-ECALL. |
| alloff_valid | mask0, target leaf valid | No target memory access or target exception; only final S-ECALL; valid PTE remains unchanged. |

All require VL8, vtype8 (e16/m1/tu/mu), vstart0, fcsr117, vcsr5; a younger
ordinary load from readable page0 and scalar progress marker; complete output,
register snapshot, 8-KiB data, 12-KiB PTE and outer-guard checks. Relevant CSRs
and machine trap state are restored and read back before successful exit.
There are 709 local checks per case, independently matched in the commit trace.

Unexpected traps log scalar metadata and take failure return before vector
snapshot/repair. Only the exact permitted active fault takes a vector fault
snapshot and repairs the PTE. Its handler preserves the target base/destination/
mask argument registers and does not modify MEPC before the original-PC retry.
The Python oracle independently verifies exact privilege/opcodes, trap ledger,
memory access list, retry ordering, stored CSR records, and complete final
memory. Exit0 or a PASS string alone is insufficient for reference PASS.

## Measured Reference Results

| Case | Spike target PC | Trap ledger | Commit lines | Independently checked memory bytes |
| --- | --- | --- | --- | --- |
| alloff_fault | 0x80000b70 | S-ECALL @0x80000c20 only | 275188 | 23084 |
| active_fault_retry | 0x80000c94 | load page fault @target; S-ECALL @0x80000d44 | 275326 | 23076 |
| alloff_valid | 0x80000b94 | S-ECALL @0x80000c44 only | 275191 | 23084 |

Commit-line counts include bounded HTIF-exit spin records and are software
reference statistics, NOT DUT cycles. The smaller active checked-byte count
reflects a second trap mstatus checked with an exact defined-bit mask separately;
its record is not omitted. All data/old-vd/guard bytes are fully compared.

Status SHA256:
`7ffc955dffc46d32b02a6e8e270a6ff4481c32205420437a238b19a32ddce128`.

| ELF | SHA256 |
| --- | --- |
| spike/alloff_fault.elf | 56ad5ad806c9290cd8246abb84a9673af79a94a00cb13a630fddd9b5729a829e |
| spike/active_fault_retry.elf | e9079d8f4d97cec19596f61407709ed8f374d32e41cd63bfea835337a013939d |
| spike/alloff_valid.elf | 29f29e42a114abcd250d0bc894834c791b8f09774c66bfbd51506136b21d265d |
| soc/alloff_fault.elf | f82d0997b05006b39f50a68ee10bbe68863ab77e005fed15a6948a89e3070228 |
| soc/active_fault_retry.elf | 3878fe33e9a73e6cd183304418e67370df88104789cd257f11cb7253d09a2691 |
| soc/alloff_valid.elf | 61e9d623e877dace0f3bac6d71d01978ba8389ef35b4cda7e0c9af19098ea169 |

The SoC and Spike ELFs differ in the existing runtime's UART/CTRL versus HTIF
backend. These are separately pinned software builds from identical fixture
sources, not byte-identical ELFs or already executed SoC results.

## reference01 Failure: Exact Cause, Not a DUT Finding

`sv39_reference01/failure.json` is retained. The first alloff_fault Spike run
exited 0, with only its expected S-ECALL. Its target commit at trace line274394:

```text
core   0: 1 0x0000000080000b70 (0x00055c07) e16 m1 l8 c8_vstart 0x0000000000000000
```

Spike emits NO v24 write event when every target element is inactive. The
initial checker erroneously required one explicit v24 write event even here,
and raised `Complete destination/undisturbed tail differs: mt_target`.
There was no measured value difference, setup fault, policy change, mapping
fault, or vstart mismatch. The message described an overly broad checker
condition, not evidence that tail data differed.

The correction requires the EXACT no-write/no-memory/vstart0 target event for
the two all-off cases, while retaining the full-value write-event check for
active retry. Complete stored snapshots remain mandatory in every case.
In reference02, the v24 snapshot at 0x800073c0..0x8000743f contains 32 words of
0x005b005b, written by `vse32.v v24` at PC0x80000bf8. All 128 bytes were compared
independently, including the tail. Neighbor snapshots and original output
buffer were also fully checked. No byte was converted to don't-care.

The initial arbitrary 250k commit ceiling was separately corrected to 350k
after inspecting the complete 275188-line successful scalar-initialization/
verification trace. No instruction loop, data oracle, runtime timeout, or
exception allowance was changed. This is a reference-parser bound, not an
RTL performance acceptance criterion.

`sv39_oracle_negative01.json` records offline mutation checks, without rerunning
any simulator. The checker rejects an inserted all-off page fault, a one-bit
change to v24's LAST tail word (0x8000743c), and a one-bit change to v25's last
guard-register word (0x800074bc). Thus the no-write-event fix does not hide an
old-vd/guard corruption. These are deliberately corrupted in-memory trace
copies, never modifications of the sealed trace.

## Reuse and Original Identity

The new fixture follows the real S-mode/page-table/trap/retry approach in
`apps/riscv-tests/isa/rv64uv/vsv39_masked_unit_fault_retry.c` and its coverage
preflight. Those existing files are read/pinned, not edited or invoked with
relaxed baseline seals. Their expected-fault e8/VL17 oracle is NOT relabeled
as scenario3 all-off coverage. The FOF fixture remains a separate future
regression, not evidence for this ordinary-load case.

The adapter copies the sealed integration startup/runtime/linker from
`/tmp/current-board-integration-fast01/prepared` after `prepare.check`, without
editing the helpers. The new app installs its own handler and restores the
startup trap state. All generated artifacts stay in this directory.

Original Linux provenance is rehashed before and after preparation, copied to
`sv39_reference02/linux_provenance.json`, and included in input pins:

- Original exception_oracle.c: af36b5d8475b2949e09957ad742bbb863d0b5a59c5cf9cd959edc2dc6bc86794.
- Original deployed rvv_exceptions_detail_e16 ELF: d7f8507da5afaf4c4683bb5b35861f6f99cd71bcbf06f6622a791d9786c55923.
- Reduced scenario3 ELF: 9de2343469ad5bd8d5c7ac817bed69ba2d9847bc29f2426a6b817f343b08651c.
- Reduced scenario.c: 45a6c005b92933c0cf3315d7ae08dc27377ca51c54df30c291be79bb4495ed03.
- Reduced scenario.S: 2d75fc09a289e319c2e58fc812748f9030e6ccd2f864753b10d874535d489376.

No original Linux ELF was run as bare metal. mmap/mprotect, fork/wait/signal
behavior and the Linux permission encoding are not reproduced or closed here.

## Deferred One-Case SoC Command

NOT executed. The final03 image exists; its frozen Ara/SoC source enables OS
support and sets NrPMPEntries=0, matching this reference setup. Full image,
source/config and program pins must still pass the sealed runner at launch.

```sh
python3 verification/fpga/current_board_review/integration/run.py run --image /home/wangwy/fpga_runs/current_board_integration_final03/campaign/image --programs verification/fpga/current_board_review/masked_translation/sv39_reference02/soc --case alloff_fault --jobs 1 --timeout 90 --execute --out verification/fpga/current_board_review/masked_translation/sv39_final03_baseline01
```

This is image reuse only, not a VCS build. Budget one execution capped at 90s
plus image-pin validation overhead; the new fixture's roughly 275k reference
commits mean a 90s DUT completion is not yet established. A timeout would be
inconclusive, not permission to extend the run or classify an all-off fault.
The newest parent instruction prioritizes reference preparation and says not
to rush VCS while full04 runs; therefore this command remains a proposal.
Announce exact command/budget again before any future launch.

A future DUT result needs real S-mode target acceptance/acc_mmu_en_q, MMU
request/exception, ordered consumer completion and trap record correlation.
An expected unfixed all-off fault must remain DUT FAIL under this strict oracle,
never a PASS reinterpretation. Static repair obligations are in
`REPAIR_REVIEW_20261010.md`.
