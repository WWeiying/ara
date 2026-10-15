# Independent Frozen e16/mf4 Runner Admission

Decision: NO_BLOCKER_FOR_PARENT_CONDITIONAL_ADMISSION. This is a frozen runner
review, not DUT PASS or permission to launch. Parent authorization and runtime
resource admission remain required. No test, disassembly, reference parse,
simulation, build or live/resource query was executed in this review.

## Exact Identities

| Artifact | SHA256 |
| --- | --- |
| prepared01/plan.json | a9a60cc30f3d88d4b15441ec3d2da2bd7367f9334c9cb36731b262bbade50d3e |
| host03.json | dba91d806c73f25d02cad23f08fac4a44834f9df0486c414f82e1a2c46a92545 |
| checker.py | 9034d1e6ab8ccfc68cf1657b7cbf707d15e573cfee5261b313a1f35cb6b30c7d |
| replay.py | 45c03511582bcf2ca75a2ef05259e0d3ea5bcc65d49d0e5685e1daecd7b1e26e |
| test_host.py | 42eaae5e0a5992a131c5bc378301202c39ac19bde0917aa9a25a47d8e396d92a |
| reference READY | f858249f61dc7b9c4e3507f78bb483543d0439ef74942e838fc1251931a661de |
| sourceproof.json | f6efe2b2b360e96d4caa69fef05764bf205040f6c7347033e01cbd19562185af |
| reference REVIEW.md | d9ad719158b37c9a1c1788b1e44fab5f84f06bc0d50a601128d8322cee91dc4c |
| reference result.json | a0cfeb4214f5569092f6acf9cfd4c9539e275b5699e319aa2e36e0d567ba8678 |
| original SoC ELF | eed20f08a98ac66766a66810b6f5f8fc829d0603477d37b3d59d48c32669f162 |
| M6 image ledger | a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0 |
| M6 snapshot | 3cba2d3a6a10c76cb4a2ee0098e3a3755e76b5903920b8b09b0fdadd2999f438 |

All733 plan pins were independently streamed and hashed: zero mismatch,
390381003 bytes, 2.631677s. Confirmed complete inclusion of all107 reference
READY pins, all539 M6 frozen sources and66 image files. Host03 directly binds
the current checker, runner and Host script, and those hashes match the plan.
All six Host01/02/03 JSON/log artifacts are retained and pinned. Reference
source/oracle acceptance is consumed from its independently accepted report
and hashes; its raw was hashed as a pinned file, not reparsed.

## Host History, Not DUT Retries

Host01: zero tests, one setup error, 3.118s. Log reports seed_store fixed-offset
drift. The original draft translated Spike main PCs into SoC by one offset;
SoC GP relaxation invalidates that assumption. Current code locates each exact
encoding uniquely within actual SoC main and rejects ambiguous/missing sites.
It still checks every retired PC/encoding against the pinned actual ELF.

Host02:31 tests,23 errors,51.989s. Logs show fixture register setup StopIteration
and a mock COMPLETE record missing status_counts. Host03 adds the existing
C.LI encoding to synthetic register setup and supplies status_counts={'PASS':1}.
Host02 and Host03 record the IDENTICAL checker SHA above, so this correction
did not weaken production data checks. Current runner consumes host03 and
checks its checker/runner/test hashes; earlier failures are not relabeled PASS.
Earlier script bodies are not claimed independently reconstructed from hashes.

Host03: exactly31 current test methods; stored log reports31 tests in71.260s,
zero failures/errors, PASS_HOST_ONLY. This is not55 and not a DUT result.
Read positive and negative test code; did not rerun it. Coverage includes
source/seed/mask, pointer/arguments, fixture bank, instruction/type/capacity,
NV/vstart/saved CSR/restore, NaN, both guards and tail, missing oracle/loops,
exit/park/truncation, DETAIL monitor, late plan drift, sticky abort and owner.

## Architectural And Terminal Contract

Exactly one canonical e16/mf4 op0 single: scenario3/l4/mode3/frm0/sticky0,
cap16/VL8. All21 helper encodings match original proof; mf4 encodings and
returned VLs64/16/8/64 remain strict. Full input16 halfwords, seed64 halfwords,
mask64 bytes and old-output144 bytes are checked. Fixture bank1/row1545 is
7e00/NV16, not bank0's7c00/0. Entire3360-row traversal/6720 field reads and
initialization counts128/512/215040/144 remain required.

The 144 ordered byte checks include result7e00,126 unchanged destination-tail
bytes and16 unchanged guard bytes. NV16, returned vstart0 and packed16<<32
status are checked. Original frm/fflags save/restore instructions must retire
consecutively with saved zero operands. This tests this zero-saved instance,
not arbitrary nonzero CSR restoration. CSV proves scalar readback, not direct
vector-port observation. Data checks were not widened to accept unknown values.

Both console and raw simulator log require exact singleton original/wrapper
markers, simulator success and finish; failure/DETAIL/abort/trap vetoes remain.
Private ELF, image/command, generic trace and independent counts are mandatory.
Original CTRL zero exit requires full oracle/helper completion; afterward only
the original no-effect park is accepted. COMPLETE must contain exactly one
case and PASS/rc0. End validation freshly hashes/reads plan and checks pins,
image and parent authorization. Checker errors latch abort; late cancellation
cannot become PASS through the existing blocked-signal atomic publication.

## Admission And Remaining Scope

Direct worker MainPID/cgroup identity, loaded/active/running service,
KillMode=control-group, Restart=no and6600s are checked using explicit user-bus
environment. jobs1/case5400/service6600, no build/retry/FSDB, fresh exclusive
launch and replay outputs. Runtime resource gate is deferred; no present host
capacity or reservation correctness is asserted by this review.

Parent must accept timeout risk:2820s is a planning estimate, not measured DUT
runtime;273 retired/s gives6807s, beyond case5400. No automatic enlargement.
Reference actual ISA includes Zfh+Zvfh, unlike the narrower minimum profile.
The independent report accepts this concrete execution with no scalar-FP
consumer; it does not establish exact-profile equivalence or a new DUT result.

Any future PASS closes only this authentic reduced single, not the full6720
Linux program, other rounding/sticky cases, or remaining10 canonical records.
Only this new independent report was written; Tesla's frozen files are untouched.
