# e8/m4 VI31 Prefix66 Entry Approved

**APPROVED_ENTRY_PLAN_NOT_DUT_OR_LAUNCH_AUTHORIZATION. No remaining blocker.**
The two historical findings are resolved by the reviewed Host03/code; earlier
STATIC_REVIEW01.md is preserved. Actual plan was reviewed, not merely a template.
Main may issue its separate explicit one-case authorization; this review is not
that authorization and starts nothing.

## Exact Final Bindings

| Artifact | SHA256 |
| --- | --- |
| Producer `prepared01/plan.json` | **5de3a259e330825548009fbe17a4f80da34c3a6b816b495a695564621ea4ddbb** |
| Producer `prepared01/ready.json` | bd3cb160c92ba1869819f2f8effa25a584975eaaefa61861e9ba43777d4625e4 |
| Producer `replay.py` | 066fed2e63e5f7dcc44423d120964b755519f23ca9cea34e114517af241b1157 |
| Producer `checker.py` | 959689ad2d2a26d1a879b5c0f9fe7d1b1b8f7f03071a8101a5058fa5a5841b59 |
| Producer `host03.json` | 21ae2b05eec4da2ffbc3cf5c3443246e84a09c928b710e7ff4f929b2fe0813b0 |
| This review `audit.json` | **1e4225433ee76362e8d2d82558641251766462ed0ac11c7e15ab3439ad20a7b3** |

All **744 actual plan pins** independently hashed and matched. Host03 records55
tests/0failures/0errors; all current Host03 pins matched. Old Host01 PASS43 and
Host02 FAIL49/errors2 are history only. No Host tests were rerun by this reviewer.
Transitive source/reference/full-binary-proof/Hilbert audit/execution/REVIEW and
frozen M6 image/source/framework pins are present with consistent digests.
Original disk plan SHA was checked before and after this audit.

## Resolved Blockers

- Owned engine hook checks exact private work/console paths, frozen simv,
  seed1, private preload, actual runtime +TESTCASE, no-FSDB/trace command and
 5400s timeout before monitor invocation. Monitor numeric tuple is exclusively
  written/fsynced immediately after monitor returns, before any frozen parent
  console read, trace validator or input check. Later classification has its
  own runner_result.unvalidated.json; it cannot replace numeric evidence.
- Actual frozen-parent host negatives force console/input exceptions after
  rc0/17 and trace exception after rc0, and TIMEOUT(-9) with later rcNone.
  Earlier numeric result/first cause survives; exceptions latch sticky abort.
  Final gate requires numeric0, timed_outFalse/failure_seenFalse, COMPLETE/PASS1
  and no late abort/pending termination. These negative scenarios cannot PASS.
- READY02 binds reference.json SHA2e48b4b2..., which binds raw commit SHA
  d6fb2514... matching the independent report. Worker additionally binds actual
  Hilbert audit3a9c5276..., REVIEW08bc0bd4..., executiona4197c53... rc0/no-timeout/
  no-retry, auditor/verified-input pins and all66 ordered payloads/counts.
  No guessed fields or synthesized acceptance attestation is accepted.

## Preserved Exact Acceptance Requirements

Source `rvv_permute_restart_e8_m4_ops3` is distinct from runtime
`gather_prefix_e8_m4_ops3`. Same SoC ELF4d2f9139..., original13 m4 helper encodings,
e8/m4/cap512/VI31,66 natural calls/65 predecessors, endpoint `[0,3,0,4,0,1]`.
Actual two vlenb128 reads/one capacity512 return; physical predicate128 bytes
(logical64, upper64zero);2178 setup values/2690 initialized bytes each call;
33792 complete byte results/132 guards/33924 scalar LBU loads/858 helper
instructions, all returned vstart0. No active-only/prestart/tail/guard reduction.
Raw logs veto failure/detail/trap/abort even alongside success; missing/duplicate
oracle data, incorrect scalar load masks/PC/encoding/setup/arguments and CTRL
exit are rejected. Only original side-effect-free a001 park follows exit.

The full original Linux binary was independently compared byte-for-byte with
the exact Buildroot rebuild again during identity review. This is binary identity,
not original Linux execution. The approved scope does not recover an unknown
stopped tuple, close11 stalls, execute full2688 or establish parent histories.

## Actual Plan / Dryrun / Future Service

M6 imagea681e274..., snapshot3cba2d3a..., configuration6aaa87d2... match the
accepted frozen identities. Fixed **jobs1 /5400s case /6600s outer**, no retry,
build, FSDB, UCLI or code coverage. reserved_slots0 is the actual plan value;
fresh runtime admission still requires external live+job+unused reserve<=24 and
MemAvailable>=32GiB. No live resource/progress/service query was performed here.

Actual prepared dryrun evidence hashes, one DRY_RUN/rcNone result and exact
command were checked. It uses the original source ELF as dryrun PRELOAD and
the **runtime** +TESTCASE. No console.log/commit_trace.csv/run.vcs.log exists
in its dryrun case. No dryrun was rerun by this reviewer.

The recorded systemd-run command directly owns the worker in:
`ara-gather-e8m4-vi31-prefix66-m6-01.service`, RuntimeMaxSec6600,
KillModecontrol-group, Restartno, fixed work/output directory. Worker checks
actual MainPID=self/cgroup before dispatch, and disk plan/source/image pins at
entry, dispatch and terminal. Those runtime checks are not preclaimed passed.

## Parent Authorization Schema

Actual ready command intentionally retains unresolved parent-review placeholders.
Main must provide a new hash-pinned JSON and substitute its path/SHA at launch:

```json
{
  "decision": "AUTHORIZE_E8M4_VI31_PREFIX66_M6_ONCE",
  "plan_sha256": "5de3a259e330825548009fbe17a4f80da34c3a6b816b495a695564621ea4ddbb",
  "unit": "ara-gather-e8m4-vi31-prefix66-m6-01.service",
  "budget_risk_accepted": true,
  "reference_ready_sha256": "11aec353de588baa6981aa0e46757b76efdbcf7c0656585d5174e96aca523ebc",
  "independent_audit_sha256": "3a9c52768d5244fdc803779ee58744fa243e6946bdddfd953b574d62b0942a4d"
}
```

This fenced schema is not a written authorization file. Worker requires
`--authorize-run`, exact plan SHA, `--parent-review` and its exact
`--parent-review-sha256`; proxy2255.49s is not a completion guarantee. Main owns
explicit fixed-budget risk acceptance. Our audit.json root decision approves
entry only and cannot itself satisfy the worker's parent authorization decision.

Only this owned entry-review directory was written. No producer/sealed inputs,
helpers, code, image or RTL edits; no compiler/reference/Host/DUT/VCS execution,
reference raw oracle reparse, live simulation polling or process/service query.
