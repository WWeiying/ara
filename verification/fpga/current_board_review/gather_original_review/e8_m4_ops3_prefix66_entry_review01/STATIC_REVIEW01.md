# Prefix66 Entry Review: Pre-Seal Findings

Status: **HOLD_PENDING_CORRECTED_HOST_AND_ACTUAL_PLAN**, not launch approval.
Read-only review of producer worker/checker, existing host43 evidence, completed
Hilbert metadata and frozen M6 runner. Only this new review directory is written.
No reference raw/CSV parsing, Host43 rerun, compiler/reference/DUT/VCS, service/
process query, producer/shared-helper edit or image/RTL change.

## Blocking Findings Before Final Pins

1. **Numeric monitor result is persisted too late.** Reviewed `replay.py`
   calls `super()._run_test()` before `persist_unvalidated()`. Actual frozen M6
   `verification/ara_verify/runner.py:480` receives monitor numeric returncode,
   then reads logs, validates trace, writes trace summary and checks inputs before
   returning a TestResult. An exception in that internal postphase loses numeric
   rc0/17; timeout also maps TestResult.returncode toNone despite the monitor's
   actual killed-process code. Existing host43 directly mocks parent TestResult
   return, so does not cover this path. Required correction belongs only in the
   new worker: durable numeric unvalidated monitor-boundary record before any
   parent postprocessing; preserve timeout/failure/cancel flags, stop scope on
   errors, no retry. Main relayed focused rc0/17/timeout postphase negative request.

2. **Raw hash versus report hash mismatch.** Initial actual-schema gate compares
   Hilbert `audit.raw_sha256=d6fb2514506307148560042d452607a966b52395ced7bbed59262bfe69bd4e5f`
   with READY02 `reference_sha256=2e48b4b2efd034cdc3876d2761dd7b9d6701879d1d89668824c101c81fd35dbc`.
   The latter is reference.json's SHA, not raw. Genuine inputs cannot pass that
   comparison. Correct binding is READY02 -> pinned reference.json -> its
   `commit_sha256`, plus existing raw pin; preserve exact independent audit SHA.
   This is an identity-link correction, not permission to weaken metadata checks.

An earlier pre-schema implementation demanded nonexistent `audit.pins` and
`audit.entire_original_linux_binary_rebuild_proven`; that finding is superseded
by the latest explicit actual-schema implementation. The real audit supplies
`full_original_binary_proof_sha256`, `pins_pre_post_unchanged`, count/payload fields
and separate verified_input_pins.json/execution/REVIEW. Do not fabricate fields.

These observations are snapshots of unsealed work. Main has relayed both active
blockers to Zeno. Do not treat them as a verdict on subsequently corrected code;
final review must bind that code, its new host report and actual prepared plan.

## Scope / Gates Statically Sound In Reviewed Checker

- Exact original SoC ELF4d2f9139..., all13 helper encodings versus archived m4
  proof, explicit e8,m4,tu,mu vsets, VI31 opcode308fbc57 and actual capacity
  encoding0022f557. Vtype2, LMUL-register-count4 and cap512 are distinct units.
- Model66 tuples/65 predecessors, endpoint `[0,3,0,4,0,1]`. Actual two vlenb128
  reads and one capacity512 return required. This is returned-error numeric
  prefix scope, not unknown historical stopped tuple or child2688/Linux replay.
- Physical predicate128 bytes with upper64 zero, logical mask64 bytes; input512,
  ordinary indices512, indices16x512 and output514 initialized values give
  **2178 scalar values /2690 bytes percall**. Unused static tails are not claimed.
- Scalar oracle requires every index in0..513 exactly once percall, scalar LBU
  and byte mask, no duplicates, after completed13 helper instructions; expected
  all512 result bytes and2guards, prestart/inactive/tail included. All66 routines
  and returned vstart0 required:33792results/132guards/33924loads/858instructions.
- Retirement PC/code bound to ELF; traps, extra target outside helper, incorrect
  args/VI31/ordinary indices/vsets/guards/CTRL0 are rejected. Full EOF accepts
  only original side-effect-free a001 park after exit. Generic validator and
  strict report counts must agree. CSV lacks internal VRF scan evidence: the
  report's source31 derives from initialized source plus original encoding,
  not a new measured internal gather-index claim.
- Both raw logs get unique exact prefix66/runtime success markers and failure,
  detail, trap and abort veto; incomplete DETAIL lines do not need final values
  or newline to trigger the marker veto. Runtime `gather_prefix_e8_m4_ops3`, not
  source label `rvv_permute_restart_e8_m4_ops3`, is passed to actual +TESTCASE.
- Fixed5400s case/6600s service/jobs1/seed1; no FSDB/UCLI/coverage/retry/build.
  Exact direct service MainPID=self and matching cgroup/RuntimeMax/Restart=no/
  KillMode=control-group; resources total<=24 and MemAvailable>=32GiB.
  Resource reader only skips actual process-exit races; other OSError propagates
  fail closed. Startup/service and authorization checks occur only at future run.
- Parent authorization binds fresh plan SHA/reference/audit/unit; disk plan,
  source/image pins rechecked at dispatch and terminal. Sticky abort and final
  pending-signal veto prevent late cancellation from publishing accepted PASS.

## Existing Host43 Evidence, Not Reexecuted

host01.json SHA `ddda582d8925f50f3232aca5ef26d10085753bce9c799cdf4a87d8d273a8f4ff`:
43 tests,0failures/0errors, recorded24.730s. Its checker hash still matches the
reviewed checker959689ad...; worker/test/scope changes require new evidence,
not reuse of host01 as a current-code certification. Source/model/physical-mask,
fullcap/missing-oracle/load-mask/guard/vstart/runtime-id, first-cause, no-retry,
late-abort/pending-signal, complete membership, resource math and owner negatives
are useful. Early parent internal-postphase and actual independent-schema gaps
above were not covered by these mocks. New concrete tests belong to Zeno.

## Final Evidence Expected, No Current Plan Approval

- READY02 SHA11aec353de588baa6981aa0e46757b76efdbcf7c0656585d5174e96aca523ebc;
  Buildroot exact-original proof7cc7582e71120bce71e5c29de897c271330ce0fa7a5c32dd6dad97dfb5c9cddd.
- Hilbert audit3a9c52768d5244fdc803779ee58744fa243e6946bdddfd953b574d62b0942a4d;
  REVIEW08bc0bd468973c644ff9e1d9ea7bfb0cba05038dd4063a60953fd1c1c0f02965;
  executiona4197c537a19076dc24f701a16ed0eec28d261ef506e3603c689c93345bc79cf,
  actual rc0/no timeout/no retry; verified_input_pins105 and auditor pins separate.
- M6 imagea681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0,
  snapshot3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438,
  config6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785.
- Actual prepared plan SHA supplied after corrected code/new host evidence,
  transitive source/reference/image/framework pins, exact no-run command and
  frozen budgets. No fake acceptance note or unresolved placeholder is authority.

Final pin/admission verdict is pending the actual prepared plan. This preliminary
note is not sufficient to launch and is not an acceptance of a DUT result.
