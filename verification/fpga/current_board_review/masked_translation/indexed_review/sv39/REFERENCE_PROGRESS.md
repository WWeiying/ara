# NF7 Reference Preparation Status

Prepared only under `indexed_review/sv39/`. Production RTL, parent geometry and
helpers, all previous sealed inputs, and extended8 successor02 are untouched.
No VCS or Linux execution was launched by this task.

## Completed Measurements

Host C versus independent Python: **all 96 geometries PASS**, 467040 exact rows
covering configuration, scrambled indices, full vector gold/validity and both
entire data-page gold/validity arrays. Evidence: `reference01/host.json` and
`reference02/host.json`.

69 corruption negatives rejected, plus all96 full-tail membership and explicit
fault-field partial-commit validity checks. Evidence: `host_tests01.json`.

Full logged Spike reference PASS for the following **20 trials only**:

| Evidence | Original trials | Scalar comparisons | Spike commits |
| --- | --- | ---: | ---: |
| reference01/group00/status.json | 0..3 | 11924 | 1098601 |
| reference02/group01/status.json | 4..7 | 11694 | 933609 |
| reference02/group06/status.json | 24..27 | 12078 | 1099521 |
| reference02/group18/status.json | 72..75 | 12078 | 1128165 |
| reference02/group23/status.json | 92..95 | 11722 | 949106 |

Totals: 59496 matching comparisons and 5209002 Spike commits. These cover
ACCERR/MAPERR derivatives, load/store, all four mask modes, whole/partial field
page splits and alloff. They do not yet establish all96 Spike acceptance.
All on-device comparisons, phase checkpoint memory, precise trap addresses/PCs,
same-PC retries, full tails/guards, prefix poison, PTEs, CSR restoration, magic
and HTIF exit passed for those trials. No firsterror was observed.

## Remaining Reference Work

Service `ara-indexed-nf7-sv39-reference03.service` runs **only software host/Spike**
sequentially for the remaining groups:

`2 3 4 5 7 8 9 10 11 12 13 14 15 16 17 19 20 21 22`

These are the remaining 76 original trials, including the boundary3 cases.
It uses the same new fixture/oracle, no variants. Expected wall time is about
15-20 minutes from measured logged-reference cost; outer RuntimeMaxSec=3600,
each Spike invocation has a 90-second subprocess limit. The outer allowance
also covers 19 compiler/extractor stages, not just one Spike timeout.

Terminal aggregate: `reference03/status.json`; first preparation/reference
exception: `reference03/failure.json`. Per-group checkpoints, exact target
events, both ELF hashes, disassembly, negative checks and raw traces live below
`reference03/groupNN/`. Absence of status is not PASS; a service interruption
must be distinguished from a reference oracle failure. No automatic VCS stage.

Before declaring all96 complete, combine groups0 from reference01, groups1/6/18/23
from reference02 and the remaining19 from reference03, require each group exactly
once, and recheck their original inputs/prepared-file/ELF hashes. No hardware or
Linux acceptance follows from software reference completion.

## Future VCS Boundary

Each immutable candidate ELF currently contains four fixed original trials.
The group selection preserves original numbering/formulas and never selects
only easy cases. Four trials already cost roughly 0.93-1.13 million Spike
commits; future VCS wall time must be reviewed, not inferred from Spike seconds.
If this is too large for the agreed VCS budget, prepare a separately reviewed
smaller fixed subdivision, retaining every oracle. No rerun or VCS launch is
implicit in this report.

See `README.md` for exact source identity, privilege adaptations, partial-field
validity, phase-specific firsterror ABI and the explicit source-derived versus
original Linux replay limitation.
