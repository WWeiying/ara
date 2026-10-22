# Parent-Reported Fixed2 Startup

Status: STARTUP_CONFIRMED_BY_PARENT; not a terminal result or acceptance.
This note is outside the sealed plan/input pins. No process, service, CSV,
or simulation polling was performed to produce it.

Parent reports launch after Averroes review, with approval SHA256 prefix
`9b3d7727...` (full hash not supplied in the startup message). The actual
FPmerge unit is `ara-fp-merge195-candidate04-01.service`; parent corrected
the proposed unit only in a new approval file, not the sealed template.

- Fixed service: `ara-fixed-boundary-candidate04-01.service`.
- Service runtime limit: 2400 seconds; jobs2, 1800 seconds per program.
- Parent confirmed both processes use the correct M4 executable, expected
  service cgroup, and separate private working directories.
- Output directory: `candidate04_run01/`.

Parent's two-second progress observation:

| Selection | simv PID | CSV cycles | Retire count |
| --- | --- | --- | --- |
| SINGLE776 | 179250 | 35015 -> 36614 | 28706 -> 29991 |
| PAIR775-776 | 179251 | 40261 -> 41991 | 31922 -> 33281 |

These observations establish startup and forward progress only. Neither
selected-case PASS nor full-prefix777 acceptance is claimed. No duplicate
launch, polling wait, additional preparation, or sealed-file change is
authorized by this note. Further vsmul source-path analysis is conditional
on an actual case failure.
