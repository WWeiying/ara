# M9 Alignment4 Architectural Acceptance

**Accepted scope:** the four directed e64/VL2 unmasked-strided alignment/retry cases,
combining two independently recovered M-mode closed CSVs with two fresh Sv39 cases.
Controls16 remain separately accepted and reused. This is not an original Linux
campaign closure and does not turn the old failed batch into a successful batch.

## Fresh Sv39 Terminal

Actual `prepared01/complete.json` status `PASS_M9_SV39_ALIGNMENT2_ENDPOINT02`:
`aborted=false`, `retries=0`, `firstfailure=null`, `pins_unchanged=true`; exact two
members and actual runner `COMPLETE/PASS2`. No firstfailure file exists.

| Member | Actual simv rc | Actual checker rc | Seconds | Full checks | CSV / retired rows |
| --- | ---: | ---: | ---: | ---: | ---: |
| load_sv39 | 0 | 0 | 50.996679 | 697 | 26662 / 26488 |
| store_sv39 | 0 | 0 | 54.866306 | 698 | 26445 / 26271 |

Each durable child receipt has `timed_out=false`, `failure_seen=false`,
`abort_set=false`. Private ELF, original runtime name/command, frozen M9 image and
actual endpoint02 checker invocation match. Actual raw console/run logs satisfy
the unchanged success and first-error veto. Generic trace summaries are VALID;
their full row/retire/last-cycle counts match the saved strict-checker outputs.

Both saved full-checker results establish nine memory owners/seven non-target
helpers, allocation/completion for every owner, precise cause4/load or cause6/store,
vstart1, same-PC retry, completed prefix/poison preservation, subsequent different
owner, complete data/guards/page-table oracle, S-mode ecall cause9/vstart0 and all14
restore CSR readbacks. Each has exactly one actual CTRL exit: PC0x80000072,
insn0x00a2b023, address0xd0000000, size8, value0. Last cycles39861/39874.

## Metadata Audit

`terminal_report01/check.py` verified **1262 input pins + 37 terminal evidence pins**,
plus report/launch/review bindings: **1306 unique pins**, unchanged before/after.
No CSV semantic reparse, simulation, reference or build was performed; CSV bytes
were read only to verify their existing cryptographic hashes.

Actual command:

```sh
python3 -B verification/fpga/current_board_review/unmasked_strided_alignment_soc_m9_sv39_worker03/terminal_report01/check.py
```

Actual external tool completion `a402c5`, exec session68898, **exit0**. This is the
metadata audit's exit, not the original service's exit. Its `result.json` binds all
consumed pins, exact member summaries and reuse identities.

One systemd observation returned `LoadState=not-found`, inactive/dead/MainPID0,
empty start/exit timestamps (`af2bbf`). The original service's historical numeric
exit is **UNKNOWN**, not independently observed0. Default Resultsuccess and
ExecMainStatus0 are not exit proof. The explanatory GC wording in `result.json`
does not prove successful service exit; only absence was directly observed.
The actual simulator and checker process exits above are durable independent facts.

Zeno's independent combined terminal review:
`../../unmasked_strided_alignment_repair_zeno01/M9_ALIGNMENT4_TERMINAL_REVIEW03.json`,
SHA `6cc579ffcd3cb0f6eab47e7bc2aed1c3680705a2ce8db674bcb7c789e951c6f2`.
It accepts the directed architectural scope with the same historical-service-exit
limitation and without another CSV semantic traversal.

## Combined Evidence

- M-mode: endpoint02 `closed_audit01/result.json`,
  SHA `fb29028a4ede5c7e07f1814cf6bba68d5c839ad65f4042729c32f25dd1844439`;
  accepted697/698 checks, 47963 CSV rows, 47615 retired rows, actual simv0 receipts.
  Independent review `M9_M_MODE_ENDPOINT_REVIEW02.json` SHA
  `f4b3881522b500a9426698d2a4a676409045576e7d0ba37c67c459bbd918ba69`.
- Sv39 terminal SHA
  `94bc640976165a60b4303572d348290121444b7f3b52397fba3790bcd5372ab9`;
  1395 checks, 53107 CSV rows, 52759 retired rows, actual simv0/checker0 for both.
- **Alignment4 total:** 2790 full checks, 101070 CSV rows, 100374 retired rows,
  36 memory owners/28 helpers and56 actual restore readbacks.
- Controls16: independent audit SHA
  `1e8a3e7ccfd3ae5a0b384be80c5a00285921aebd94dea6ccd0cc3d5bcc32db4d`;
  all16 accepted, full310350 cycle-event rows unchanged from M8. Not rerun here.

Old `unmasked_strided_alignment_soc_m9_worker_successor01/prepared01/complete.json`
remains `NOT_ACCEPTED_LATE_ABORT` with the original checker `tohost` error and null
adapter metadata. No old result, fixture, sealed helper or RTL was modified.
