# Gap97 CSR and Large AVL Preflight

Scope: one new bounded bare-metal fixture, compiler and Spike preflight only.
No VCS/DVE run, admission, exclusion, new RTL signoff, or configuration change.

## Inputs and Existing Fixtures

- `apps/riscv-tests/isa/rv64uv/vgap97_csr_large_avl.c` uses the existing
  `verification/tests/gap75_start.S` and `gap75.ld` unchanged.
- `vgap35_vstart_csr.c` exercises vstart RMW, not this vxsat/VCSR matrix.
- `linux_csr_gap33.c` exercises system CSRs, not this vector CSR matrix.
- Existing fault fixtures save/restore VCSR; this is independent RMW checking.
- Exact admitted705 baseline:
  `verification/out/gap96-offline-admitted-705-20261006-01/combined-bits.json`.
- Six target coordinates are diagnostic raw condition offsets, NOT DVE IDs.

## Architecture Contract

VXSAT and VCSR each execute CSRRS(register 1), CSRRC(register 1),
CSRRSI(1), CSRRCI(1), CSRRCI(2), independently initialized by writing VCSR.
The dynamic mask is loaded from volatile memory and checked in the committed
register state; source and destination encodings cannot be x0.

| Operation | Initial VCSR | VXSAT returned old / new VCSR | VCSR returned old / new VCSR |
| --- | --- | --- | --- |
| CSRRS 1 | 4 | 0 / 5 | 4 / 5 |
| CSRRC 1 | 7 | 1 / 6 | 7 / 6 |
| CSRRSI 1 | 2 | 0 / 3 | 2 / 3 |
| CSRRCI 1 | 5 | 1 / 4 | 5 / 4 |
| CSRRCI 2 | 6 | 0 / 6 | 6 / 4 |

Each phase checks seven observations: initial VCSR/vxsat/vxrm, returned old,
and final VCSR/vxsat/vxrm. The last immediate operation distinguishes reserved
VXSAT bit 1 from meaningful VCSR VXRM bit 0. No saturation arithmetic is used.

One `vsetvli` with AVL `1 << 20`, E8/M1/TU/MU checks returned VL=128,
CSR VL=128, VTYPE=0, VLENB=128, VSTART=0. Total: 75 checks, 600 exact
observation bytes, no vector data requests or vector register groups.

## Exact705 Targets and Source Identity

Dispatcher scope: `ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher`.
Condition checksum `1370170966`, width 1140, module checksum `1448229316`.

| Raw offset | Source line | XML condreg | Vector | Intended stimulus |
| --- | --- | --- | --- | --- |
| 189 | 1736 | 75 | 10 | AVL high bits nonzero, low 11 bits zero |
| 576 | 4695 | 246 | 01 | VCSR CSRRS old sat 0, set bit 0 |
| 588 | 4729 | 251 | 10 | VCSR CSRRC old sat 1, clear bit 0 |
| 603 | 4804 | 257 | 01 | VCSR CSRRSI old sat 0, zimm 1 |
| 615 | 4843 | 262 | 10 | VCSR CSRRCI old sat 1, zimm 1 |
| 616 | 4843 | 262 | 01 | VCSR CSRRCI old sat 0, zimm 2 |

The five CSR targets are VCSR source branches, not the corresponding VXSAT
branches. The frozen source SHA256 is
`9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43`.
It is recovered from `/home/wangwy/openproject/ara_dsa/hardware/src/ara_dispatcher.sv`,
checked against the original integration build-source manifest key, and copied
verbatim into each final preflight output. The current integration dispatcher
is not used to explain the compiled image. Original compile flags and compiled
parameters are recorded without modifying either.

The preflight pins bitmap/status, design files, source coordinates and condition
shape/info, tools, startup/linker, fixture, parser/checker code, and tests;
inputs are rehashed after Spike. The old plan image hashes are recorded, but
the executable image is not launched or certified by this Spike-only preflight.

## Reproduction and Admission Boundary

```sh
cd verification/coverage
python3 -B -m unittest test_build_gap97_preflight -v
cd ../..
python3 -B verification/coverage/build_gap97_preflight.py \
  --output verification/out/gap97-csr-large-avl-preflight-705-20261006-02
```

The output contains target-before.json, archived source, compile/Spike commands,
ELF/disassembly, trace, exact validation, and a hashed preflight manifest.
Directories must be fresh; failed and earlier successful evidence is preserved.
Committed probe PCs must occur once and in exact order. All observations must
be written with exact values. Trap-handler entry, wrong CSR/operand/old value,
incomplete signature, or any prior/duplicate tohost write fails closed.

Any future VCS runner needs its own frozen image identity checks and full scalar
comparison plus contract/signature validation. Zero vector data traffic is
intentional here, not a substituted empty vector-comparator PASS. Actual
coverage gain must be measured separately; the six intended targets remain
unapproved predictions until that run.

## Separate PMP/PTW Case Plan (Not Implemented)

Goal: cold Sv39 translation whose physical PTE read is rejected by PMP, rather
than a normal unmapped/permission page fault. The matched frozen PTW checks PTE
reads as S-mode READ (`cva6_ptw.sv:238..249`), routes `!allow_access` to
PROPAGATE_ACCESS_ERROR (`563..584`), and the MMU maps data loads to access fault
(`cva6_mmu.sv:703..725`). Existing `sv39_state_prereq.c` provides the bounded
M-handler/Sv39 setup pattern, but its frozen source must not be changed.

Minimal reviewed implementation should:

1. Keep the handler and initial code in M mode, use separate aligned root/mid/
   leaf table pages and a mapped data page with valid R/W/A/D PTEs.
2. Save PMP/SATP/status/trap CSRs. Verify the actual old-image PMP entry count,
   unlocked writable entries and exact CSR readback before enabling translation.
3. Put a higher-priority NAPOT deny rule over only the selected 4 KiB leaf-table
   page, with a lower-priority allow rule over required RAM. An illustrative
   deny encoding is pmpaddr=(PA>>2)|511, pmpcfg byte=0x18; this is a proposal,
   not a certified configuration. Leave M-mode handler access unlocked.
4. Flush translations and perform a labelled load via S privilege or carefully
   bounded MPRV/MPP=S. Expect exactly one mcause=5, exact mepc and original
   faulting VA in mtval; unexpected traps must fail, not be counted as success.
5. Clear MPRV before handler memory accesses if using that route. Restore allow
   permissions, sfence.vma, retry the same instruction, check exact data, then
   restore all saved architectural state and verify completion.

Discriminator: `allow_access=0` with valid PTE contents, followed by
PTE_LOOKUP -> PROPAGATE_ACCESS_ERROR -> LATENCY. On705, FSM checksum3345966803
raw2 (state), raw16 (entry), raw11 (exit) and PTW condition raw0 are unhit.
A data load does NOT hit MMU raw44: that condition at line450 belongs to ITLB
fault propagation. A separate cold translated instruction-fetch phase could
target it with mcause=1, but is not required for the first bounded case.

PMP-enabled Spike settings must be reviewed separately (not the gap97
`--pmpregions=0` setting). This plan authorizes no simulation, no fault injection,
no waiver, and no aggregate admission. Do not promise gain until the PMP
configuration and the exact trap/retry contract have been independently reviewed.
