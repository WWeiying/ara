# Newly Confirmed Owner Exception

This supersedes the unqualified required-target-owner statement in this
directory's entry review. Preserve the original review/result and running
sealed worker unchanged. No service action, active CSV read or execution was
performed for this addendum.

Aquinas supplied `slide_noop_owner_contract_review01/REVIEW.md`. Independent
inspection of frozen M9 `ara_dispatcher.sv` confirms:

- 2330-2340: VSLIDEUP.VI unsigned immediate becomes stride; stride>=VL sets
  null_vslideup.
- 5349-5351: this no-op bypasses layout maintenance.
- 5970-5978: successful direct response suppresses ara_req_valid.
- 5997-6001: successful response resets architectural vstart.

Thus source op19 `0x38813c57` (slideup immediate2), VL1/2,start0, may legally
have no backend owner. Current checker `start<VL` alone overconstrains these
calls. The entry review missed this RTL-specific no-op exception; its prior
Host-positive owner generator mirrored the same predicate, so passing those
synthetic tests did not establish this contract.

Source-loop arithmetic predicts18 affected calls (3seeds*2VL*3masks), reducing
the required target minimum2610 to2592 and total23085 to23067. These are static
predictions, not an observed DUT owner recount or terminal failure. All20475
memory-helper owners and117 nonempty op24 targets remain required. VL3
slideup, slidedown VL1/2, and masked-off ordinary targets are not exempt.

Keep the live run and original terminal result intact. If authorized after
closure, a separate offline successor may recognize only the exact decoded
slideup no-op, retain full data/guards/history/vstart and lossless malformed-
event rejection, and preserve actual numeric execution evidence. No silent
replacement of the sealed checker, rerun, or acceptance based on this static
prediction is warranted.
