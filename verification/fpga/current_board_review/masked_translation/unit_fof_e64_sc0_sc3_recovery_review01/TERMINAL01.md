# Final Metadata Review

**ACCEPTED: two M9 source-derived architectural results recovered offline.**
The original batch remains NOT_ACCEPTED_LATE_ABORT; this is not a successful
replacement worker execution or Linux-family closure.

| Case | Child rc / seconds | Full checks | Required owners | Returned VL / post-helper VL |
|---|---|---:|---:|---|
| e64/sc0 FOF | 0 / 246.556700 | 5477 | 4 complete | 4 / 8 |
| e64/sc3 alloff ordinary | 0 / 246.998061 | 5481 | 4 complete | 8 / 8 |

- External audit receipt: PID2756457, actual wait0, no timeout,
  24.275941688s. It binds the approved command/review and exact result hash.
- Unique closed-CSV pass totals333389 rows,333181 retirements,10958 checks,
  4 checkpoints and8 memory owners (6 non-target helpers). Each owner's
  nonempty allocation/completion list, response and retirement are present.
- Immediate VL is also retained in the saved a0 values4/8; both completion
  contexts show post-helper VL8/vstart0. All16 handler restores are recorded.
  Only sc0 final out[5..8] is undefined; sc3 has no exemption. Full original
  defined data/guards,130-element allocation,8KiB data,12KiB page tables,
  mask16 and CSR checks are preserved. Both actual SoC exits are CTRL0,
  with no target architectural exception.
- The936-entry pin ledger includes every original894 plan pin unchanged.
  Metadata-only review matched per-case result files, generic summary
  extents, CSV hashes recorded in the ledger, actual child/monitor receipts,
  reviewed checker hashes, and original failure/service files. The audit's
  pre/post full-pin verification is retained, not falsely described as a
  new936-file rehash by this reviewer.
- Both old strict results retain error8; original complete remains aborted
  NOT_ACCEPTED_LATE_ABORT and actual systemd exit remains exited/1/exit-code.
  No CSV, reference or Host rerun was performed during this final review.

## Bound Evidence

Paths below are relative to sibling
`unit_fof_e64_sc0_sc3_checker_recovery01/`:

- `closed_audit01/result.json`: `f85942d662bab18098147cef3606fd38cc9755ba982ab1c18fa6201cb0eb892e`
- `audit_process01/execution.json`: `0d4c1e6f77d9530965429d4895fb10bdd541238ee9311f79040a915f9d84b5df`
- `closed_audit01/pins_before.json`: `6f6a4f705c826013f5845807fa3723aa159888c5175ff517c865e58342eaf41a`

Preserved original worker `prepared01/` evidence:

- `complete.json`: `8485ce6f99dd052d4e2aad6b726c87e19666992138ba1495130298eaa4c1d696`
- `service_exit.json`: `9c0a896076328dcb52c22335eb30273acb8152cc9ac6c8285be5938898d46dcd`

Independent metadata check exited0 (tool chunk e68e43,0.451632034s).
No new runtime admission layer is introduced. This review closes the two
selected-source result audit only, not all original scenarios or zero
physical MMU/AXI activity.
