# Full17920 M9 Worker Entry Review 01

Decision: **HOLD_AUTOMATIC_SERVICE_EXIT_RECEIPT**. This is a service orchestration
finding, not an RTL or original-oracle failure. No DUT launch is approved here.

## Finding

- P2: `fp_compare_unboxed_full17920_vcs_m9_plan01/replay.py:101` generates
  `Type=exec, RemainAfterExit=yes`, while lines105-106 rely on `ExecStopPost` for
  the actual service exit receipt. A successful worker can publish complete.json
  and exit0 while the unit remains active(exited); the stop hook does not run at
  that normal process-exit boundary. There is no prepared automatic stop/collector
  path to supply the missing receipt. Do not treat an absent service_exit.json as
  success. The installed systemd.service(5) documents both RemainAfterExit and
  ExecStopPost semantics. Tesla confirmed the gap and is preparing a separate
  narrow service-property successor; plan01 and its worker remain preserved.

## Verified Inputs And Gates

- Actual plan: `../fp_compare_unboxed_full17920_vcs_m9_plan01/prepared01/plan.json`,
  SHA `54f4fbbac1603f1742cbb6d6ad090aee20a9609f9d2efed2dc1c29dd85b0bbdd`.
  All745 non-raw pins were independently rehashed with no mismatch. The remaining
  closed-reference raw pin is bound to the previously accepted reference receipt;
  its size matches, but its contents were not reread. Total plan pins:746.
- Frozen M9 image: all66 image members independently matched. image.json SHA
  `48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a`;
  simv SHA `f75040906f251bf090fc8c03815c1447640d05e2208df3c88fa12e3dca7d0320`.
- Host02: actual numeric exit0, 28 tests, zero failures/errors,5.178458s.
  Host01's incorrect182-versus185 assertion remains a preserved failure. The
  correct static count is182 operation instructions plus3 capacity instructions.
  Actual prepare/dryrun receipts report exit0; dryrun has no simulator output.
- Worker/checker/strict hashes respectively:
  `88d7d1472f9475f6a678b7e2e3c114816cc49cb72acf255cb20a0a9adf95f4ac`,
  `c3e5f0847d652f2ac7939372e91002a8ee0c56dd32808333a6527228417172f5`,
  `0bfc7055399b1b3bac8692d0469b617f8efc93f8f752ac67fe01d3ee31c7d485`.

## FPR And Full-Scope Review

The frozen14-file chain in FPR_OBSERVABILITY01.json proves that valid FMV.D.X
retirement selects commit_instr_result, with we_fpr and full64 commit writeback
to the FP register file. rd=0 denotes f0 for this opcode, not GPR x0.
strict.py:40-44 checks the actual opcode/PC, preceding t2 value, rd0 and full64
zero-extended original b[0]. Lines162-165 explicitly keep this out of the GPR
tracker. All10752 moves,336 per seed, are required. Host02 exercises all32 seeds
and rejects wrong rd/t2, missing FMV, nonzero payload replaced with0, boxed upper
bits and other high-bit corruption. Numerical qNaN-equivalent results cannot
substitute for this writeback check.

The evidence is **FPR committed writeback**, not physical FPR readback or an
accelerator operand snapshot. No dynamic M9 payload result exists in this review.

The source-qualified worker retains17920 contiguous calls,286720 result bits,
35840 guards,17920 flags/vstarts,41 fresh stores and8 input LD per call, one actual
output LWU per call,2240 record loads,326144 operation-helper retirements and
capacity3. Original allowed tails and DK0 old5b5b remain intact. Output bytes4..129
are checked for initialization, not claimed as an original post-result oracle.
The actual full owner contract is89600 mandatory memory owners plus15360 nonempty
target owners; only2560 VL0 targets may elide. All raw protocol rows are delivered
to the generic observer and strict observer in one semantic CSV pass. Numeric
child outcome is persisted before postchecking, with command/private-ELF and
console/failure vetoes. Fixed budgets remain10800/12000/13200, jobs1, no retry.

No new Host, reference, compilation, DUT, live process query or raw semantic parse
was performed for this independent review. Hash/metadata inspection exited0.
After the service-property successor is sealed, review its exact delta, plan,
short service-gate tests and dryrun; the already accepted oracle/Host/reference
must not be rerun merely to correct this orchestration issue. A separate actual
parent run authorization remains required even after an entry NO_BLOCKER.
