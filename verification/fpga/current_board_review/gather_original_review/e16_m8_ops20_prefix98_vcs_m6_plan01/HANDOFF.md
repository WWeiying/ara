# EI16 Runner Prepared, Not Launched

Host32 PASS,43.715s, zero failures/errors. Static preparation succeeded on
the already-built M6 image. There is no `prepared01/launch.json` or replay
directory. No DUT/build/Spike execution, live-job query or sealed-input edit.
The monitor Host test launched only a private ordinary Python child.

| Artifact | SHA256 |
| --- | --- |
| `prepared01/plan.json` | `711e1f5ff862e9da4697ad3b6b2dfd278e78ec079f011b14665f4bfebb84d510` |
| `prepared01/ready.json` | `66effd34cc19017d02043fb65d9490b8f6057ddb7929e2c87503be1109f69a01` |
| `replay.py` | `5c88e2f9e880afcd9cb52c99f081b0301adab25a264c74e8bb1e9a5f7f98bca7` |
| `checker.py` | `b31d5ff38ce9b917d3cd3cf32c57337547e0be8b8b973a1a73ac3c6b42fe13a0` |
| `test_host.py` | `de0be34663e8818286a38eea3cea3d33320a32c239bea7c71b0a028aa78e6e25` |
| `host01.json` | `bf33ec138f7838820dca0a1cc62e0bc422c1bbc94e72b34088e5bf9dd39f4f1a` |
| `README.md` | `56c2982e90d3852eeaf97f00fc9a1acbf072286e70c9ab04370d1360f9eb1043` |
| M6 `image.json` | `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0` |

The786 plan pins bind original ELF/source/oracle/reference, accepted independent
REVIEW/audit, static M6 image/snapshot/configuration, frozen runner, reused
helpers, new worker/checker and Host report. Prepared source/reference READY
remains `1fde3acbc776a3ce8b5ea40d20bfb4e46827758cacfacf5e0333c3d6d4526149`.

Exact scope remains98 calls/97 predecessors/cap512/13asm/returned-vstart,
50176 results+196 guards. EI16 pointer and dynamic/OOR semantics are tested
separately: wrong `indices` pointer; call49 index511 active result44879;
call66 terminal index512 OOR0; call98 terminal index1 data538; call74 inactive
OOR retains91. Original vx constant61881 cannot substitute for those results.
Full98 synthetic protocol fixture is Host checker evidence, not DUT acceptance.

Jobs1/case9000s/service10200s/no retry/no FSDB are fixed. At273 retired/s,
reference2134409 implies7818.35s nominal,9382.02s with20% margin, exceeding
the case budget. No completion guarantee or timeout increase is implied.

Independent runner review must precede parent admission. A new pinned parent
review must bind this plan/READY/source review and explicitly accept budget
risk. Actual resource admission is deferred; no live process/service was
queried. Unused external reservation is0 in this sealed plan; another value
would require a new prepared/reviewed plan, not changing this one. Ready service
command contains review placeholders and was not executed.

No further edits intended after this handoff. Service termination provenance,
full2688/Linux history and exact historical stopped tuple remain outside this
preparation; only a later real replay can establish DUT results.
