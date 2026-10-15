# Restart Successor: Ready, Not Launched

Plan SHA256: `f0edb7011fdd4a69e0b633f03fa94405c072b7874367b69e3ab864e570069667`.
Sealed plan03, its inputs and its checker are unchanged. This successor invokes
the existing frozen M4 runner without a hardware/software build.

| Scheduled ELF | Calls | Inner limit |
| --- | ---: | ---: |
| restart_e16m2_prefix130 | 130 | 3600s |
| restart_unmasked_e16m2_prefix130 | 130 | 3600s |

Jobs2, outer4500s. All ELF/oracle/PC/trace requirements equal plan03. Inherited
27 host checks and15 successor checks PASS; frozen-runner dry-run contains
exactly these two entries, neither an actual simulation nor acceptance.
All2731 pins verify. Preparation did not poll Gather,38,NF8 or launch a service.

The complete682-call entry, original ELF and original oracle remain in
`plan.json:held_cases` with `HOLD_NOT_RUN`; it cannot enter the runner's case list.
Successful completion is **PASS_2_ORIGINAL_PREFIXES_260_CALLS_M4**, never942 DUT
calls. Both cases must pass the strict original summaries, raw failure veto,
exit0/tohost0/finish and complete CSV target counts. Any failure/checker exception
cancels peers and queued work. Missing evidence is not a pass.

## Launch Gates

The parent supplies a NEW review JSON using the schema in `review.template.json`,
then explicitly authorizes that file's SHA and this exact plan SHA. It must bind:

- Exact38 terminal PASS and its plan hash; service and simv workers released.
- Gather75 terminal and worker-exit evidence with matching plan hashes; service
  and simv workers released. Initial admission is insufficient. A failed Gather
  terminal releases scheduling only and does not count as acceptance.
- NF8 initial `worker.json` admission: jobs8/reservation8/cap24/memory gate,
  pinned by hash; its shared reservation unit identities must match the review.
- Distinct whole/NF7/NF8/prefix5/FP/Gather/38 systemd unit identities and explicit
  parent confirmation of old38 reservation accounting.

Before startup and each dispatch, cgroup accounting charges the greater of
actual live workers and whole6/NF7two/NF8eight/prefix5two/FPtwo reservations,
plus unclassified simv processes. Cap24 and MemAvailable32GiB are mandatory;
no wait/retry or automatic682 transition exists. Pins, approved plan hash,
review hash and gate evidence hashes are rechecked after completion.

Example command for the parent AFTER all gates and review, not executed here
(`units.fp` must match the named service):

```sh
ROOT=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/fp_comparison_original
REVIEW=/absolute/path/to/parent_review.json
REVIEW_SHA=<parent-reviewed-sha256>
systemd-run --user --unit=ara-fp-original-restart-candidate04-01.service --collect \
  -p RuntimeMaxSec=4500 -p TimeoutStopSec=120 -p KillMode=control-group -p Restart=no \
  /usr/bin/python3 -B "$ROOT/replay_restart_successor.py" work --authorize-run \
  --approved-plan-sha256 f0edb7011fdd4a69e0b633f03fa94405c072b7874367b69e3ab864e570069667 \
  --review "$REVIEW" --review-sha256 "$REVIEW_SHA"
```

Fresh output is fixed to `../candidate04_restart_run01`; existing output is
refused. After both PASS, `complete.json:calibration` records actual cycles,
retirements and walltime for later682 budget review. It neither changes the
held ELF/oracle nor proves that long point. Plan04 remains an unlaunched draft.
