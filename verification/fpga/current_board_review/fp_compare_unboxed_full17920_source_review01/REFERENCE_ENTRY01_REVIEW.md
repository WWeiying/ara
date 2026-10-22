# Reference Entry01 Review

Decision: **HOLD_ENTRY_HOST_IDENTITY_GATE**. Do not execute this entry yet.

## Blocking Finding

`reference_entry01/execute_once.py:45-48` loads pinned input identities, then
adds the *current* host.wait.json and host.log hashes. Neither Host file is in
input_pins.json. ENTRY contains host_wait_sha256, but the executor never compares
it. The receipt's log_sha256 is likewise unused. Thus replacing the reviewed
Host receipt with another numeric0/timed_out=false receipt and replacing its log
after review leaves ENTRY/review/checker/input_pins unchanged, yet this gate
accepts and records the replacements as its starting baseline. This violates
the exact reviewed-Host prerequisite. `False == 0` also passes the existing rc
test, so the replacement need not even contain a numeric exit.

Current evidence is not bad: all88 input pins freshly match, the actual22 short
tests passed with numeric0/2.874s, and the actual receipt/log hashes match the
declared values. The finding is the missing execution-time identity check,
not a failed oracle, reference attempt, source defect or RTL issue.

Minimal repair: preserve this entry, use an explicit successor executor/entry;
before adding the Host files to the runtime pin set, require actual receipt hash
equal the exact reviewed ENTRY value, actual log hash equal the bound receipt
log_sha256, type(returncode) is int and value0, timed_out is False. Short static
gate negatives must reject changed receipt, changed log and boolean rc. No repeat
of22 checker Host tests, compile, model or reference is necessary for that delta.

## Other Reviewed Scope

Source/spec bind the new Spike ELF0ecbd714..., CAP16/vtype14/DK0, all32 raw
scalar seeds including nonzero values, the complete17920 order and185 original
helper encodings. Per-call phase checks require41 stores,8 interleaved input LDs,
one full output LWU and the correct record every8 calls (2240 total). Expected
inputs/flags/allowed tail bits are source-model derived. The checker verifies
caller s6/sticky preservation, exact helper continuity, source vector contents,
raw LHU/FMV.D.X, fixed old5b5b, returned flags/vstart, result bytes and both guards.
Unused backing input BSS must remain zero. Unknown initial callee-save values
are permitted only at the actual initial spill PCs; memory loads are checked
against written/ELF bytes, rather than unknown GPRs defaulting to zero.

Actual bootstrap and failure PCs are from the new ELF. HTIF success requires
PC8000007a/value1 and complete scope. Audit continues through EOF, allowing only
side-effect-free8000007e/a001 park after success. Nonpark activity, partial EOF,
trap/diagnostic paths and original failure output are vetoed. Saved CSR operands
are checked; no nonexistent post-restore readback is claimed.

The fixed command remains rs4000000;quit,120s,768MiB per-file FSIZE cap, one
closed audit600s and firmware3M. FSIZE is not RSS. The new reference01 directory
is exclusive; raw/input hashes are checked before and after audit, failures stay
NOT_ACCEPTED with no retry. Existing numeric wait receipts precede semantic
acceptance. This review does not execute tests/reference or query the e32 observer.

After the narrow identity repair and exact successor review, no other currently
identified blocker requires changing source, checker, budgets or scope.
