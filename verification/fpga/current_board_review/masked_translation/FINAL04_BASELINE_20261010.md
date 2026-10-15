# Frozen Final04 Real-Sv39 Baseline

Completed host-VCS baseline, NOT candidate validation. No production RTL or
sealed helper edits, no RTL/software rebuild, no Linux/container launch.
Exactly the three previously host/Spike-passing SoC ELFs were reused once.

## Results

| Case | Strict result | Wall time | Observed behavior |
| --- | --- | --- | --- |
| alloff_fault | **FAIL** | 313.98s | Unexpected cause13 at the all-off target PC 0x80000b68, tval=0x40001000. |
| active_fault_retry | **PASS** | 309.49s | Exact cause13 at 0x80000c8c; repair PTE, SFENCE, same-PC retry; only later S-ECALL. |
| alloff_valid | **PASS** | 305.67s | Target retires normally; only the expected S-ECALL. |

All completed below their individual 600s limits. Each used an independent
singleton sealed runner, concurrently at most three, so the expected all-off
failure could not cancel either control. No additional reproduction variants
or reruns were launched.

The all-off FAIL is the architectural failure being reproduced, not a harness
PASS. The VCS executable returns zero even on the testbench's FAILED print;
the sealed runner correctly classifies its `Core Test *** FAILED *** (tohost=1)`
as FAIL and returns one. Never classify this case by simulator exit code alone.

## Exact First Error and Cycle Evidence

Cycles below are `ara_commit_monitor.cycle_q`, sampled on the positive clock
edge. `cvx_req` is the external valid/ready acceptance, not the earlier backend
allocation. `uop_done` is the tracked backend completion, not a normal target
retirement. These are not the local measurement04 cycle numbering.

For **alloff_fault**:

| Cycle | Evidence |
| --- | --- |
| 146151 | Actual SD writes target leaf PTE=0, wmask=ff. |
| 151387 | Actual SB writes input mask byte0=0, wmask=01. |
| 155713 | arch_start for target opcode 0x00055c07. |
| 155714 | Backend allocation, VID2, architectural sequence16, transaction7. |
| 155756 | cvx_req and matching cvx_resp with trap=1. |
| 155761 | Backend uop_done for that target. |
| 155821 | Handler CSR read: mcause=13. |
| 155833 | Handler CSR read: mepc=0x80000b68, exact masked-load target. |
| 155838 | Handler CSR read: mtval=0x40001000. |
| 155912 | Handler record stores younger marker=0. |
| 155939 | Handler record stores original target PTE=0. |

The stored trap record independently matches CSR reads: true S-mode MPP,
expected Sv39 SATP, VL8, vtype8, vstart0, fcsr117, vcsr5. No PTE repair or
target success/recovery-load site executes. The fixture takes its strict
unexpected-trap failure return. The FIRST printed software mismatch is check4,
`mt_unexpected`: wanted0, got1. Later errors are downstream incomplete-result
checks, not a different first fault. It finishes all 709 checks with errors139
and FAIL; the test is neither timeout nor retirement deadlock.

For **active_fault_retry**, cause13 is read at cycle155927 with exact target
EPC and the same tval. The trace then proves this order:

| Cycle | Site |
| --- | --- |
| 156518 | mt_repair_store |
| 156540 | Addressed mt_repair_sfence |
| 156547 | mt_retry_mret |
| 156572 | Original target PC0x80000c8c retires successfully |
| 156714 | Younger readable recovery load retires |
| 156732 | Younger scalar marker store retires |
| 157022 | S-ECALL at PC0x80000d3c |
| 157043 | Handler reads cause9, no second page fault |

Final scalar writes show checks709, errors0, completed magic, marker1,
trap_count2, unexpected0, and the repaired target PTE. Full old-vd, destination,
guard, data, page-table and restored-CSR checks executed in the unchanged ELF.

For **alloff_valid**, target PC0x80000b8c retires at cycle155764; backend done
is cycle155777; recovery load retires155906; marker store155924; S-ECALL156206.
The only trap is cause9 at the exact ECALL PC0x80000c3c. Final checks709,
errors0, completed magic, marker1, trap_count1, unexpected0 are confirmed by
actual scalar writes, not just the PASS string.

## Interpretation and Limits

