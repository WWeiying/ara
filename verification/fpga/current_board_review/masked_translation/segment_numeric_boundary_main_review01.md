# Segment144 Numeric-Outcome Persistence Main Check

The revised `replay02.numeric_monitor` saves returned monitor primitives to
`monitor_numeric.unvalidated.json` before command hashing or metadata reads.
This fixes a worker durability gap, not a production RTL defect. A later
postcheck failure still rejects acceptance; the numeric receipt alone never
proves the architectural oracle.

Main independently executed `test_numeric02` against the actual revised run
wrapper using its deliberate fake monitor and post-monitor hash failure.
The final report save was captured in memory rather than overwriting the
owner's existing `numeric_host02.json`; temporary per-case receipts were
still exercised through the real exclusive, flushed save function.

Both cases passed, actual checking-process exit0. Fake monitor returns0 and17
were persisted unchanged. Both deliberately broken run wrappers returned1
and published NOT_PASS, preserving abort status and the hash-read cause.
Neither case launched a simulator. This proves the tested numeric-before-
postcheck boundary, not the full144 fixture, real simulator return semantics
or a DUT acceptance. Existing Host/reference/DUT artifacts were not changed.
