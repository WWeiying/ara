# Final03 Successor e16 Timeout Review

Read-only review of the completed `final03_successor01` artifacts. No simulation,
build, timeout change, script change, or production RTL edit was performed.

## Conclusion

`matrix_e16` is not stuck in a comparison case. All 102 calls to `run()` returned
zero errors, and the console contains `MATRIX_PASS sew=16 cases=102 errors=0`.
The 600-second wall-clock limit interrupted the subsequent wrapper PASS-message
output. Architectural retirement continued through the last recorded cycle.
This supports normal execution exhausting the wall-clock budget, not a fixed-case
deadlock. It does not identify the host-side cause of the elapsed runtime.

The runner result remains **TIMEOUT (600.1578627061099 s)** and the successor
overall result remains **FAIL**. The complete `BOARD_CASE_PASS`/exit handshake was
not observed; numerical-oracle completion is not a whole-program PASS.

## Evidence And Method

Paths below are relative to `verification/fpga/current_board_review/`:

- Status: `extension_overlap/final03_successor01/status.json`.
- Console and CSV: `extension_overlap/final03_successor01/matrix-e16/tests/matrix_e16/{console.log,commit_trace.csv}`.
- Executed ELF: the same directory's `input.elf`.
- Source/disassembly: `comparison/matrix.c` and `comparison/soc_matrix/matrix_e16.dis`.

The CSV was scanned in file order, reconstructing integer registers from each
`retire` row's `rd`/`rd_wdata`. Calls were counted at `run` entry PC `0x80000108`,
with arguments a0/a1/a2/a3 (op/kind/side/mode); returns were counted at its common
`ret` PC `0x800005b0`, sampling a0 as the error count. There were **102 entries,
102 returns, and no nonzero return values**. These are architectural retire
observations, not backend maintenance/handshake counts.

| Trial (zero based) | op/kind/side/mode | Entry cycle | Return cycle | Errors |
| --- | --- | --- | --- | --- |
| 99 | 3/2/1/5 | 469018 | 473728 | 0 |
| 100 | 0/1/1/6 | 473763 | 499311 | 0 |
| 101 | 0/1/1/7 | 499324 | 524645 | 0 |

Last successful trial: **101 (the 102nd case)**, VMFEQ, sNaN in source B/v16,
mode 7, count 272, VL 269, vstart 0, sNaN at masked-off index 261, preexisting
sticky flag 1. This checks the masked exception and full data/setup oracle.
Trial 100 is its active-sNaN mode-6 counterpart. **First unfinished trial: none.**

The final vector inspection store (`0x02b60027`) completed at cycle 506625.
The remaining scalar oracle finished at cycle 524645. Matrix-main returned
a0=0 to wrapper PC `0x8000009c` at cycle 525405; PC `0x8000009e` then took the
success path. At cycle 525431, PC `0x800000c0` called `replay_text` with
a0=`0x80000888`, the wrapper PASS string.

The last retired instruction was cycle **525503**, order **396512**, port 1,
PC **`0x80000760`**, compressed instruction `0xbfcd`, `j 0x80000752` in
`replay_text`. The preceding same-cycle retirement at PC `0x8000075c` stored
`0x41` ('A') to UART address `0xc0000000`. The loop consists of lbu, conditional
branch, pointer increment, sb and jump; this is productive string output.
The last eight UART byte-store retirements were:

| Cycle | 525454 | 525461 | 525468 | 525475 | 525482 | 525489 | 525496 | 525503 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Byte | B | O | A | R | D | _ | C | A |

Reconstructing retired UART stores gives a tail of
`MATRIX_PASS sew=16 cases=102 errors=0\nBOARD_CA`; console output stops at `BOA`.
Retired stores and UART console visibility are distinct observations. Neither
shows a comparison loop or an unfinished trial at the timeout boundary.

## Final04 Risk (Report Only)

At the inspected final04 campaign status snapshot, `comparison-matrix` was
PENDING (the pipeline had progressed to `combined`). Its recorded plan uses the
same `comparison/soc_matrix` ELF set, jobs=4, a 600-second per-ELF limit, and a
720-second stage limit. This is not a prediction of final04's eventual result.

The identical e16 ELF has now demonstrated insufficient completion margin at
600 seconds even with all 102 oracle cases successful. Therefore another
wall-clock truncation is a concrete risk, not evidence that a particular trial
must be skipped. Parallel execution can change wall-clock timing. e32 completed
in 337.65477327117696 seconds in the successor, so that run supplies no analogous
600-second cutoff evidence for e32.

`integration/run_pipeline.py` rejects any required non-PASS case and marks later
PENDING stages NOT_RUN on failure. In final04's order, `extension-matrix` follows
`comparison-matrix`; an e16 timeout can prevent the six extension groups from
running. Parent coordination before that stage is warranted to avoid repeating
a known budget-bound failure. No cancellation, limit increase, script edit, or
rerun is made or authorized by this report.

Other completed successor outcomes: flags_sequence PASS (39.176630111876875 s),
reduction-epoch/all PASS (22.159998056013137 s), matrix_e32 PASS
(337.65477327117696 s). These do not replace final04 acceptance.

## SHA256

- Executed e16 `input.elf` and `comparison/soc_matrix/matrix_e16.elf`:
  `36352972969effa9f606d097dd8e4407fda17f76978e00b0755c43e0baa35e63`.
- e16 `console.log`:
  `b3376a5f656ee454132c68a601f1e0b3454a716e9d8ef251b1cddda2a79edddd`.
- e16 `commit_trace.csv`:
  `9dcfe865cefae55a1fcc12627cf60fb818c1fe283ed3f060ffe0d66f002160b5`.
