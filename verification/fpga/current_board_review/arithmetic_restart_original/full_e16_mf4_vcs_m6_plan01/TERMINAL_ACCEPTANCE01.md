# Full E16 MF4 Terminal Accepted

Existing automatic audit completed one full CSV traversal. Metadata reviewed
without rereading raw CSV; terminal/report/actual child exit/worker complete
hash chain matches.

- Worker PASS_M6_FULL_ORIGINAL_E16_MF4_4095_CALLS_NOT_LINUX;
  simulator numeric exit0,6406.345964943s, no abort, retries0, pins unchanged.
- Independent audit numeric wait0,179.784607765s, PID1923582, attempt1,
  no timeout/error. Worker cgroup was recorded removed by the auditor.
- Full4095 calls,65520 results,8190 guards,4095 vstarts,53235 helper instructions;
  original order retained, no partition and no invented fflags oracle.
- Full3987908 rows,3806630 retires,6 post-CTRL parking retires.
- CVX request/response/architecture45048 each, uop alloc/done23067 each,
  no exception/replay; all six-event checks completed in the single traversal.

Auditor: ../full_e16_mf4_terminal_audit01/run01/TERMINAL.json
SHA256: 934885e2efd02825b2ed92cd3d78eddab40ded5994dc94087a7f17be7bee1370
Worker complete SHA256: ef808395dc93c60934d3a0a23b1dd3dce42bbff3bd99d14a2228dcafcd9a1db8
Actual audit exit SHA256: 586604264bcede495574beb69bcc556d6ecd5a2595127971127f79c9b75c750c
Raw CSV SHA256 from the one-pass audit: 201f8a46f1baaf6f5243e734a23a4e0afe87762485bf9e3d42053cde827101c9

Only authentic reconstructed full e16/mf4 arithmetic on M6 is accepted here.
Not Linux/all22 closure. Historical systemd service exit remains unconfirmed,
not inferred from pidfd notification or numeric simulator/auditor exits.
