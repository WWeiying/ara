# Independent Successor Entry Review

Decision: NO_BLOCKER_FOR_PARENT_CONDITIONAL_LAUNCH. This frozen successor
addresses the reviewed checker-scope issue without reducing the original data
oracle. Not DUT PASS, automatic launch permission, or a current resource finding.
Parent exact-plan authorization, budget-risk acceptance and runtime admission
remain mandatory. Prior withdrawal and old evidence remain unchanged.

## Reviewed Identities

| Artifact | SHA256 |
| --- | --- |
| prepared01/plan.json | 51711836aab45fa44a34f16e80801fb9ac0dbf2412cf6660577e0737c17f013c |
| host01.json | 19ffb3ea1791559d9706a24484b2e318f6d825bd4e4b88d03c9fc0711db905e0 |
| host01.log | 3834925fb5d43aec98f52f69fb661436ecad20a22ed321468f484dc102537ea2 |
| checker.py | ad174cc5eb265fea958ba388c476094d109cb382af618f0d2d022b88bbb58568 |
| replay.py | 483e838974280a944411ba22f3664bd4372fcb0210e65295b73f265574012ea6 |
| test_host.py | 1f6a6ddf740ef94f9ad7bdbefc9be19a515a3e7c3d4fe7bffa87d7dd32c996a0 |

Rehashed all738 new pins and all733 predecessor pins,745 distinct files in
their union: no mismatches or conflicting shared digests. This took2.682573s.
All107 source/reference READY pins are included unchanged. Host JSON directly
pins current checker/runner/test code and matches the prepared plan.
Original SoC ELF remains eed20f08a98ac66766a66810b6f5f8fc829d0603477d37b3d59d48c32669f162;
M6 image ledger remains a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0.

## Successor Scope Checks

- Every actual retired PC/encoding must still belong to the pinned ELF.
  Both entire unused helper ranges are excluded, including integer/CSR/return
  instructions: [0x80000728,0x80000778), [0x80000778,0x800007c8).
- op0 entry is one-shot after complete prelude/capacity. Its remaining20
  instructions require an active window and exact consecutive retirement PCs.
  Window closes at return: internal integer, CSR or RVV instructions before
  entry or after return cannot pass, even with balanced CVX transport.
- Allowed RVV retirement PCs are exactly capacity's vset plus the ten original
  op0 vector instructions. Each occurs once; final Counter equality rejects
  omissions as well as duplicates. This is11 RVV retirements, not11 helpers.
- Legal capacity is preserved as all3 consecutive instructions: li t0,-1,
  e16/mf4 vset returning16, ret. Entry count1 and step count3 prohibit interior
  entry/replay; original fractional LMUL is not replaced by a whole-register type.
- Five original startup CSR instructions and two actual C/wrapper vlenb reads
  are allowed in order before capacity. Both vlenb reads return128. Original
  prepared main.c and scenario.c contain these reads, with capacity after the
  scenario read. Helper CSR save/read/set/restore remains legal within op0's
  full21-step window. No blanket ban on legitimate CSR operations was added.

Diff review confirms original setup, fixture traversal, memory byte masks,
arguments, NV16/vstart0/packed status, saved-zero CSR restoration,144-byte full
oracle, exit and park checks are unchanged. Reference/source acceptance and its
extra-Zfh profile limitation are consumed from sealed evidence, not reparsed.

## Stored Host Evidence

Host PASS_HOST_ONLY:41 tests, zero failures/errors,152.236s. Independently matched
every current test name to a successful stored log entry; no test was executed.
All31 old test methods remain. AST comparison shows only the old full-positive
method changed, adding four stronger assertions: capacity3, outside-helperCSR7,
RVV11, unused-helper0. Its synthetic fixture now includes the real prelude and
full capacity instead of the old abbreviated capacity entry. The positive still
passes generic plus strict CSV validation; all old rejection methods remain.

Ten new successful rejection tests cover:
1. Recorded op1 interior min through generic/strict/full artifact gates.
2. Recorded op2 interior max through the same gates.
3. Unused op1 integer interior.
4. Unused op2 return interior.
5. op0 integer repeated after return.
6. op0 integer before entry.
7. Capacity entry replay.
8. Capacity vset interior replay.
9. Late original-C vlenb CSR.
10. Replayed startup vstart CSR.

The two full-artifact mutations retain the complete old oracle and use matched
request/response/retirement events; rejection specifically names the unused
helper range, not an unrelated malformed trace. Duplicate op0 RVV also meets
the explicit zero-prior-count rejection in static code; no additional executed
negative beyond the recorded41 is claimed here.

## Conditional Launch Boundary

New unit ara-redspecial-e16-mf4-original-m6-02.service, jobs1/case5400/service6600,
no build/retry/FSDB. Runner retains exact MainPID/cgroup/service checks, trusted
explicit user-bus query, exclusive launch, same M6/private ELF, full raw marker
veto, COMPLETE/summary checks, terminal fresh plan/pin verification and sticky
abort publication. These control paths were unchanged by the successor diff.
The existing publisher's final pending-signal check is its terminal decision
boundary; this is not a promise to revoke a decision for every later signal.

Parent must validate its unused reservation roster and accept the unchanged
timeout risk (2820s planning estimate; slower273-retire/s proxy exceeds5400s).
Future acceptance covers only this original reduced single, not full6720,
remaining10 original records, arbitrary nonzero CSR restoration or exact
narrower-reference-profile equivalence.

Actions limited to reads, AST comparison and hashes. No Host rerun, raw reference
parse, objdump, resource/live query, Spike, DUT or build. Only this new report
was written. No old report, withdrawal, helper, pin or evidence was modified.
