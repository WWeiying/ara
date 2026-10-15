# Host03 ENTRY Fixes, Awaiting Re-review

Status: `PASS_HOST_ONLY_NOT_DUT_AWAIT_ENTRY_REVIEW_NO_PREPARED_PLAN`.
No compiler, VCS, Spike, image build, service launch or RTL edit was invoked.
No actual plan, dryrun, service or parent authorization has been created.
Only this directory was written. Independent source and reference evidence
remain untouched; no independent raw audit was rerun.

## Retained History

- Host01 remains PASS43, SHA
  `ddda582d8925f50f3232aca5ef26d10085753bce9c799cdf4a87d8d273a8f4ff`.
- Host02 remains FAIL49/errors2, SHA
  `234f11fd452e8e368528eca9b2812040a5060244673709239116188bb7ac46ca`.
  Its raw/reference metadata cross-artifact comparison failed closed; no prepare
  attempt was made, and its evidence was not relabeled or overwritten.
- Host03 PASS55/failures0/errors0 in30.928s, SHA
  `21ae2b05eec4da2ffbc3cf5c3443246e84a09c928b710e7ff4f929b2fe0813b0`.

## Both ENTRY Blockers Addressed

1. READY02 `reference_sha256` pins reference/reference.json (`2e48...`).
   That pinned JSON's `commit_sha256` binds the raw commits.log (`d6fb...`),
   which equals the independent audit's raw_sha256. Both artifacts remain
   independently pinned. The gate also binds the completed REVIEW, actual
   execution rc0/no-timeout/no-retry, verified105 input pins and full source
   binary-proof payload. No gate was weakened to accept missing fields.
2. The one-case worker's owned engine hook durably records the actual monitor
   tuple immediately after monitor return, before the frozen runner's generic
   console/runlog reads, trace validator or check_inputs. The tuple includes
   numeric rc, elapsed, timed_out, failure_seen and exact runtime/private-CWD
   command. No metadata reads occur before its first exclusive/fsynced write.
   Parent result classification is a separate runner_result.unvalidated.json;
   timeout classification None cannot overwrite the negative monitor wait rc.
   Hooks are scoped to the sole worker and restored; frozen source is unedited.

Host03 invokes the actual frozen M6 parent _run_test with a fake monitor tuple,
never build/run or a simulator. It forces real generic console/input errors
after rc0 and17, a trace error after rc0, and timeout(-9) yielding the frozen
parent's TIMEOUT/None classification. Numeric evidence and first cause survive;
the worker cannot mark these cases PASS. The private ELF is staged under this
directory before testing so no frozen-tree build lock or writes occur.

## Files for ENTRY Review

- replay.py SHA:
  `066fed2e63e5f7dcc44423d120964b755519f23ca9cea34e114517af241b1157`
- checker.py SHA:
  `959689ad2d2a26d1a879b5c0f9fe7d1b1b8f7f03071a8101a5058fa5a5841b59`
- test_host.py SHA:
  `118c3756712319a50fb98be342b2f78af5a310ebdc27f20c10d2dc7651694875`
- newscope.py SHA:
  `2f28bbe6834387148bb425f1f91e094fc40e79aaee15aa661693fa7cb6cd7f48`
- README.md SHA:
  `325b549b9ac6a3772f9c9fa49ad63d9bfd0b3191b85b83cfe4179835549dd4f1`

These files are now held unchanged for re-review. Main's latest instruction
stops prepare until both fixes and review are complete. After renewed ENTRY
clearance, the intended sole output is fresh prepared01, reserved_slots0,
actual READY02/AUDIT hashes, frozen M6, jobs1,5400s case/6600s outer. Optional
one-case dryrun only; parent plan-SHA run approval remains unresolved.
