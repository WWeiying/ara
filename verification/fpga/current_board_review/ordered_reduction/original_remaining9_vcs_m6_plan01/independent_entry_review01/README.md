# Independent remaining-nine M6 entrance review

**CLEAR for the sealed preparation below; not launch authorization or DUT acceptance.** No unresolved entrance blocker was found. The two pre-freeze blockers are fixed. Actual independent mf4 DUT acceptance and a new parent authorization remain mandatory runtime prerequisites.

Plan: `prepared01/plan.json`, SHA256 `10807a26d22d6beb48acdd075e3e1ccea37e5ca69f38c783ce2ed9027375891a`.
Worker: `replay.py`, SHA256 `ca22d0134b40d53fb14534b853128d1ae20362c8cdd2b289566ab4b44536bab8`.
Checker: `checker.py`, SHA256 `2e92159b44879c96e2faca67cec3744d08c2633d507abd3d0afc91cf6f65ee15`.
Host02: SHA256 `7d2a76d8ccced172d1de3ceb6aa0606c111db71ec716974b03490eea99d46b68`.

## Evidence and scope

Independently hashed all 1352 plan pins before testing and rechecked all after testing. The shared executed `integration/prepare.py`, shared replay/publication modules, frozen runner/trace modules, M6 image/snapshot/configuration, nine original SoC ELFs, source/reference evidence and both Host generations are covered. Additional review inputs, including `FROZEN.md` and the producer's old-Timer counterexample, are recorded in `review_input_pins.json`.

Validated the actual plan and accepted reference bindings. Independently decoded ELF load segments and compared all 5816 instruction-map entries against their actual bytes. The nine shapes are e16 mf2/m1/m2/m4/m8 and e32 mf2/m2/m4/m8. Each retains the original single selected call, contiguous 21-instruction op0 sequence, complete forbidden op1/op2 ranges, seven legal startup/C CSR sites, three-instruction capacity sequence, original surrounding initialization/fixture loops and complete 144-byte scalar oracle. The source and compiled LD/XOR/store paths agree with the checker's e32 write-data semantics. The generic checker establishes CSV request/response/retirement consistency; scalar stores use address-shifted byte masks and unshifted low-byte data. No direct vector payload or waveform claim is added.

Isolated rerun: **17 methods, 431 recorded checks, zero failures/errors**. This includes the exact 15-method/44-check Host02 selection, all nine complete synthetic CSV positives with both generic and strict validation, and all 378 unused-helper-PC negatives. The original Host01 92-case data/control negative matrix was inspected and retained through its exact immutable hashes, not claimed rerun. Temporary fixtures and rerun outputs were confined to this independent review directory; sealed producer files were not modified.

Host01 remains `HOST_FAIL`, 17 methods/548 recorded checks, with two failures. Both are diagnostic assertions expecting `op0 interior` where the checker correctly rejected the duplicate entry with `Duplicate RVV retirement`. The frozen log confirms the two exceptions. Host02 binds the exact original worker `04a66a0ef74214d4605b9c128edb3ea0ed591049ebfd0482f38a96405977e758`, unchanged checker/test source and Host01 evidence, corrects both assertions, and tests the declared runtime changes. Full source diff inspection confirmed the changes are confined to option construction, deadline quiescing, proof strengthening and Host02 preparation/pins.

## Closed blockers and runtime gates

1. **jobs/seed inversion closed.** The original positional call supplied jobs1/seed3. The replacement uses named arguments, jobs3/seed1, and the actual frozen RunOptions plus process-free dry-run command check passed. The dry-run printed a command but never executed simv.
2. **Timer/publication race closed.** The original Timer could set the sticky Event after the publisher's final `is_set()` read but before its final pending-signal query, allowing PASS. Independent opcode-boundary reproduction used an actual Timer/Event and the real `sigpending()` syscall, without a pending-set mock. The revised worker cancels and joins its Timer, preserves any callback's abort, and samples/latches an expired monotonic deadline before publication. Frozen executor workers have already joined on return. Seven independent cases passed: old race reproduction, joined callback rejection, actual expired-deadline rejection, and real SIGINT/SIGTERM on either side of the final pending-set snapshot.

The signal decision is the kernel snapshot inside the final `sigpending()` query, after worker/Timer quiescence; it is not rename or Python call return. Signals arriving before that snapshot reject PASS. Signals after it do not revoke the accepted decision. The worker deadline is explicitly sampled after Timer join; the outer service bound remains separate.

Simulation failures, strict-check exceptions and cancellation share one sticky Event. Queued tests observe it before simulation; active private process groups are stopped by the frozen monitor. A test already admitted can encounter cancellation during startup and is then cancelled by that monitor. Final acceptance requires exact nine COMPLETE/PASS rows, exact metadata, fresh disk plan SHA/content and pins, fresh image validation and unchanged approval evidence. Failed or cancelled artifacts and summary rows are retained.

The mf4 gate now requires explicit report/audit/terminal hashes and evidence keys, exact independent audit status, plan/image identity and matching terminal SHA, plus exact single-result PASS/no-abort/elapsed checks. The parent authorization separately binds the mf4 proof SHA, this plan SHA, reference review, unit and budget-risk decision. Synthetic positive/negative fixtures exercised this schema; this entrance review did **not** read or accept the actual mf4 DUT run or its live state. The eventual parent-selected proof must refer to the actual independently reviewed artifacts.

## Limits

jobs3/seed1; each case 5400 seconds; worker cancellation deadline 18900 seconds; direct systemd unit bound 19800 seconds; no build, FSDB or retry. Admission requires enough unchanged case budget plus 600 seconds of validation allowance. Runtime resource admission is deferred to authorized execution and checks the live process count/reservations and available memory. No live resource or service query was made here.

Nine reduced single-call programs and their 1296 scalar oracle bytes are not nine full 6720-call Linux parents. The parent-reported mf4 3470.2-second result is only a limited cost proxy; it neither proves the remaining LMUL cases nor guarantees completion inside 5400 seconds. Runtime prerequisites, numerical/DUT acceptance and parent authorization are not waived by this review. No DUT, reference/Spike execution, build, service launch or live query occurred.

Reproduction/evidence: `host_review.py`, `host_review.log`, `host_evidence.json`, `boundary_review.py`, `boundary_evidence.json`, `static_evidence.json`, `review_input_pins.json`, and `findings.json`.
