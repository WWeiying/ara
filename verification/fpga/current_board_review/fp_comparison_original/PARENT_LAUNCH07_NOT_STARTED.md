# Plan07 launch did not reach simulation

The parent invoked `ara-fp-original-restart-candidate04-01.service` with
plan SHA256 `75b25fae4ebdd7e6c68d9e66ee72c1673e88efd91495fa03a144cb96996f6737`
and the pinned `candidate04_restart_plan07/parent_review.json`.

The worker exited in the inherited `gates()` function before `RUN.mkdir()`
and before starting any DUT simulation. The first line in the complete log
is `Failed to connect to bus: No medium found`. The script clears its process
environment before calling the inherited systemd query; that query returned
a nonzero exit status and raised `CalledProcessError`. The traceback is
retained in `candidate04_restart_plan07/service.log`.

The parent's initial diagnosis used the traceback tail and incorrectly
attributed the observed failure directly to the already collected Gather
unit. An independent review identified the missing first-line diagnostic.
The observed launch failure is an unavailable user bus in the sanitized
worker environment, not evidence that a missing-unit response was received.
The collected-unit case is a separate state the successor must also handle.

This is a launch-check failure, not a failed floating-point test, timeout,
or new RTL defect. The two 130-call source prefixes have not run under this
attempt. The 682-call prefix remains held.

Preserve plan07 and its sealed helpers. A successor must distinguish a
collected, completed unit from an active unit or an unavailable systemd
query, using the terminal evidence and absence of owned processes. Queries
must use a verified user-bus environment even after worker sanitization.
Unknown query results must remain rejecting. Independent host review is required
before a new launch; no change to the test oracle or RTL is authorized by
this launcher correction.

## Read-only Environment A/B

The parent queried the same Gather unit with `/usr/bin/systemctl --user show`
and the seven identity/state properties. No simulator was launched:

| Environment | Return | Observation |
| --- | ---: | --- |
| Only PATH and HOME | 1 | Empty stdout; `Failed to connect to bus: No medium found` |
| Same, plus current UID's `/run/user/UID` and `unix:path=/run/user/UID/bus` | 0 | Exact unit ID, LoadState=not-found, inactive/dead, MainPID=ControlPID=0, empty ControlGroup |

This reproduces the environment failure and distinguishes it from the actual
collected-unit response on this host. Successful state queries alone do not
prove test completion; the pinned terminal evidence remains mandatory.
