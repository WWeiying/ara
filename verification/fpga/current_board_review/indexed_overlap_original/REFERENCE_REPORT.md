# Three Original-Source Sv39 References Ready

**HOST/SPIKE ONLY. No DUT run, image rebuild or production edit.**
Accepted preparation directory: `reference03/`. Do not use the incomplete
`reference01/02` as the launch input. Those raw failure histories remain intact.

## Exact Evidence

`reference03/status.json`: `THREE_HOST_SPIKE_REFERENCES_PASS_NOT_DUT`.
All three per-case `status.json` files report `HOST_SPIKE_PASS_NOT_DUT`.
`REFERENCE_HANDOFF.json` contains 58 generated artifact pins and the exact SoC/
Spike ELF identities, PCs, sizes and counts. All 21 preparation input pins were
independently rehashed after completion with zero differences.

- `reference03/identities.json` SHA256:
  `4a5546cc452378cdbdd71a5f5d0fac9bb4cd60f5de8769c9dd6fa49c814f238b`.
- `reference03/pins.json` SHA256:
  `43620fbe4885ca490a37cb1fee45afd63630d5a6f4805861ac470ffc0e4d12ea`.
- Each original Linux ELF rebuilt byte-identically using the archived command,
  changing only `-o`. Exact commands and archived SHA256s are in identities.json.
- All 41 original helper instructions, including both gather branches, index
  setup, all configuration/CSR operations and resident masked restart, match the
  original ELF's machine code. This is not a reconstructed tiny VFU substitute.
- Host executed original 50-round C oracle; independent Python checked every
  host value. Offline tests accepted four valid states and rejected 126 corrupt
  data/CSR/guard/terminal states, including contradictory PASS+FAIL and no exit.

| Source case | Spike instructions | Firmware checks | Checkpoints | Index setups | Faults / repairs / retries |
|---|---:|---:|---:|---:|---:|
| d32m2_i64_fault_ov1 | 1595309 | 21595 | 50 | 50 | 1600 / 1600 / 1600 |
| d32m2_i64_resident_ov1 | 840319 | 5215 | 51 | 51 | 0 / 0 / 0 |
| d32m2_i64_fault_ov0 | 1595309 | 21595 | 50 | 50 | 1600 / 1600 / 1600 |

Every ordinary checkpoint checks original 32 values and both guards. Resident's
51st checkpoint checks the original VL17/start7/odd-mask/-7 background result.
All check VL32/vtype17/vstart0/fcsr117/vcsr5. Firmware additionally checks all
32768 source words, all input indices, final PTEs, counts, original exit and magic.
The raw firmware strings are the exact original VECTOR_PASS plus one
INDEXED_ORIGINAL_PASS; Spike exits successfully with tohost=1 (success encoding).

## ELF And Target PCs

Paths below are relative to this directory, with no compilation needed for a
future authorized replay:

| `reference03/<case>/soc.elf` | SHA256 | Original target PC / opcode |
|---|---|---|
| d32m2_i64_fault_ov1 | `5a73bf57dc9d9cef6136ec8daa53e409c77abd5e0e47645d403392df5310347f` | `0x80000d64 / 0645f207` |
| d32m2_i64_resident_ov1 | `85b1da567120fba1d04f2ec11ab6abc5d1898970c55550ed440b1ddc7cf276df` | `0x80000cf0 / 0645f207` |
| d32m2_i64_fault_ov0 | `1c1c653af2c745964b80b7bcc50a9d7c9fb06aaae8c90e6c1d50b57f43c810ad` | `0x80000d56 / 0645f807` |

The non-overlap PC really is `gather32+26`: verified against every reference02
and reference03 SoC disassembly, not inferred from a changed expectation.
Use each ELF's `.symbols.json` and `.dis` for all observer PCs.

## ISA, Layout And Runtime

Spike ISA is exactly `rv64gcv_zfh_zvfh_zvl1024b`; privilege `msu`, pmpregions0,
memory2MiB. Compiler ISA `rv64gcv`, ABI lp64d, mcmodel medany. Runtime expects
VLEN1024/four lanes. No floating-point instruction is introduced by the fixture;
fcsr117 and vcsr5 are sentinel state that must remain unchanged.

