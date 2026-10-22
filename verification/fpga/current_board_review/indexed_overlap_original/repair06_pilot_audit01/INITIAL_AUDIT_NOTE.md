# Initial Audit Invocation

The first offline invocation returned1 before CSV recomputation because this
new auditor counted closure marker substrings. Both the UCLI `puts` command
echo and its actual output contain that substring. The original logs have
exactly one standalone actual closure marker line in each log.

The owned auditor was corrected to require that standalone line exactly once.
No original artifact, checker, worker, plan, budget, or DUT run was changed.
This was an audit-script parsing error, not a pilot failure. The original
failure was `ValueError: Missing/duplicate capture closure`; no audit acceptance
or recomputed analysis had been published at that point.
