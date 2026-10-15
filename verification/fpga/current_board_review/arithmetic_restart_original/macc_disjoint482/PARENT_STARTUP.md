# Parent-Reported MACC Startup

The parent reported actual startup of
`ara-macc-boundary-candidate04-01.service`, RuntimeMaxSec7800,
KillMode=control-group, jobs2, with sealed plan SHA256
`96b6aa302176fda36d2b684b00c8df3e136e172e9b1c62b65cac4bff72326a58`.
Parent review SHA was reported with prefix `856cb14c...`; the full review hash
is not inferred here.

Before launch, the parent reported its read-only fixed gate returned
ACCEPTED_PASS after rechecking both fixed CSVs,807 pins, raw logs, private ELFs,
abort/terminal evidence and absence of owned processes (1195 processes examined).
This is parent-reported gate evidence, not a second gate run by this agent.

Parent then confirmed both actual simulator processes resolve to the correct
frozen candidate04 executable, service cgroup and private work directories:

| Program | PID | Earlier cycle | Later cycle | Earlier retire | Later retire |
| --- | ---: | ---: | ---: | ---: | ---: |
| macc_e8_m4_single481 |217272|37849|39798|31278|32965|
| macc_e8_m4_pair480_481 |217271|40840|42896|33939|35628|

The observation interval was2 seconds. These observations establish startup and
forward progress only, **not testcase or campaign PASS**. This document records
the parent's measurements verbatim; this agent did not query/re-poll the service,
processes or traces, duplicate launch, or modify any sealed input.
