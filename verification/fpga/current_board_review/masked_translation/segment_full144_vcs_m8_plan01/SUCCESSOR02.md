# Document Pin Successor

Prepared01 and all consumed source/checker/Host/reference files remain intact.
Main appended its review after preparation, invalidating exactly that old
document pin. This was detected before any DUT launch, not a hardware failure.

`replay02.py` consumes Zeno's sealed `SOURCE_ADDENDUM01.json` with its actual
schema and permits only the specified old-to-new main-document hash. All
other original review/source/evidence pins must remain identical. No oracle,
simulation budget or process protocol is changed.

The independent entry reviewer also found a real durability gap: sealedrun
hashed command metadata before persisting the returned monitor tuple. The
successor wraps that actual monitor call and first exclusively fsyncs
`monitor_numeric.unvalidated.json`, containing only returned primitive values.
It then returns the unchanged tuple to the sealed worker. A later hash/read
failure still produces NOT_PASS, while actual process outcome survives.
This record is not architectural acceptance and never fills a missing old rc.
`numeric_host02.json` exercises the real run boundary with fake monitor0/17
followed by a deliberately failing command hash; both preserve actual numeric
values and terminate NOT_PASS. No simulator is executed by these two tests.

Use `prepared02/ready02.json` as the authoritative successor launch command.
The inherited `ready.json` is retained as generated dryrun/preparation evidence;
its older entrypoint is not admitted for this successor plan. Independent
worker entry review must bind the new actual plan SHA before the already
authorized one-shot M8 run. Source/backend-only review is not worker admission.

`binding_host02.json` tests this sole document substitution and rejects six
metadata counterexamples. It rechecks unchanged Host02 input hashes, without
rerunning full144 Host, Spike or any simulation. Parent authorization will
record the actual coordinating-goal instruction; no independent decision is
manufactured by the worker author.
