# Gather Prefix Launch02 Startup Evidence

This note is outside the sealed launch02 plan's753 pins. Only this new note
was written. No service/process query, live trace sampling, terminal polling,
launch, stop, retry, RTL change or modification of sealed inputs occurred.
All running campaigns were left untouched.

Parent reports launch02 was started after launch01's unit was collected,
with a fresh output directory and the reviewed02 authorization. The service
name is reused, not the previous run's output or acceptance:

- Unit: `ara-gather-prefix2-candidate04-01.service`.
- Output: `gather_original_review/stall_prefix2_launch02/vcs_candidate04_01/`.
- Plan SHA256: `64fa59ee5ff9533268bfe8e33165a5979695c4009135cf3b0c3d6db93ad48c45`.
- Ready SHA256: `5e458e1600b3212980dca6f79711052a3619735eba9ef641c19359e0c929b6b1`.
- Parent review SHA256: `7e560343b949f428aaa346efcd86202202839d913c989b00f0a3c30520dd4d0a`.
- Budgets unchanged: jobs2,9000s/case,9600s outer, no automatic retries.

## Persisted Startup Confirmation

The worker's bounded startup monitor wrote `ADVANCING_TWO_SIMV`. A single
read-only verification of that saved record with launch02's existing
independent `checker.progress` passed; this was not a new live observation.

| Authentic child | PID | PID start ticks | CPU ticks before/after | CSV bytes before/after | Complete CSV cycle before/after |
| --- | ---: | ---: | --- | --- | --- |
| e8m4 ops1, masked vx |231950|268141000|205 /254|32768 /57344|599 /942|
| e8m4 ops20, indexed-e16 |231954|268141029|175 /225|20480 /53248|425 /885|

Both samples retain the same PID generation, exact frozen M4 simv executable,
service cgroup, case argv, private input.elf, separate work directory and
private commit_trace.csv. The executable is
`/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image/_build/vcs/simv`.

Evidence paths below are relative to launch02's output directory:

- `actual_simv_confirmation.json` SHA256:
  `8d3343ed5da72c9874a8841d96c27357f6e54c443362a5e07d3368d8a25edc11`.
- `authorization.json` SHA256:
  `2f9ad4842d6aa8271f692710b96c66ae51acf6cc6d5f201f3e5b5a684db5dd04`.
- `worker.json` retains the owning worker's cgroup identity.

The initial discovery contained zero-byte/zero-cycle streams. Launch02
rebased to a positive baseline and subsequently observed genuine growth;
the same60s deadline was retained. Parent independently replayed launch01's
real discovery fixture without VCS: initial anchoring never passed, whereas
the02 logic accepted sample21/120 for PIDs223705/223706, cycles1001/483 to
1683/1170. No startup evidence was waived.

## Acceptance Remains Pending

This is startup/progress evidence only, not an oracle, arithmetic, terminal
or RTL PASS. Complete CSV cycles are not retired-instruction counts.
Acceptance still requires both authentic98-call prefixes, unchanged13-asm
call sequences, full512-element scalar oracle and both guards on every call,
exit0, no abort/failure marker, independent terminal gates and unchanged pins.
The archived original stopped tuple remains unknown; no exact11-stall or
full-parent closure is claimed. Launch01 stays immutable
`NOT_ACCEPTED`, `aborted=true`, `CANCELLED2`.
