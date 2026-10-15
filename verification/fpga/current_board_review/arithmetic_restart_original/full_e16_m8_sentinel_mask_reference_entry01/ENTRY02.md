# Exact Reference Successor

ENTRY.json remains HOLD; no reference was dispatched under it.
ENTRY02.json consumes reference02.py/reference_check02.py.
Only changes: nonempty unparsed raw lines reject (blank lines remain allowed),
and firmware_to_HTIF, rather than firmware_to_exit, drives the <=3000000 gate
and READY firmware. Both counters remain in full result.
HOST02 13 actual-PC/source fixtures remains accepted and unchanged.
HOST03 adds 5 small parser/EOF/cost-boundary tests, not fullstream/raw proof.
No recompile, fullstream Host, reference or DUT was used to create this entry.

Independent JSON schema unchanged from README:
status=NO_BLOCKER_SOURCE_SOFTWARE_FOR_ONE_BOUNDED_REFERENCE_NOT_DUT,
entry_sha256=actual ENTRY02 hash, one_attempt=true, DUT_authorized=false.
Only execute reference02.py execute --review PATH --review-sha ACTUALSHA
after that exact independent gate. Existing conditional parent authorization
allows one finite reference and one closed audit, not VCS.
