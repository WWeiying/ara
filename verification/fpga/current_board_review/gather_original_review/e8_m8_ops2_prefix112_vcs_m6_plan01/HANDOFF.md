# Sealed Prepare-Only Handoff

Status: **PREPARED_NO_DUT_AWAIT_PARENT**. The existing draft was resumed, not
regenerated. `PAUSED_STATUS.md` remains unchanged as historical evidence.
Formal source/reference audit02 is now accepted and pinned; no DUT acceptance
is claimed. No DUT, Spike rerun, compilation/build, or live-resource/service
query was performed. Only owned Host tests and prepare were executed.

## Results And Pins

- Host55:55 passed,0 failures,0 errors,198.761s. Full112 synthetic positive
  passed generic and strict CSV checks. Last80 scalar reads missing,112th final
  guard, upper512 omissions, upper tail/mask/prestart, final enabled/disabled,
  old66 markers/trace, wrong VI/VX encoding, pointer, CSR, LBU, CTRL/park,
  actual partial-DETAIL monitor, drift and late-abort controls passed.
- `prepared01/plan.json`:1098 verified pins; SHA256
  `bb3b5302ce2c65ec91874c22ed85705488aae4ba2043ad32b285ba60c6d81c11`.
- `prepared01/ready.json`: SHA256
  `880682355e85e9cccb7b4ba12167bc1a04a1e18e59a4052fd8898dbf14344d94`.
- `host01.json`: SHA256
  `67702527d52c99ab458bbe870b7643732b92aaf9af4dd8902ac9f54af1ae7681`.
- `replay.py`: SHA256
  `0409776216fe0eae514ffe715540663b31414d68ef10e8ec7cc5983cd95631e5`.
- `checker.py`: SHA256
  `77683517a53ff02666068b6176eebe3df7eb2f74daaefa914d3ad1536e93cff7`.
- `test_host.py`: SHA256
  `892b298f63f4c3a7a0fa188a074319d3616aedbf2c48ea171c2e7a28ff70b4df`.

Bound reference entry: successor READY `e6962c38...f135520`, not an invented
READY in old incomplete prepare01. Formal audit02 REVIEW SHA256
`dcfc682bfb94597c210c88b05c2469a01b6bfbde8c6f0cbd88a483290ef53bd9`;
audit.json SHA256
`e4fa3b3850826cec964014821c9e497917df60c86542d7a08f2e603f4be1ed5b`.
Old incomplete artifacts, audit01 failed attempt, references and ELFs are
preserved. The audit02 report and its13 park negatives are pinned too.

## Exact Future Scope

One unchanged original SoC ELF, SHA256
`a0445bcb877799d488e40f37d7bcbc038d9f0e36a7a60e147ed8baf3c5ea5f74`;
original112/111 predecessors/cap1024/114688 results+224 guards/112 returned
vstart checks/all7VL x4mask x4start/original13 instructions `30803c57` VI0.
Original ordinary indices, a6/t3 zero, immediate0 and source0=185 remain.
Full RNG/setup, all LBU oracle reads and strict original CTRL exit are required.
Late disk plan SHA, exact runner COMPLETE, unchanged pins and sticky no-abort
publication remain enforced. No full2688/Linux/historical-stop closure claim.

M6 image: `/home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image`.
Image ledger SHA256
`a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`;
snapshot SHA256
`3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438`.

## Budget And Admission

jobs1, case9000s, direct service10200s, no FSDB, no retry or rebuild.
Reference5050000 steps are not a DUT instruction limit. Measured reference
firmware5002732 gives a conditional M6 VX proxy7586s/+20%=9103s, exceeding
9000 with margin. VI31's separate rate gives6987s/+20%=8385s; neither operation
nor its backend/runtime is identical, so no completion guarantee follows.
See `BUDGET.md` for exact terminal evidence hashes and conservative273/s case.

Intended future unit: `ara-gather-e8m8-vi0-prefix112-m6-01.service`.
The emitted command in `prepared01/ready.json` is NOT executed. It still needs
formal plan review and separately pinned parent authorization accepting the
budget risk. No `prepared01/launch.json` or `prepared01/replay` existed at
handoff. No service-state or process observation is claimed.

The worker/checker/Host reports and prepared plan are now sealed by hashes;
do not edit them. This handoff is a later report outside the plan's pin set.
