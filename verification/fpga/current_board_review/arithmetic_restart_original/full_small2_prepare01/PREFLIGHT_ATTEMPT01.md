# Preserved Software Preflight Error

Initial `python3 -B prepare.py` exited1 before any Spike execution.
e8 full Host positive and eight negative controls completed; e8 SoC ELF compiled.
The provenance check then requested original `capacity` by symbol name and
raised `KeyError: 'capacity'`. The original archived Linux ELF is stripped,
as `nm` explicitly reported. This is not a source mismatch or DUT failure.

Owned preparer correction: scan the actual original disassembled instruction
stream for a unique complete helper encoding sequence, including all13
instructions (capacity3), instead of requiring absent original symbols.
Original ELF bytes/hashes are still matched against recovery22. Completed
compiler/Host commands are reused only with identical command metadata and
their actual persisted expected returncode. Incomplete commands cannot retry.
No prior source, ELF, log or golden output is replaced. Resume is explicit,
`--resume-after-stripped-original`, not a reference retry.

The first `reference.py bound` import also stopped before creating any bound or
reference output: local `prepare` shadowed the immutable integration module
during nested imports. The new local module now temporarily isolates that name
while loading the old read-only adapter. No old helper was edited; no process
or reference invocation occurred on this import failure.
