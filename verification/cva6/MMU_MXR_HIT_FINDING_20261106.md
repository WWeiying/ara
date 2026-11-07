# CVA6 MXR DTLB-Hit Permission Finding

Date: 2026-11-06. Disposition: permission bug reproduced; RTL repair awaits
explicit authorization. No RTL changes, new EDA, or commit were made for this
archival review. This finding does not stop the separate flat-RAM performance
queue or establish a 256-bit-specific regression.

## Authoritative Evidence

Evidence root: `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out`.
Paths in the following table are relative to that root; SHA values are SHA256.

| Record | SHA256 |
| --- | --- |
| `e2e_mmu_mxr_hit_20261106_01/result.json` | `8771ee9dfab61462182af057afbcaa700f11dd9749c8d57334c7d8445c5105ea` |
| `e2e_mmu_mxr_hit_checked_20261106_01/result.json` | `8e4379df0c7e2e40a40d6db549532703c82b8c2f7a071f713cc0d89c028fb636` |
| `e2e_mmu_mxr_hit_checked_20261106_01/sim/console.log` | `cce38cd92553eadeb35d31cbfbe7db41261c56f586fc90449b323f4a37311f40` |
| `e2e_mmu_mxr_hit_host_audit_20261106_01/result.json` | `96c824e8818e2e9439d79c8a6cc986aa633f3506b0e88fc86d06f4a16e66e930` |
| `e2e_mmu_mxr_hit_host_audit_20261106_01/audit.json` | `c60f902d266b4b0465a3a2cdd4f5e7fddc515ee3c0e2577227b506b73aed1e50` |
| `e2e_mmu_mxr_hit_host_audit_20261106_01/source-pins.json` | `c9474a2605bea2f31110323f96c744fc873d5b83d05132f7abb374d928086546` |

The host receipt state is `MMU_MXR_HIT_PERMISSION_BUG_REPRODUCED`, with
`rtl_functional_status=FAIL` and `verified_coverage=false`. Both original worker
states remain FAIL. The archive verifies 80 input pins and four audit artifacts,
including all 45 checked-worker pins, 28 artifacts, and three compiled image
files; it also verifies the first worker's 42 pins and 22 artifacts.

## Observation and Scope

The DUT is the actual frozen SoC `cva6_mmu.sv` and its config/dependency copies
from `e2e_physical_wide_soc_inputs_20261106_01/source`. MMU SHA256:
`3e3f19db1ef8d3526c2e5e751c89ce923244a4ae7be617144d523c6c6480d431`.
The fixture uses Sv39, S-mode loads, RVH=0, NrPMPEntries=0, and no shared TLB.
It injects two legal PTEs only at `dut.update_dtlb`, then releases that refill
input. Lookup outputs and latched PTE outputs are not forced. MXR is driven at
the MMU input, not through an executed CSR instruction. No TLB flush occurs.

| Case | PTE / MXR | Expected | Observed |
| --- | --- | --- | --- |
| 0 | Readable / 0 | Allow | Allow |
| 1 | Readable / 1 | Allow | Allow |
| 2 | Execute-only / 1 | Allow, warm real hit | Allow |
| 3 | Same execute-only / 0 | Load page fault | Incorrectly allowed |
| 4 | Same execute-only / 1 | Allow again | Allow |

Every case observes lookup hit=1, latched hit=1, request=1, valid=1, and the
expected VA, PA, and latched PTE. Case 3 retains PTE `0x20008049`
(V=1, A=1, X=1, R/W/U/G/D=0), VA `0x40001108`, and PA `0x80020108`.
The only three mismatches are `exc: 0 -> expected 1`,
`cause: 0 -> expected 13`, and `tval: 0 -> expected 0x40001108`.
There are exactly 52 checks: ten per case plus drain-valid and PTW-count checks.
The observed PTW request count is zero. This is a real DTLB-hit permission
probe with interface-refill injection, not a cold-PTW, full-SoC, shared-reader,
AXI, PMA, nonzero-PMP, or CSR-write integration test.

In the frozen MMU, the PTW checks readable-or-executable-with-MXR at
`cva6_ptw.sv:471`, but the load-hit path at `cva6_mmu.sv:632` checks privilege
and canonical address without rechecking that read permission against current
MXR. The component observation confirms the hit-side defect; it does not by
itself demonstrate an end-to-end SoC exploit. MXR changes are required to take
effect without SFENCE.VMA by the
[RISC-V supervisor specification](https://docs.riscv.org/reference/isa/priv/supervisor.html).

## Preserved Failure History

The first runner accidentally used three `+incdir=` arguments. Its compile
failed before simulation. The typo and original FAIL are preserved unchanged.
`run_mmu_mxr_hit_checked.py` is an intentional, hash-bound successor wrapper:
it changes only those three arguments to `+incdir+`, retaining the bench, DUT,
functional checks, first-failure identity, and actual corrected argv records.
Total historical work is two compile attempts and one simulation. The checked
build took 16.16 seconds (300-second bound); simulation took 5.51 seconds
(30-second bound). VCS returned zero despite the deliberate bench fatal.

The second worker also remains FAIL: its original parser expected an unquoted
fatal filename and a separate `Scope:` line that VCS did not emit. The separate
host collector accepts only the actual quoted filename and inline scope at
bench line 164, immediately followed by the unique `MXR_HIT_CONTRACT_FAILED`,
then `$finish` naming exactly the same file and line. It requires exactly one
global `Fatal:`, the exact five observations and three mismatches, and the full
existing record order. It neither rewrites the log nor injects a `Scope:` line.
Acceptance means reproduced RTL failure, never design PASS or verified coverage.

## Historical Commands and Review

These are archival commands, not instructions to overwrite sealed outputs.
Working directory: `/home/wangwy/openproject/ara_dsa`.

```sh
python3 -B verification/cva6/run_mmu_mxr_hit.py --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_mmu_mxr_hit_20261106_01
python3 -B verification/cva6/run_mmu_mxr_hit_checked.py --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_mmu_mxr_hit_checked_20261106_01
python3 -B verification/cva6/collect_mmu_mxr_hit.py --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_mmu_mxr_hit_host_audit_20261106_01
python3 -B verification/cva6/test_collect_mmu_mxr_hit.py
```

The full raw VCS compile and simulator argv, cwd, return codes, elapsed times,
and bounds are preserved in
[checked commands.json](/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_mmu_mxr_hit_checked_20261106_01/commands.json).
The archived host command and test output are in the host-audit directory.

Archival review replayed all fields against `audit.json`, verified pins and
artifacts, and reran the 13 host tests successfully, without rerunning EDA.
Negative tests cover every observed field, wrong origin/line/finish, duplicate
fatal, missing/misplaced/duplicate reason, extra errors, mismatch noise,
missing/reordered/duplicate observations, source drift, and pin drift. The
parser is intentionally specific to this immutable record, including its
timestamp and whitespace; it is not a generic VCS log parser. No blocker was
found for this narrowly scoped finding archive. Frozen collector/test SHAs:

```text
collect_mmu_mxr_hit.py b93bf591cd83ea0d3ec020e4b81ea2c5e553de5081235aa33daa8aaf5ae7ad3c
test_collect_mmu_mxr_hit.py f57fd3da3b71c775fe95cb55e520607383f8dd4153efd02fa697227974830846
```
