# E32 Full5985 Terminal Metadata Review

Decision: **ACCEPT_E32_FULL5985_TERMINAL_METADATA**. No blocking findings.
This review consumed the completed one-pass auditor and worker reports; it did
not reopen DUT CSV or reference commit logs, launch simulations, or edit sealed
worker/checker/profile/plan/results. Review process actually exited0.

## Verified Terminal Evidence

- Standalone worker complete: PASS_M6_FULL_ORIGINAL_E32_MF2_5985_CALLS_NOT_LINUX,
  COMPLETE/PASS1, retries0, abortedfalse, unchanged pins and no failure reason.
- Actual simulator numeric exit0,10026.130593s, no timeout/failure/cancellation.
  Exact private command/ELF/image provenance remains bound by verified evidence.
- Actual independent audit child PID1787106 waited exit0,238.399099s, attempt1,
  no timeout/error; this was within its900s limit. No failure marker exists.
- Terminal -> candidate -> per-case report, complete, actual exit and raw-hash
  chains match. All899 unique nonraw input/evidence pins match current files.
  Two original reference commit logs and the DUT CSV were deliberately not
  opened; their recorded hashes remain bound to the prior accepted audits.
- All5985 call-ledger entries match the pinned original model's op/seed/VL/
  mask-mode/vstart order, exact target PC and18 result/guard reads, returned
  vstart0. All35 operations and3 original seeds are present. Full oracle/setup/
  global-RNG semantics are supported by the unchanged Strict full traversal,
  not by a fresh raw interpretation in this metadata review.
- Independent strict/generic reports exactly equal the worker reports.

| Complete Scope | Count |
| --- | ---: |
| Original ordered calls | 5985 |
| Results | 95760 |
| Guards | 11970 |
| Returned vstart checks | 5985 |
| Original helper instructions | 77805 |
| Capacity calls | 1 |
| CSV rows | 6187577 |
| Retirements | 5922689 |
| CVX requests/responses/architecture starts | 65838 each |
| Backend allocations/completions | 33687 each |
| CVX exceptions/replays/architecture replays | 0 each |

Six-event counts sum exactly to6187577 rows. Firmware through original CTRL
raw0 ends at retirement5922683, followed by6 parking retirements; last cycle
8719182. No explicit fflags oracle exists in the original source and none is
claimed. Source is the previously accepted byte-equivalent reconstruction,
not a claim that original C bytes were recovered.

## Identity And Limits

REVIEW.json SHA: `19ce884e694dc2c8bfa92a7be64a25368e936ebe7c7ced30b04d367a9927f2d5`.
Terminal SHA: `35a6f06b6be566ac5c60e13ab70e27768c5a527bdab87c5ffb6f69f2dc961fcf`.
Worker complete SHA: `5ff4a9561be0460029a683be1f8864147bf0734acc7290882eb63cc9edb2e7e7`.
Actual audit exit SHA: `be515a548f45aaa3fe2955c7b16539132731670f35af00dd853814281d31de28`.
Single-pass raw SHA: `ea88e975a6cb538756bb41b0472f50cf19b886bdfffaadd600567165331c4eca`.
Current raw size713074111 bytes was stat-only, not rehashed or reparsed.

The recorded pidfd event proves original worker1691221 exited; the audit found
its cgroup removed. No current live-process scan was needed. Historical outer
systemd exit remains UNCONFIRMED_NOT_INFERRED. This is acceptance of the new
standalone full e32 mf2 SoC run only, not Linux/all22 or relabeling the original
Small2 batch. Old e32 CANCELLED and whole2 NOT_PASS remain unchanged. Main owns
the aggregate CURRENT_SCOPE/coverage update.
