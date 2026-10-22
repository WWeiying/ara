# Full Original E16/MF4 Reduction Software

Status: original-C Host comparison and one fixed SoC/Spike compilation each
completed. Linked successful-path cost is below 3M. No Spike execution, VCS,
RTL change, or full-parent architectural acceptance is claimed.

## Source and Scope

- Original parent: `rvv_fp_redspecial_e16_mf4`, canonical
  `rvv_verified_handoff03/rvv_small_redspecial02/rvv_small_fp_redspecial_e16_mf4`.
  Original ELF SHA256:
  `0e20bf3cf1449d2d4ce4b9dbf482d107154966554031bcd02cd35f9008e282ec`.
- Full source: original `fp_reduction_oracle.c`, SHA256
  `f92ffb3af070febf3dfebb85b0a25f6c5612b95044e2aa1262d600687926eb4f`.
  `execution01/sourceproof.json` and `software/source.diff` record the canonical
  selected-scenario relationship and complete-parent scalar/runtime changes.
- Original order remains 8 scenarios x 7 VLs x 4 masks x 5 rounding modes x
  3 operations x 2 sticky values = **6720 contiguous calls**. Operations are
  ordered sum, minimum, maximum. No partition reset or skipped predecessor.
- Both original fixture banks remain linked, with all 6720 bank entries checked
  against the archive. VLEN1024 uses bank1; row1545 is `0x7e00/NV16`, not bank0's
  `0x7c00/0`.
- All three original 21-instruction helpers and capacity3 match unique original
  ELF byte sequences. No added vector or FP instructions. Helpers load m1 seed
  and destination and store **128B**, regardless of fractional source LMUL.

## Preserved Oracle and History

Each scenario initializes only input[0..15] of the original 1024B backing;
the remaining bytes retain startup BSS zero. Each scenario initializes all
64 halfword seed values (128B). Each original operation row initializes the
64B mask once, reused across its two sticky calls. Each call initializes and
checks **all144 output bytes**, including both 8B guards, and retains the
original combined status/vstart/flags error, `flags_seen` OR, CSR save/restore,
and `errors < 20` diagnostic condition.

Totals: 967680 output-byte comparisons, 6720 flags, 6720 vstart checks;
128 input SH, 128 seed SD, 26880 mask SD, 120960 output SD and 120960 output LD.
There is no invented per-call input refresh. The scalar fast comparison ORs
word XORs; any mismatch executes the literal original byte-error loop, so
multiple errors cannot cancel or change DETAIL eligibility.

## Actual Host and Compilation

`receipt01/supervisor.exit.json`: actual wait0, no timeout, 7.242454s.
`execution01/host/RESULT.json`: nine full original/packed transcript pairs
(positive, byte, status, flags, mixed, diagnostic boundary, VL0, wrong bank,
wrong NaN), plus four missing-write/read negatives correctly rejected.
The positive Host also checks all 967680 single-byte corruptions locally.
Host operations use the unchanged archived fixture; the independent expected
error accounting is the original C, not a new generated FP model. This tests
the scalar adapter/oracle, not hardware floating-point execution.

Both target compiles ran exactly once, after Host success, with fixed existing
non-ZCC GCC flags and `rv64gcv_zfh_zvfh_zvl1024b`; no flag tuning or retry.
Full commands and numeric child receipts are in `execution01`.

| Backend | ELF SHA256 | Conditional whole-positive upper |
| --- | --- | ---: |
| SoC | `5242911cb3a64d2bab02be8babdad363d75796a5f25dd351b82706c6279aca7c` | 1138255 |
| Spike | `0326cc068509dd6a42a8840426de99fd251dcefe04e552bda5135c36040c7d1e` | 1142355 |

`linked01/RESULT.json` and backend reports: every source-function instruction
classified, all source-derived branch weights flow-conserved, actual ELF bytes
and switch-table edges checked. Source CFG975572 + original helpers141123 +
seed-index memcpy1816 + startup upper800/4900 + printing/wrapper upper18944.
The largest source blocks are full144B comparison362880 and output/setup/
helper-return329280. No failure path is assumed to have this successful-path
bound; these are not measured retired counts.

Source frame368B; normal nested maximum432B with 64KiB stack reserve.
Image through BSS: SoC111992B, Spike120448B, within 1MiB.
`cfg_receipt01/supervisor.exit.json`: actual wait0, no timeout, 1.570506s.

## Minimal Next Reference

Pending authorization and a case-specific strict reference adapter only:
reuse the exact current Spike ELF and established golden profile
`rv64gcv_zfh_zvfh_zvl1024b`, VLEN1024/ELEN64. One finite `rs 2000000; quit`
invocation, 120s wall bound, 512MiB raw bound, no retry. Persist actual child
wait status before checks. One closed-raw audit, bounded600s, must verify all
6720 original calls/fixture selections/21-instruction windows, actual memory
extents and values, CSR/status/flags, all144B per-call oracle, original console,
successful HTIF exit and pure post-exit parking. Budget exhaustion is not PASS.

The estimated Spike path is1.142M, leaving about858k instructions below this
proposed finite reference limit. Neither this estimate nor the earlier selected
M6 single is full-parent reference/DUT acceptance. No new software compile,
large Host rerun, generic framework, or RTL build is needed for that step.
