# Parent Launch Authorization

Reviewed plan SHA256:
`34b4caf0f0810a3194449e58bc337b9cadb93d4a31847f70dc871b16c209e0b4`.
This authorizes its exact five original prefixes on frozen M4, two workers,
unchanged ELF/oracle and budgets. The executable performs fresh identity and
resource admission itself. Authorization is not successful startup or PASS.

Release evidence:

- M4 selected38 terminal PASS and successful service exit, independently
  checked1368 pins/38 private ELF identities/76 raw logs. See
  `../integration/CANDIDATE04_38_TERMINAL.md`.
- Gather75 terminal exact-result independent validation PASS: all75 source
  ports,378 prepared files,3972 pins,150 raw logs and75 CSVs verified;
  7792 full-capacity output reads plus150 guard reads. Complete SHA256:
  `9b71c95ad9df4e32beb84d88407c40ff5368bfb311bdfa6ae4897de7afd551f6`.
  Worker and first12/remaining63 stages returned0 without an error. No owned
  service/cgroup/simv remained in the independent process inventory. Journal
  access was denied, so no journal-based service-exit proof is claimed.
- NF8 initial admission is recorded in
  `../masked_translation/nf8_strided_review/sv39_full192/vcs_jobs8_plan02/worker.json`.
  It reserves8 slots and records24 actual-plus-reserved slots. Pilot service
  and actual simulator were confirmed live before releasing this campaign.

The Gather per-case checker no longer runs; reusing the released38 slots
therefore cannot cause its fixed-reservation admission to reject later cases.
FP2 remains held for a separate checker repair and independent review.

Required service: `ara-arithmetic-prefix5-candidate04-01.service`, directly
owning the worker, RuntimeMaxSec10000, KillModecontrol-group, Restart=no,
local append stdout/stderr. No build or retry. Confirm real simulator startup
and advancing trace once, then leave the bounded campaign in the background.

## Startup Confirmed

The service was started once with the required settings. Two actual M4 simv
processes in its cgroup were observed, with private traces for the first two
planned prefixes:

| Program | PID | Earlier cycle | Later cycle | Earlier/later trace bytes |
| --- | ---: | ---: | ---: | --- |
| arithmetic_e8_m4_prefix56 |125091|17762|18659|1490944 /1568768|
| arithmetic_e8_m8_prefix38 |125092|17359|18098|1462272 /1527808|

Each observation pair was one second apart. Executables resolved to the
candidate04 frozen simulator. This confirms real startup and progress only;
neither case nor the five-case campaign has terminal acceptance yet.