Code/data retain the proven S-mode 0x80000000 identity mapping. Indexed virtual
base is 0x40000000, extent0x20000 (32 pages), each leaf is read-only. Code, pages,
logs and stack fit the existing 1MiB L2 linker map: SoC BSS ends at 0x80040030
(fault) or 0x8003f030 (resident), far below the reserved 64KiB stack boundary.

Preparation copied `/tmp/current-board-integration-fast01/prepared` runtime
inputs. Their copied bytes independently match both the live originals and that
directory's provenance.json:

| File | SHA256 |
|---|---|
| startup.S | `3ab886ee55bf807790e0c17e982d3142e5207f317bbde593d2b5d8cc4f151582` |
| runtime.c | `91aecf556bf3f17f1e3b21241099c81fdca2e624eff3a1a37986dc9629dae5db` |
| replay.ld | `6478bcdc036d6fa64beec95c51748e4778a2e0c49a74efcabc0fdb537ad3a82a` |

The finished ELFs have no runtime dependency on `/tmp`. Re-running preparation
does depend on that retained directory and the pinned compiler/Spike/imported
helpers. New tests did not edit any imported helper. M/S transition plumbing was
adapted from the proven NF2 fixture; original C uses a local RV64 Linux-compatible
rusage header rather than newlib's incomplete structure.

## Trap Replacement Boundary

The original C and ASM math, sequence, loop count and oracle remain intact.
The adapter substitutes Linux syscall services, mapped VA, demand-page policy
and M/S entry/return, with extra scalar checks around helper calls. Each fault
round initially invalidates all 32 PTEs. Handler checks the true target opcode,
records PC/tval/vstart/CSR, repairs only that page, executes addressed SFENCE and
returns to **unchanged mepc without any vector operation or index/CSR reload**.
That produces starts0..31 each round in Spike; it is intentionally not a claim
about Linux's observed 150 minor faults or unknown ov1 failing round/start.

reference01 failed to compile only because newlib lacked ru_minflt. reference02
fault/ov0 exposed an unaligned scalar opcode read in our handler (PC only
2-aligned); four volatile byte reads fixed it. Both old failures are preserved.
No expected value, original instruction, 50-round bound or fault policy was
weakened to obtain reference03 PASS.

## Cost And Next Gate

Using the parent's measured M5 rate **723 retired instructions/s** as an estimate,
not a guarantee: fault cases are about **2207s / 36.8min each**, resident about
**1162s / 19.4min**; serial total about **92.9min**. Real trap/MMU/vector latency
and host contention can differ. A proposed later budget of 7200s per fault case
and 3600s resident remains below the user's 3h-per-ELF ceiling and does not reduce
any oracle. Outer service must additionally allow observer/teardown time; no
service or scheduler is prepared/launched by this reference task.

Before a pilot, implement/review the dedicated real CSV observer described in
`VCS_CHECKER_BOUNDARY.md`, pin the selected image and original SoC ELF, and review
resource admission separately. Existing Spike checker is **not a VCS checker**:
faulting targets may not retire in CVA6 CSV, and vector memory/VRF data are not
directly exposed there. Full scalar result/checkpoint and trap records transfer;
precise partial-write/snapshot epoch evidence requires `PROBE_PLAN.md` signals.

Current evidence neither proves nor disproves the historical failure in current
RTL. Snapshot-valid clearing is not independently a root cause. No DUT PASS or
full original Linux closure is claimed.

### Independent Review Qualification

The preparation checker is not a complete independent instruction/CSR ledger:
it checks target-attempt counts and matching retry PCs, but not the complete
per-round target-PC/opcode list or every `io_retry_mret` event. Final round/minor/
map/unmap/check totals are checked by firmware, not all independently asserted
by Python. Its memory reader defaults missing bytes to zero. The 126 negative
tests exercise checkpoint/terminal values, not omissions in a full trace.
These limits do not turn the firmware/reference result into DUT acceptance.
The future CSV observer must independently validate those ledgers and require
observed memory bytes, and test missing/duplicated/reordered events. Do not
modify reference03 artifacts or silently present its checker as that observer.