This establishes the all-off target page fault on real S-mode/Sv39 hardware
simulation, using actual page tables and actual CSR trap records. The positive
control proves that ordinary active fault, page repair, precise original-PC
restart and younger execution work on this old image. The valid-page control
proves full old-vd preservation and successful completion for all-off when
translation succeeds.

The commit trace does NOT observe raw MMU requests/AR on the valid all-off
case. Its PASS does not establish that those requests were suppressed; local
measurement04 already observed unwanted translation/AR on valid all-off with
the identical AddrGen source. The present run proves the real exception chain,
not another raw-MMU waveform capture. No complete Linux signal/wait/retry or
store/stride/FOF/segment claim follows from these three load cases.

## Evidence and Identity

Root: `sv39_final04_baseline01/`.

- `preflight.json`: sealed image/config/ELF/runner compatibility, geometry and pins.
- `validate_before/`: sealed runner dry-run validation, no simulation there.
- `{case}/summary.json`: strict individual runner results and wall times.
- `{case}/tests/{case}/console.log`, `commit_trace.csv`, `inputs.json`, `command.json`: raw evidence.
- `analysis.json`: independent CSV-derived CSR records, setup, sites and ordering.
- `complete.json`: all three runners completed; post-run image and reference pin checks succeeded.
- `launch.json`, `children.json`: detached host process IDs and exact commands.

Image: `/home/wangwy/fpga_runs/current_board_integration_final04/campaign/image`.
Image ledger SHA256:
`6c6786cfaf55e803ba92a62662624ad2edfe6b257e7bd3234860e87192e8e3e8`.
Frozen AddrGen SHA256:
`a339e5fe0c96728e4e97e21139b03649121a6c37ba765a4ee62f261c7e14f988`.
Preflight SHA256:
`dc7508bf6861b040c5d08c61ba6ec4b621fe40e82d960cef6df101adbfd91c82`.
Analysis SHA256:
`d3b7a019ab0d2a8749fbaf1582f23ed691493f411b9eca7b4463aab63468de29`.

The exact SoC ELF hashes remain:

| ELF | SHA256 |
| --- | --- |
| alloff_fault | f82d0997b05006b39f50a68ee10bbe68863ab77e005fed15a6948a89e3070228 |
| active_fault_retry | 3878fe33e9a73e6cd183304418e67370df88104789cd257f11cb7253d09a2691 |
| alloff_valid | 61e9d623e877dace0f3bac6d71d01978ba8389ef35b4cda7e0c9af19098ea169 |

Interface checks before launch: ELF64 RISC-V, entry0x80000000; load segments
fit the frozen 2-MiB L2; 4 lanes/VLEN1024; no HTIF tohost symbol in these SoC
ELFs; UART0xc0000000 and CTRL0xd0000000; frozen OS support/PMP0 setup; compiled
source-manifest/library hashes and prepared-runtime provenance all checked.

## Candidate Staging, Not Execution

The candidate snapshot is
`/home/wangwy/fpga_runs/current_board_masked_candidate01/frozen`.
The parent identifies `ara-board-masked-candidate-build02` as the real build;
the earlier failed build invocation is not treated as a completed image.

`stage_candidate.py` has NO simulator-launch entrypoint. It verifies both
539-file seals, normalizes only root relocation in `frozen.filelist` and
`hardware/bender`, and requires that the sole semantic changed input is
`hardware/src/vlsu/addrgen.sv`, candidate SHA256
`470c6c92d26cd2e540562302788f58d8d85ae6f147886fb949668e7728be41da`.
The staging plan keeps the exact three ELFs/oracles and isolated 600s runners.

Candidate execution is blocked until explicit parent confirmation that local
tests and build02 PASS. After confirmation, verify the completed candidate
image binds this exact snapshot and passes the sealed runner dry-run before
running the same three ELFs in a separate candidate output directory. No
baseline PASS in this report is a candidate PASS.

Parent update after staging: build02 exited0 and candidate image.json exists.
Local AddrGen verification is still pending; candidate execution has NOT begun.
The parent also reports a separate real-VLDU exception-path risk under test.
If a later active-fault run hangs, first distinguish ordered AddrGen exception
delivery from VLDU prefix drain/exception cleanup/completion; do not attribute
the hang to AddrGen merely because its source is the candidate's changed input.
