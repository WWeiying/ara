# Two NaN singles: reference terminal entry review

Decision: **ACCEPTED FOR THE TWO SEALED SOURCE-SINGLE VCS INPUTS, NOT DUT PASS.**
No blocking finding in the scoped metadata/source/ELF/pin review. This is not
an independent full-raw revalidation. No reference, Host suite, compiler, or
DUT was rerun; no full raw log or CSV was opened. Structured ledgers and the
small captured-witness negative-test records were inspected.

## Identity and actual outcomes

READY: `../nan_minmax_soc_prepare01/observer_recovery01/complete01/READY.json`

SHA256: `11cc4d306bdc5a37976d13eca3ec164ab597b42406e47c294ba714ef8bcf7cfc`

| Single | Original fixture bank/row, zero-based call | Mask / VL | Result | Spike actual rc / seconds | Offline parser PID / rc / seconds |
| --- | --- | --- | --- | --- | --- |
| call1294 | 1 / 647, call1294 | 0x24 / 3 | 0x7fc00000 | 0 / 2.974907114636153 | 1653767 / 0 / 44.46225466718897 |
| call1234 | 1 / 617, call1234 | 0x00 / 3 | 0x7fc12345 | 0 / 2.9749113894067705 | 1654180 / 0 / 42.64747465401888 |

call1294 is an offline recovery of the original run, not a second Spike run.
call1234 is its previously undispatched initial run (Spike child PID1654128).
Both actual numeric exit receipts have timed_out=false; each parser's numeric
wait result is persisted before postchecking and binds its exact command hash.
Receipt `validated:false` labels the low-level unvalidated receipt, not a
nonzero process outcome. No service/GC exit status was inferred.

Both references use `rv64gcv_zfh_zvfh_zvl1024b`, the pinned Spike binary, and
the same 3,000,000-step / 256 MiB raw-file / 120 s limit. Both ledgers record
1,857,110 firmware instructions, 1,860,000 total commits, 2,885 park commits,
HTIF value 1, and the exact one-case original PASS console without diagnostics.

## Source and oracle

Canonical archive: `ara_hw_campaign_20261007_01/rvv_fp_redspecial03`, e32/m1,
not an alternate reduced fixture chain. Current source hashes match its
manifest for the five original C/input/fixture/generator sources.

- Original C SHA: `f92ffb3af070febf3dfebb85b0a25f6c5612b95044e2aa1262d600687926eb4f`.
- Original Linux ELF SHA: `6bdf00a1600f10ebfc7a8b519bfea655d31e6b6b2b62d89f9e459d266eb597bc`.
- Removing the single selector exactly restores original C. Only the Linux
  entry/I/O/exit wrapper is adapted; the scalar scenario loops and full oracle
  body match byte-for-byte. All archived helper/fixture copies match.
- Both use op2, **vfredmax**, SEW32/m1, CAP32, scenario1, length slot3, frm0,
  sticky0. call1294 has only element2 active; call1234 is all off. The source
  seed/input payload is quiet NaN 0x7fc12345; independent bitwise max semantics
  agree with the selected original fixtures. Both expect flags0, not NV16.
- Verified actual ELF bytes for all three 21-instruction helpers against the
  original ELF in both SoC and Spike binaries: 12 ported helper windows total.
  Each ledger has one contiguous op2 window, actual PC/encoding matched to that
  ELF, and zero visits to every PC in the two unused helper windows.
- Each structured ledger preserves 144 ordered output-byte reads, including
  128-byte destination and both 8-byte guards, plus input256/seed512 element
  initialization, 215040 mask-byte stores, and 6720 fixture-field reads across
  the original 3360 fixture rows. This is not 3360 executed helper calls.

The delta fix is exercised by actual ledgers: index10 explicit fflags=0 and
a7=0; index11 has vstart=0 with no fflags event; index13 actually returns x6=0.
Saved frm/fflags are zero and restoration instructions/writes are present.
No missing CSR event is defaulted to zero. These reference CSR records must
not be promoted into evidence of future DUT CSR state or post-restore readback.

Each producer single-pass extraction reports 12 negatives using captured
actual raw-line effects plus 33 complete-ledger negatives. Their recorded
mutations and relevant rejection reasons were checked, not rerun. Independent
full-stream completeness still relies on the reviewed sealed extractor and its
bound exit/result records; this review did not independently rescan raw.

## Pins and review execution

100 producer pins match pre/post byte-for-byte; all 15 READY result pins match.
The union with sourceproof/admission pins and actual attempt/exit/execution
receipts contains **121 independently rehashed non-raw files**, unchanged at
the final check. Original checker and STOPPED hashes remain those in
`CSR_DELTA_REVIEW01.md`. The reviewed successor remains SHA
`783ca239cc93e90dc6579f75ed7f6cc92cd59bce9a1820dbf31ddd08d40f9958`.

Raw identity is cross-checked between execution metadata and architectural
results; file byte counts match stat and the resource bound. Raw hashes were
not independently recomputed, to honor the no-full-raw-read restriction.

Read-only independent metadata/source/ELF verification command: inline
`python3 -B`, tool output chunk `74f230`, actual exit **0**, elapsed **9.53963116 s**.
It did not import or execute the producer checker. This is a metadata-review
exit, distinct from the recorded Spike/parser exits above.

## Direct VCS handoff

Use only these two existing SoC ELF files, with at most two workers. No source,
ELF, oracle, or reference rebuild is needed. A separate VCS plan must still bind
its actual image, runner, full oracle, and durable outcome gates. This report
does not launch or accept a DUT run.

| Relative to nan_minmax_soc_prepare01 | SHA256 |
| --- | --- |
| call1294/soc/program.elf | f9f3950cb84244d964747c45482d73f7d960270095cbd309a2b956460cf56275 |
| call1234/soc/program.elf | b93e81cc92e625c04094f67531d2aa8ad2a6bb7c3c3b4947478310cec737e28d |
| call1294/spike/program.elf | d300332635aa8352391f9b7d4bfaf84e3bdcf6af9e182500e650fbb235aeb1d9 |
| call1234/spike/program.elf | 5d2742d6379d39d31454d473ddca69eb1f39e586024437f7ff9bf642c4048a01 |
| call1234/reference01/actual_exit_unvalidated.json | 800a2fec448b774eff4a268b6dfa9b8676acb48411fc9f485837e9b7988f809d |
| call1234/reference01/execution.json | 1ea6789ac7b537a225a6cd2f1326ec07a453a78ed8795908d777d160d9c1ae16 |
| call1234/reference01/ATTEMPT_STARTED.json | 887dacdec419261bfa263ea3cde1a4b6ed6a51def86eb2544b5e62d590d99f8d |

The newly generated call1234 process receipts above are additionally bound by
this review; downstream handoff should pin them with READY and its result pins.
Scope is two selected source-faithful singles, not the preceding helper-call
history, full Linux parent, all min/max operations, or a DUT closure.
