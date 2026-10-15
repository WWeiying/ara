# NF2 Remaining34 + Same-ELF J4 M6 Replay

Preparation only. No VCS/reference/build launched here. Averroes's actual
`ACCEPTED_REFERENCE34_NOT_DUT` audit is bound, not a provisional result:
audit SHA `e5db50970a48445a7ff8f65c6ca3a457fc47dbdc7216cd65ec1202e691c7e478`,
REVIEW SHA `e418fcbf76d581738ef08aeec87ca758cf3458238e6836bfc3dc59bb04ea823e`.
The new worker reuses immutable runner utilities and each generation's actual
observer, not nine copies of the checker. Final Host output is `host01/`;
the earlier passing development runs remain under `host_draft01/02`.

## Exact Scope

- Groups01..08: four original failed singles each; group09: two. Same prepared
  SoC ELFs, full 128 halfword outputs, two guards, 8192-byte memory, PTE/neighbour
  guards, CSR context, prefix poison, nofault precleanup and remap checks.
- J4: original `../sv39/reference01/soc.elf`, SHA
  `2ddce29de6d035fb02616f7924235b03e8863a74dfad161c3b2a4219ced61a67`.
  Uses original `../sv39/csv_check.py` and symbols, including its b3 field-address
  allowance and exact b5 later-field checks. No compile or golden rerun.
- J4 adds two original b3 failed singles and two b5 positive controls. The
  controls are not counted among 40 failures. J4 previously passed on M2 only;
  this is a separate current-M6 regression, not retroactive M6 attribution.
- With the four accepted pilot inputs, source membership is 34+2+4=40. This is
  reduced-single Sv39 coverage, not Linux signalframe or original parent replay.
- Source mask clarification from independent review: the original C expression
  `mask[128*LMUL_NUM/8]` for m1 is **16 bytes**, not 128 bytes. Fixture is 16 bytes;
  cap64's mask helper consumes 8 bytes. No sealed reference input was changed.

## Budgets

| Job | Parsed reference records | Fixed case seconds |
| --- | ---: | ---: |
| group01 | 1261953 | 5700 |
| group02 | 1177976 | 5400 |
| group03 | 1318302 | 6000 |
| group04 | 1256185 | 5700 |
| group05 | 1352171 | 6000 |
| group06 | 1265954 | 5700 |
| group07 | 1366991 | 6300 |
| group08 | 1308073 | 6000 |
| group09 | 650445 | 3000 |
| old J4 | 1189205 | 5400 |

Budget rule: ceil(records / 273 * 1.2 / 300) * 300. Reference records include
fault attempts, not an asserted hardware retirement count. Every case remains
under three hours. No automatic retry, reduced oracle or runtime budget change.
The runner's global timeout option is explicitly null so it cannot override
the native per-TestCase timeout; metadata therefore records `timeout_s: null`.

Three workers TOTAL, including J4. Simulation budgets sum to 55200 seconds.
Allowing 600 seconds validation per job gives a generic three-worker list
scheduling envelope of 25000 seconds. Worker bound 25200 seconds, direct owning
service 27000 seconds (7.5h), including 1800 seconds teardown/observer headroom.
These are worst-case protective bounds, **not expected elapsed time** or a
completion guarantee. Before each dispatch the unchanged case budget plus
600 seconds must fit the remaining worker allowance. Generic trace validation
and final pin checks also consume time. Expiry stops dispatch, never extends it.

## Gates and Evidence

Pilot independent result was actually verified, not inferred from console:
`../nf2_remaining4_terminal_audit01/terminal01/result.json`
SHA `79037611e05a12289eb6734b836f8cbcb5c28658bd0a88f3002fc895d5bb51ee`.
Pilot complete SHA
`39c697f34c0db5b827cdebb428e7e5181ce0631715cfe8cc71f2d63bf554fcbe`.
The gate checks real COMPLETE/PASS, exact cases/image/ELF, persisted numeric
child zero, strict report, command and raw evidence pins. Metadata ERROR,
null returncode, console-only PASS or control-flow-implied zero cannot admit.
No live service state is inferred from garbage-collected systemd properties.

At execution, direct service ownership, trusted explicit user bus, cap24/free
32GiB resource check and unused reservations are checked. Prepare/dryrun never
query running simulations. Parent controls launch and current reservations.
First failure latches cancellation, including during expensive validation.
Each child result is durably recorded before postcheck. Historical names remain
source identities; `+TESTCASE` uses the separate runtime ID through a copied
case adapter. Final plan/pins are reread and abort checked at publication.

The observer for each new group runs in a private process to isolate configured
MX_N state. Old J4 uses its own original observer process. Group09's N=2 does
not inherit the old J4 N=4 contract.

## Commands

After actual reference acceptance is bound and final Host gates pass:

```sh
python3 -B replay.py prepare --authorize-prepare \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01" --reserved-slots 0
python3 -B replay.py dryrun \
  --image /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image \
  --out "$PWD/prepared01" --plan-sha256 PLAN_SHA
```

`prepared01/ready.json` will contain the exact owning-service command. Run
additionally requires a new pinned parent review with decision
`AUTHORIZE_NF2_REMAINING34_J4_M6_ONCE`, exact plan/unit/pilot audit SHA, actual
reference review pins and `budget_risk_accepted: true`. This document does not
authorize launch. Existing pilot, reference and old M2 outputs remain untouched.
