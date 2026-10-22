# Full682 Worker Interface Finding

No DUT was launched by this review. This is a verification integration
finding, not a new production RTL fault.

## Confirmed Schema Mismatch

The initial `checker.artifacts` tested `generic['status'] == 'VALID'` after
calling `ara_verify.trace.validate_trace`. The real implementation returns
count fields and raises `TraceValidationError` on rejection; its successful
return has no `status` key. The initial composition would therefore fail
with `KeyError` even for a valid completed trace.

Main executed the real validator on a temporary three-record witness with
one vector request, matching response and retirement. The process exited
zero, confirming `status_key_present=false`. The temporary generated file
was removed; no sealed trace or shared validator was modified.

## Required Event Presence

That same real validator accepted zero architectural-request and backend-uop
events. This is not automatically a defect in the generic validator, which
can serve traces without backend instrumentation. However, this campaign
explicitly promises the frozen six-event trace. Its composition must enforce
the expected architectural and backend event presence/counts, in addition to
the generic ID/order/instruction matching and the full scalar oracle.

The worker owner and independent reviewer were notified before admission.
Require a Host test using the actual validator schema, plus rejection of a
complete removed event family, before accepting the revised worker binding.
Do not fix this by adding a fictitious status to a mock or weakening the
published lifecycle claim.

## Revised Composition: Independently Retested

The worker owner removed the nonexistent status-key assumption and added
`protocol_gate`. It compares actual CVX/architectural instruction sequences
against the offloads observed in the strict original-helper retirement audit,
checks equal request/response/architecture/retirement counts with no exception
or replay, and requires backend allocation for every offload that needs it.
The shared validator continues pairing each actual allocation/completion.

Backend presence does not incorrectly require a uop for vector configuration
or a VL0 comparison target. Actual dispatcher source suppresses non-config
execution when vstart>=VL; source/mask loads and result stores in these helpers
use CAP512, so they remain required. The archived accepted first50 count is
consistent with this classification, not a replacement for the new DUT run.

Main independently executed `python3 -B -m unittest test_worker.WorkerTests
-v`: seven tests, 3.386 seconds, actual exit0, `OK`. Tests use the actual
shared lifecycle validator for missing-family and bad-transaction cases;
they also exercise the frozen parent runner's numeric-before-postcheck
handling, console contracts, timeout receipts, late abort, wrong membership,
plan drift and resource/budget gates. No DUT simulation was launched by this
test command. Final independent binding and VCS admission remain separate.
