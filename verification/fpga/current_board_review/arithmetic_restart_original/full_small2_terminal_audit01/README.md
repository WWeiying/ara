# Conditional Full Small2 Terminal Auditor

**Prepared only. No event service or terminal audit has been started.**
Own directory only; worker, consumed entry/parent approvals, image and source
inputs are unchanged. No active CSV was opened or read during preparation.

## Frozen Scope

- Plan `7ec58e3f38f5877838c7edf898d4b85d4872437dcdc54e7542357e8f2736f9ee`.
- Entry `88c9d814d713c0095fba0d2bd4e3f5c104795a70605bc8ec739f76eda091b8e3`.
- Parent `59ed91223eb2b925ae518ad81ad4618c118589b43d03bfa0670241da0dd34bf8`.
- Worker PID1580624, unit `ara-arithmetic-full-small2-m6-01.service`.
- Same two complete source programs:10080 calls,161280 results,20160 guards,
  original25/35 helpers/three seeds, full history/setup/CSR and model/oracle.
  No invented fflags oracle, original Linux execution or all22 closure.

## Event And Audit Contract

After separate main authorization, verify pinned code/launch inputs, exclusively
create run01, bind actual PID argv/cgroup/start ticks and wait on its PIDFD.
No model-driven polling or repeated systemctl queries. A worker already absent
requires durable complete.json; a PID-identity race fails closed, not reattached.
Waiting never signals or changes the DUT. Only the auditor's own child may be
killed at its bounded offline timeout. Cgroup must be empty or removed after
worker exit. PIDFD proves exit occurrence, **not an exit status**: historical
outer service exit remains UNCONFIRMED_NOT_INFERRED in every accepted report.

Before opening either CSV, require whole2 COMPLETE/PASS, zero retries, no abort,
no first failure/error, exact memberships and both durable numeric monitor
exits0 without timeout/failure/cancellation. Bind private ELF/image/source pins,
commands, consumed approvals and caller metadata; all860 plan pins are checked.
Failure exits/timeout or missing evidence stop this one attempt without parsing.

Each immutable terminal CSV is physically opened and parsed once. The unchanged
frozen generic validate_trace consumes a private DictReader adapter; each row
also reaches the reviewed worker Strict.consume. The generic module instance's
csv binding is local to this audit, not a shared monkeypatch or modified source.
Hash exact input bytes during that same traversal, require complete EOF and
stable inode/size/timestamps, and compare full generic/strict outputs with worker
reports. Full original setup, all result/guard reads, source-helper windows,
CTRL raw0 and original park remain enforced. No raw/reference rerun exists.

Recheck all non-CSV evidence/input/review pins and CSV identity after both cases.
The child writes only a candidate report. Supervisor waits for actual audit rc0,
records timeout/elapsed/exit facts, then publishes independent terminal acceptance.
Signals are sticky; the short final publication decision is exclusive and
signal-blocked, with expensive checks outside it. First failure/traceback and
any partial case report remain; run01 cannot be reused or automatically retried.

## Bounds And Host Evidence

Event wait14400s; one offline audit child1800s; proposed direct observer service
16800s (14400+1800 plus600s supervisor allowance). These bound only this observer;
they do not extend the original DUT case10800/worker12000/service13200 budgets.
Actual audit cost is unmeasured; timeout means NOT_ACCEPTED, never partial PASS.

New gate Host:8 methods PASS, actual process rc0/0.467232s within30s. Tests cover
whole2 terminal/monitor negatives, exact argv, a real short scalar-child PIDFD
exit and timeout, fake cgroup occupancy, lossless CRLF single-stream fanout and
malformed/unknown-event rejection, sticky abort and exclusive output. All
fixtures were owned temporary files; no full-matrix Host or DUT/reference data
was executed or parsed. Existing14 source-checker Host methods were not rerun.

## Conditional Command

Main must approve actual pins.json SHA in PREPARED.json before executing:

```sh
systemd-run --user --unit=ara-arithmetic-full-small2-terminal-audit01.service \
  --property=RuntimeMaxSec=16800 --property=KillMode=control-group --property=Restart=no \
  --property=WorkingDirectory=OWNED_DIR \
  --property=StandardOutput=append:OWNED_DIR/event_service.log \
  --property=StandardError=append:OWNED_DIR/event_service.log \
  /usr/bin/python3 -B OWNED_DIR/terminal.py --authorize-event-worker --pins-sha256 APPROVED_PINS_SHA
```

PREPARED.json provides the expanded exact command. There is no permission to run
it in this preparation turn. Failure requires review and explicit successor
authorization; do not rerun the same parser or delete its attempt markers.
