# Full Original e8/m4 4095 Software Feasibility

This directory is a new software successor, not a DUT acceptance. It preserves
the reconstructed original source's complete 4095-call ordering, original RNG,
25 original assembly helpers and original mismatch fallback. The original C
bytes were lost; binary-identical reconstruction evidence remains in
`../recovery22/report.json`. The original Linux ELF is not this bare-metal ELF.

`preflight.json` records the actual 10172-word dictionary, maximum uint16 index
10171 and 614110-byte index/dictionary/mask ROM. `proof.json` binds actual
compiled helper bytes to unique windows in the original stripped ELF, both
linker bounds, and the Host evidence. No additional vector instructions appear
outside the original capacity and operation helpers.

Each call initializes exactly 514 bytes, checks 64 complete 64-bit chunks and
one exact two-byte tail, covering all 512 results and both guards. Byte pointers
and constant-size builtin memcpy avoid unaligned typed-pointer casts. Four-way
fixed scalar unrolling is the sole candidate, not a parameter search. The
physical predicate remains 128 bytes, with its upper 64 bytes zero; its setup
retains the original per-mode position before the vstart trial loop.

Host03 runs both actual source loops with a Host-only helper emulator. Every
source input byte, physical mask byte, fresh output byte, actual call parameter
and original C per-position expectation is checked against the independently
generated Python model/dictionary. This is a software transformation proof,
not hardware execution. Seven corruption classes preserve original fallback
diagnostics and counts exactly. UBSan trap mode checks undefined behavior;
the deliberate shift64 negative actually exits by SIGILL (-4).

Earlier compile failures are retained separately: Host01 is an unused-function
fixture compile error; Host02 is a missing system UBSan shared-library link
error. Neither is a numerical model mismatch. Host03 uses compiler UBSan trap
instrumentation without that library; it does not waive undefined behavior.

`reference.py` requires an actual independently accepted review hash before
one bounded complete Spike measurement: 120 seconds, six million hard steps,
768 MiB maximum raw log. Three million firmware instructions is the cost
admission target, not an assertion of a hardware wall-clock bound. Exceeding
that target writes HOLD and does not authorize a DUT run. Numeric child wait
is saved before counter parsing or raw observer checks. Raw is parsed once.

No RTL changes, image builds, DUT runs or accepted-prefix reruns are authorized
by this directory. Any new reference or observer failure stops without retry.
