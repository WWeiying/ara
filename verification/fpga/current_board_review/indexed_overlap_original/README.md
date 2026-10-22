# RVV-01 Original Indexed Overlap: Preparation Only

No VCS launch or production change is authorized here. The three selected
programs are `d32m2_i64_fault_ov1`, `d32m2_i64_resident_ov1`, and
`d32m2_i64_fault_ov0`. The archived failure is the first program's Linux SIGSEGV,
not a measured current-RTL failure.

## Source Identity

Archive: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/`.
`width_restart04_live.json` records each exact compiler command and ELF hash.
`prepare.py` repeats those commands, changing only the output path, and requires
byte-identical original Linux ELFs before preparing each adapter.

| Original ELF | SHA256 |
|---|---|
| fault ov1 | `07b1438fbea419215576f071fd5e89c38f01238ab19fbc564ad861faf738e03d` |
| resident ov1 | `76ef2e1a73b1987729ba887a99108ad2fe61daeee36634d6e847448489941df5` |
| fault ov0 | `06df907defa6a148601d7a275fc8d6a63c9f8f07842e61da2a09636abb481772` |

Original C SHA256: `64f95f20d87d405c81f8e0848efc72390391d1b0312037c6001ac3e66558c74b`.
Original ASM SHA256: `ea838ecf30290c56134d4ad5972f08288bc573d92d8217ff41349e6d00748fa8`.
The adapter includes a byte-identical copy of original C, renaming its entry
and wrapping helper calls only to add checks. Original ASM is compiled unchanged;
the checker compares its complete helper opcode sequence against the original
ELF, including configuration, index reload, target, result store and CSR reads.

## Retained Contract

- All 50 rounds, all 32 gathered values per round, both `0x5b12` guards, original
  expected-byte assembly, VL check, and original helper's final vstart check.
- Original pages: 32768 uint32 values `(i*7919)^0xa5a50f0f`.
  Index `i`: `((i*13+7)%32)*4096`. No input filtering or shortened matrix.
- Original e64m4 index setup in v4; e32m2 VL32 `tu,mu` destination v4 (ov1)
  or v16 (ov0). The narrower destination overlaps the lowest part of the wider
  source: this is legal, not a reserved overlap encoding.
- Resident program retains its additional original masked restart helper:
  VL17/start7/odd mask, old v16=-7, then full 32-value check.
- Additional independent checks: exact final VL32/vtype17/vstart0/fcsr117/vcsr5,
  every input index, all backing memory, PTEs, checkpoint order and firmware exit.

## Explicit Porting Boundary

The Linux syscall instruction remains in original C. The local M-mode handler
implements the narrow memfd/write/mmap/getrusage/munmap/exit service contract.
Code runs in S-mode with actual Sv39 translation. Startup/runtime/linker are
copied from `/tmp/current-board-integration-fast01/prepared`; M/S transition
follows the accepted NF2 fixture under `masked_translation/segment_review/sv39`.
The syscall ABI compatibility header supplies RV64 rusage layout because
bare-metal newlib does not expose `ru_minflt`.

Each fault round deliberately starts with 32 invalid read-only leaf PTEs.
The handler repairs only the faulting page and retries unchanged mepc, preserving
all scalar registers, vector state, vstart and indices. It executes no vector
instruction and never writes vstart/vtype. This gives 32 faults per round,
including starts 1..31, and 1600 faults per fault ELF in Spike.

This is **not** the historical Linux page-fault schedule. Archived fault ov0
reported 150 minor faults across 50 rounds; Linux mapping/read-ahead batching and
the failing ov1 round/start are unknown. The historical ov1 PC was `0x1045a`,
base `0x3fba441000`, badaddr `0xc03fba460000`, cause13/exit139. Those observations
do not establish a present snapshot-lifetime or layout root cause.

Host substitutes only the inline-assembly syscall boundary and vector execution
with scalar models, then runs the original C oracle. Spike uses original ASM and
the real traps. Neither is DUT acceptance. No oracle will be reduced to meet a
three-hour DUT budget; reference instruction count and measured comparable
simulation throughput must be reviewed before any later launch.

## Preparation History

- `reference01`: first fault/ov1 original ELF rebuilt identically; host finished.
  Adapter compile rejected newlib's missing `rusage.ru_minflt`; no Spike/DUT
  acceptance. Logs preserved. Added a local ABI compatibility header, not an
  oracle change.
- `reference02`: all three original Linux ELFs rebuilt byte-identically. Fault
  ov1 and resident ov1 passed host/Spike. Fault ov0 failed in the adapter handler,
  before its first completed gather: its original load PC `0x80000d3e` is only
  two-byte aligned, and the handler's uint32 opcode read trapped at `0x800006f8`
  with `trap_load_address_misaligned`. `gather32+26` was the correct target PC.
  Replaced that diagnostic read with four volatile byte loads. No original
  source, ASM, expected data, round count or fault policy changed. The failed
  trace and successful sibling statuses remain preserved.
- `reference03`: all three complete host/Spike references PASS, including
  byte-identical original ELF rebuilds and all 41 original helper instructions.
  Final counts, identities, ISA/layout, runtime dependencies and estimated cost
  are in `REFERENCE_REPORT.md` and `REFERENCE_HANDOFF.json`. These are the
  reviewed preparation inputs for a future separately authorized DUT pilot.

See `PROBE_PLAN.md` for the three discriminating hypotheses and capture boundary.
