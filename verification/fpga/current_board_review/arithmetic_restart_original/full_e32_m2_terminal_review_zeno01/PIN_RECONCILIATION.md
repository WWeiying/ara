# Pin Count Reconciliation

No unexplained omission: **903 - 46 + 16 = 873**.
Original plan contains903 pins. The actual entry JSON also binds exactly903
identical pins; its reported902 is the number it freshly rehashed, plus one
accepted source-reference raw pin bound without rereading.

The terminal review freshly verified857 nonraw files from that plan and16
additional terminal/approval/review files. It deliberately did not rehash
the following46 original-plan .log paths:

| Category | Count |
| --- | ---: |
| Native original compile.log and case0..11.log | 13 |
| Native packed compile.log and case0..11.log | 13 |
| Six native negative compile.log and case0.log pairs | 12 |
| SoC/Spike compile.log and size.log | 4 |
| Reference-entry host.log | 1 |
| Reference01/commits.log (source raw) | 1 |
| Worker Host01/Host02 logs | 2 |
| Total excluded original-plan paths | 46 |

Therefore entry902 rehashes =857 nonraw +45 logs; its remaining one bound
pin is reference01/commits.log. The terminal report's full excluded list49
also includes three NEW DUT evidence files, not present in the original
plan: console.log, work/run.vcs.log, commit_trace.csv.

The16 NEW verified nonraw files are entry result.json; plan, complete,
collector_result, collector_exit, service_exit, launch; replay run/summary;
private ELF, inputs, command, numeric child outcome, strict report, trace
summary; and the independent review script. Full absolute path lists and
each recorded hash appear in PIN_RECONCILIATION.json.

## Actual Inherited Evidence

- Entry: A/e32_m2_block_m9_entry_review01/result.json,
  SHA48f1a47e394ce576834a13104e5ece06a76250a02ef7d1c396c7a410411984ec,
  actual NO_BLOCKER_ENTRY_REVIEW, binds all903 plan pins.
- Producer: prepared01/complete.json,
  SHA6508b05ce26eee26eb78ed7567981582767271a0b1a0a3b73c7b9fcb68d5a596,
  actual whole PASS, pins_unchanged=true/noabort/retries0. Its evidence_pins
  bind all12 execution artifacts including console/runlog/closed CSV.
- Collector: prepared01/collector_result.json, actual ACCEPTED,
  pins_pre_post_unchanged=true; the sealed collector validates original
  plan, execution evidence and approval pins, plus the closed raw hash.
  Actual service and collector exit0 receipts were checked by REVIEW.json.
- Closed strict report:
  SHA35fa3fe257b87a5ab5e1ea3c6d9fed7ad2359f449d30795fe081d8212e0db33e.
  Its actual_csv_sha256, producer evidence pin and collector csv_sha256 agree:
  db817855d318e88e951e65fba0ebc06f6f707adbaa3e8a3359080db7cf1407aa.
  The strict/generic report binds the one completed raw parse; this review
  did not run a second parse or reread raw to manufacture independence.

Thus873 means873 fresh nonraw hashes plus explicitly inherited raw/log
chains, NOT903 independent fresh hashes. All903 original-plan paths are
accounted for; unexplained_plan_omissions=[].
This addendum only reads small JSON manifests and hashes small metadata.
It does not modify the original REVIEW/plan/entry or the event observer;
e64/m2 inotify remains untouched, with no progress query.
