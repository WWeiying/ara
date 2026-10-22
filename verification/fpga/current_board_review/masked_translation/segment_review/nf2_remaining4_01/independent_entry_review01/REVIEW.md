# NF2 Remaining Four Entry Review

2026-10-12. READY FOR PARENT CONDITIONAL LAUNCH; no blocking finding.
Read-only source/report/hash review, no Host rerun, golden/raw reparse, live
resource query, compilation or simulator execution. This is not DUT PASS.

## Frozen Identity

- Plan SHA: `7a644bfd57e314649a92a6512cd6c994c49f7e9b656f0caaa5e172ec0e4d9c55`.
  All700 file pins independently rehashed, zero mismatches.
- READY: `d427f9c9846e0c59d9374efb6fbae020df08c8f6a4472ce740e05ddf4306aa2f`.
- SoC ELF: `cd2aa14f5251bf32353bf256b5c64e9035dc0ed266688bece78f7c691ac234d2`.
- M6 image ledger: `a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0`.
- Actual independent REVIEW: `47fc85fe429f9be67ae48b5c0bc73b979a808ed60e6750e5bdf21b954abab582`.
- Actual result JSON: `f7c60873358baeeea6d8a0798a6ec8e0bdf5ad0f9daeb2750784ec0f23c918e6`.
  Runtime validates accepted source/reference status, READY, exact four IDs,
 3567 reference checks and unchanged pins; parent approval binds those same files.

## Exact Scope And Oracle

Four archived failed singles match actual fixture configs (base/mask/start):
u0_s0_b1_m2_f1=4090/24/2; u1_s1_b3_m2_f0=4084/24/5;
u0_s1_b5_m3_f1=4074/00/8; u1_s0_b1_m3_f0=4092/00/8.
All target phases are VL8/e16m1; start8 denotes no fault, not a restart value.
Both all-off cases require only the S-ecall handler, no fault retry, and full
memory/PTE/guard checks before cleanup/refill can conceal side effects.

Source golden functions use case constants, original memory formula and seed
formula, not observed target results. Full8192-byte memory, two64-halfword
fields,128 final output halfwords plus2 guards, prefix poison, tail/neighbor
state and restored CSRs remain checked by pinned firmware. CSV validates
actual check arguments, counts, target/handler order, records, PTE repair,
SFENCE, restart and refill. No blanket MMU-skip is allowed for fault cases.
The two no-fault cases cannot alone prove translation occurred; this is not
claimed. Both protection variants use invalid Sv39 PTEs, not Linux subtype ABI.

The observer's gold[2]=actual[2] branch is restricted to the exact independently
computed second protected field address, not an unconstrained observation-as-
golden rule. Its one-check count adjustment matches the source's allowed-field
branch. Vector payloads are not exposed by scalar RVFI; full vector correctness
is supported by the pinned firmware oracle, not a claimed direct CSV vector dump.

## Host And Execution Gates

Consumed observer Host02:2 synthetic positive sequences,25 rejected mutations;
worker Host04:7 tests, zero failures/errors. Their pinned scripts match. No
new test execution was needed. Dryrun is one actual DRY_RUN record bound to
this plan, seed1, M6 simv, runtime TESTCASE=nf2_remaining4_sv39 and correct cwd.
Dryrun preload names the source ELF; real execution requires a private input.elf.

The runtime/historical name adapter preserves source provenance while checking
the actual TESTCASE. Exact seed/preload/cwd/image checks remain enabled.
The successor runner exclusively creates and fsyncs child_outcome.unvalidated
before strict checking, preserving child rc even if checker throws. That record
is explicitly not architectural acceptance. Sticky abort, COMPLETE/rc0, final
fresh plan/pin checks and signal-aware atomic terminal publication remain bound.

One job, case6300s/service6900s, no build/retry/FSDB. Direct service MainPID and
own cgroup, exact1h55min/control-group/Restart=no are checked via explicit user
bus environment. Parent still owns exact-plan authorization, budget and live
resource admission; this review makes no availability or runtime guarantee.
Scope is four source-derived Sv39 cases, not original full Linux parent closure.
