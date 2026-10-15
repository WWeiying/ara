# Actual Host History

Full Host01 was invoked once with run_host.py (600s bound).
Actual pid3045267, wait0, elapsed462.121474342s, no timeout.
23 tests/zero errors or failures; one full4095 constructed stream3017401rows.
No CSV/raw reference read, no DUT/reference/build invocation.

Preflight ABI probe found a fixture mismatch before fullHost: actual e16 startup
has17 prelude instructions and bss-storePC80000046; arithmetic_main stack304B,
return-address80000052. The fixture was corrected from actual ELF before Host01.
This was not a reference model mismatch or DUT/RTL failure.

Startup checker/replay hashes were NOT captured by run_host.py. Therefore
host01_code is a source-text reconstruction, NOT a loaded-code attestation.
While Host ran, only checker.audit timing statements (not called by Host) and
replay.monitored_with_outcome stdout timing wrapper were added. No Strict/spec/
model/transport or fullHost test logic was changed. Existing report pins were
computed at fullHost end; host01_end_code/replay.py preserves exactly that hash.
After the fullHost exit, replay.prepare was extended only to bind this actual
history, end-of-run pins, reconstructed snapshots, and focused timing evidence.

The narrow test_timing_successor.py compares AST of all checker logic except
explicit audit elapsed/progress prints, and all replay logic except uncalled
prepare evidence binding plus the exact timing wrapper. Actual current wrapper
is exercised for0/17/timeout, first numeric persistence, later postcheck error,
sticky abort and no-overwrite. It records pre/post hashes before execution.
No full4095 Host repeat is used to cover this timing-only successor.
The final independent entry must inspect the complete exact diff and plan.

