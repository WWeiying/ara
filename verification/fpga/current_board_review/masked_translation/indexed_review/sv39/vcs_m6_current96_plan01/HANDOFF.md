# NF7 M6 Successor Ready For Parent Review, Not Launch

## Actual Preparation Evidence

- `host01/status.json`: **28/28 PASS**, zero failures, process exit 0.
  Synthetic Host cases only; no DUT/reference/Spike execution or live capacity query.
- `prepared01/dryrun_gate.json`: **DRYRUN24_PASS_NOT_DUT**, process exit 0.
  Frozen M6 Runner emitted 24 commands without executing any simulator/build.
- Post-dryrun read-only verification: all **840 pins unchanged**; all 24 command
  JSONs exactly bind the original ELF, M6 simv, seed 1, unique runtime ID,
  `+NO_FSDB` and commit-trace output. No coverage flags, DUT CSV, `launch.json`
  or `replay/` exist. No service was created or queried.
- The frozen Runner's dry metadata is `status=DRY_RUN`, counts `DRY_RUN:24`,
  not DUT `COMPLETE`. A supplementary read-only inspection initially asserted
  `COMPLETE`; correcting that inspection to the actual dry-mode contract passed.
  No prepared file, helper or test expectation was changed, and no dryrun repeated.

## Preserved Scope

24 byte-identical previously accepted SoC ELFs, 96 trials with each original
four-trial group kept in order; 284816 original numerical comparisons,
168 checkpoints and 168 trap records (72 architectural faults plus 96 ecalls).
Original cases/status/symbols/ledgers and `csv_oracle.Checker` are unchanged.
Each observer is an isolated process. Historical source identity is separate
from runtime `nf7_g00..23`; the original label cannot replace a runtime ID.
This prepares M6 source-derived Sv39 full96 regression, NOT a M6 DUT PASS and
NOT closure of the unidentified original Linux error's exact trial/phase.

Host negatives cover wrong runtime ID, image and private ELF; missing,
duplicate and reordered members; missing actual oracle; PASS+FAIL veto;
postcheck error preserving actual numeric child exits 17 and 0; missing command
identity still preserving the numeric outcome; no record overwrite/retry;
strict-postcheck failure retaining exit 0 but rejecting acceptance; late abort;
direct service/cgroup/bounds; pin drift; resource arithmetic; and no launch
without a fresh parent authorization. No fabricated artifact was accepted as
an architectural oracle result. The unchanged real Checker rejects the empty
synthetic CSV in the isolated observer.

## Exact Identities

| Artifact | SHA256 |
| --- | --- |
| `prepared01/plan.json` | `b29f616c1075ccf06a9294bc970382a5c7d6f897b17339b284a2bb22d829d64a` |
| `prepared01/ready.json` | `37d9e3871feebe3384bf19c3ae76f40927a2bac733018fa8b55e7a0556ab9aab` |
| `prepared01/dryrun_gate.json` | `d11fc8679123d7870a0259c940e85017bcefe47538734f5c3c1ea703e715d093` |
| `prepared01/dryrun/run.json` | `346f9f5f24279b30cadcf99f59d8021c056d5e04a77b5a9a4bc0f5fad4b456c3` |
| `prepared01/dryrun/summary.json` | `2b9380415d193681f84d043a02e3d30dd63578a026fa811a4b64c33e2e31c9a7` |
| `host01/status.json` | `47b95e6232b41f65fcc6b444b0a6e814fec51876e1a457c072638519f823c1b4` |
| `host01/log.txt` | `5a0e1308b00ecc8ca24b44060ace1caa16f0db886367f05b6a60b506ad2316f8` |
| `replay.py` | `62e8720e80bf438f6a07f56ff2862146169d889dc76e82f5cac8b5c2299679cb` |
| `checker.py` | `f3c5ec0e4573542ba906bac27933f6b9ada2d08d3ab8f5b883616112b4002b13` |
| `observer.py` | `3db0771a5abd305fe36be0bced763b6dd55bc0b1fc410319f7a70aa06076d55a` |
| `test_host.py` | `acdb1c4dda40b9ff6f18232aa29d8ae685e5df9a7e848e508084b1cfdc61899b` |
| `README.md` | `101309ff93fd14ea05fa047411cb023b6073b3b06b1906b062ec61f28ad29526` |
| frozen M6 `image.json` | `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0` |
| original accepted program manifest | `f39037e695688e0706324b3f9d27dc62e0765848348e306d19a4d8f4572f611c` |
| original independent M2 full96 audit | `183b1bd1a268741f5c49dfa97b57ae9a8e239ff02bd5e478a3773f94bcf63a80` |

## Unresolved Parent Gates

1. Independent review of this implementation and a NEW pinned authorization
   JSON in the schema documented in `README.md`; preparation grants no launch.
2. NF2 remaining34+oldJ4 whole-batch terminal and independent acceptance. This
   task did not inspect active NF2 outputs or assume its completion. The future
   worker requires its pinned terminal/plan/review and correct M6 image/status.
3. Parent reconciles other reservations; plan's unused external reservations
   are zero. At authorized launch only, actual live + new4 + reserved <=24 and
   available memory >=32GiB. No automatic retry after refusal.
4. Direct worker MainPID/cgroup in `ara-nf7-current96-m6-01.service`,
   RuntimeMaxSec=16800, KillMode=control-group, Restart=no. A command template
   is in `prepared01/ready.json`; it has not been invoked.

Budgets remain 2400 seconds per simulator, 2700 per group including oracle,
16200 worker envelope, original four-job 16800 outer bound. The old measured
M2 four-job ordered estimate is 9689.75 seconds; M6 timing is not measured and
completion is not guaranteed. No timeout increase, new reference, regrouping,
oracle reduction or automatic retry is authorized.
