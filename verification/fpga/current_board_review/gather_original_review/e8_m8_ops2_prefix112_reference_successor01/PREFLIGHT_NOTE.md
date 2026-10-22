# Preflight Compatibility Record

The first invocation stopped in `sha(ADMISSION)` because this host Python lacks
`hashlib.file_digest`. The exception is retained verbatim in `error.json`.
It occurred before admission validation, `reference.mkdir()`, command creation,
or `subprocess.run`; it was not a Spike execution or a bound hit.

Only the new driver's SHA implementation was changed to a streaming SHA-256
loop compatible with this Python. The new numerical checker was not changed.
The subsequent invocation uses the same admission and the original two ELF
files. `reference/command.json` and `reference/execution.json` record the one
authorized Spike execution. The exclusive reference directory prevents another
execution. No original artifact, old helper, source, ELF, or RTL was modified.

`error.json` is retained historical preflight evidence, not the terminal result.
Any successful successor status is separately recorded by the complete raw
checker in `reference/reference.json` and by offline controls in `READY.json`.
