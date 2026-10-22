# Final Prepared02 Review

Decision: **ALLOW_FOR_PARENT_LAUNCH_NOT_DUT_PASS**. No blocking finding in the
frozen successor, checker, host negatives, capture or plan/context. Read-only
review and independent hashing only; this reviewer ran no host test, simulator,
build or service. Other owners' files were not edited.

## Exact Binding

- Plan: `../vcs_candidate05_plan01/prepared02/plan.json`
  SHA256 `ab3b7fad17469a4fb317d7bcfaa0d7ca63e0b244fc6a4cb55cdf301f812e89c5`.
- Independently rehashed all **735 pins**, zero missing/mismatched inputs.
- Worker successor SHA256
  `398eb80d86a2ba91a4e02ee3dfaf0091826556f3f100f1fade0a5a2575bf57d0`.
- Checker SHA256
  `2fa13d4e03c18f383c2f1b06d292d77cc2ef356ef6273b29ad3e32f6bb31ab58`.
- Successor host report SHA256
  `cd2a952f4dd8cee57becccab436ec84f04add61b7ba496105af05d957b418a75`:
  HOST_PASS_NOT_DUT, 29 tests, zero errors/failures; all six report pins match.
- Capture SHA256
  `b1cf525a69d2915dbddac0d16f4c9107130eaaa43fe696b6690711e7c18b30f7`.
- Launch command SHA256
  `5a91284709cba664dd0e207e903e54e501e23bd88fefe2983d476af980ed8cb4`.
  Direct successor worker, unit `ara-indexed-overlap-m5-01.service`, fresh
  `prepared02` output. `launch.json` absent at independent hash review.

## Scope And Gates

Only reference03: pilot `d32m2_i64_fault_ov1`, then resident ov1 and fault ov0.
The successor fixes the former tool-name/case-name shadow and asserts exact
three-case membership; prepared01 and original worker remain unusable for
launch. The actual prepared02 membership, original ELF hashes and SoC ELF
hashes match the previously reviewed reference03 identities. M5 image JSON
SHA256 is `9349bdae91e72706ffbb22ad20a7f62795215a5263b1ec0cc4e4837fc21d1500`;
snapshot SHA256 is
`0fb492aebe246deeeacf312b387d0813837afe4b023e53e5fe5d584bca5c0dbf`.
Compiled sources, configuration, simulator files and frozen runner are pinned
and revalidated by existing image_context; no build path is introduced.

Worker enforces pilot jobs1 before controls jobs2, first failure/sticky cancel,
no retry and complete exact membership. Parent explicitly confirmed the final
sealed budgets: service9600s, worker8800s, fault4200s/resident2400s. The common
deadline overrides each case, including checking and transition to controls.
Cap24/MemAvailable>=32GiB admission counts actual external simv plus phase slots
and unused reservations (plan value0); non-exit /proc read errors fail closed.
Parent still confirms actual service/cgroup/simv progress once after launch.

Checker validates every retired PC/opcode, contiguous retirement, scalar-store
register/address/width/shifted-BE/unshifted-data semantics and strict known bytes.
Each original helper's argument/prologue/VL and accepted/retired index reload
are checked. Each checkpoint requires all72 real checks, double actual loads
of all32 outputs, actual indices/guards and complete39 stored result fields.
Resident retains the original 51st masked helper and its full32-value oracle.

Each fault case requires1650 accepted targets,50 successful retires,1600 actual
exception responses/CSR captures/repairs/MRETs/same-target continuations, with
starts0..31 per round. The checker uses real handler cause/PC/tval/CSR reads,
correct record slots, actual old-PTE load0, correct leaf store, fence/addressed
SFENCE and unchanged fault mepc/scalar context. It does not invent CVX PC/cause
or demand1650 target retirements. Pure CSR reads are allowed; handler/retry
vector data/configuration and index reloads are rejected.

Terminal checks include all32768 backing-word and1536 PTE-word actual scalar
loads, exact21595/5215 check totals, final round/maps/unmaps/minor/fault/mask
counters, error0/exit0/magic, exactly one raw full VECTOR_PASS and
INDEXED_ORIGINAL_PASS, CTRL0, permitted a001 parking only, simulator rc0 and
normal finish. Both console and run.vcs.log veto failures after a success line.

## Negative Coverage And Limits

Read all29 test methods and successor test rebinding; report pins bind those
tests to the final successor/checker/capture. Negatives cover bad/missing fault
CSR/record/MRET/repair/SFENCE/context-reconstruction, reload/target order,
transaction pairing, checkpoint counts/load coverage, values/guards/masked
oracle, missing zero bytes, terminal counters/duplicate exit, corrupted actual
backing load, scalar address/data/BE, malformed CSV, raw failure after PASS,
cancellation/queue failure/interrupted runner, pin drift and resources.

Host positives use synthetic partial/terminal states plus real NF2 scalar CSV
decoder compatibility, not an end-to-end positive CSV for these three new ELFs.
This is an explicit test limit, not a reason to reduce the oracle; pilot performs
the first real end-to-end measurement. Any checker/probe failure must preserve
the original evidence and stop, not be relabeled RTL or automatically retried.

Pilot capture is bounded to1000000ns on frozen ClockPeriod1ns; first complete
checkpoint must be before cycle950000 and FSDB must close/nonempty. This covers
the complete first32-fault round only when that runtime gate succeeds. Token
tests establish static source availability, not measured elaborated signal
availability. CSV acceptance alone does not establish pre-fault VRF timing;
offline wave review remains necessary for that claim.

No original Linux fault batching/signal/scheduler or unknown historical stopped
round is reproduced. Passing these full50-round Sv39 source fixtures must not
be called original Linux/full-parent closure. No new scope/functionality is
required for this launch review. Prepared01 remains invalid and preserved.
