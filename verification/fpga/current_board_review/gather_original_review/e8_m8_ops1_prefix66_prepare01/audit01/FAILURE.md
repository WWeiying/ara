# Offline Audit Diagnostic Mismatch

The first audit completed its full raw-reference/source/Host8 recheck, then
rejected its truncated `missing_oracle.trace` with `Incomplete calls/asm/oracle/exit`.
The inherited e16 fixture expected the different `Missing oracle/guards`
diagnostic, so the audit itself stopped and produced no audit PASS record.
The other four negative fixtures reached their expected rejection checks.

This is a test diagnostic expectation mismatch, not a Spike or DUT failure.
The e8 trace ends before a subsequent call/exit can invoke the per-call finish
check. Both paths reject the missing oracle. `audit_reference02.py` changes
only that expected diagnostic and the fresh output directory to `audit02`.
All original fixtures and the original auditor remain preserved. No source,
ELF, reference log, oracle, limit, or shared helper changes; no Spike rerun.
