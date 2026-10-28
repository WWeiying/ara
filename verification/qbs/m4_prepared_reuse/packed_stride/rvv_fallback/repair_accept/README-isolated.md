# Fork-Isolated Private Acceptance

Run `python3 -B verification/qbs/m4_prepared_reuse/packed_stride/rvv_fallback/repair_accept/accept-isolated.py`.
The fresh output is `verification/out/m4-stride-rvv-repair-20261027-04`.

Only the driver is recompiled. Linking reuses the exact frozen -02 repack
object and four normal archives. The generated driver adds sys/wait.h and
unistd.h, then changes only main's case loop to fork, execute one original
run_case in the child, and wait/stop on first failure in the parent. All code
before main, including run_case, remains byte-identical after the two includes.
driver.patch and driver-audit.json record this boundary.

Parent setup uses stdio/environment functions and RVV intrinsics, not GGML
initialization. Each child inherits an unpopulated tensor-decision dedup table.
Normal child exit emits its own coverage report. The unchanged strict
successor check.py still requires a runtime-disabled decision in every case,
plus all numeric, ownership, callback, stride, producer and integrity checks.
The unchanged mutation suite runs against the new raw log.

The single QEMU run has the original CPU settings, xaraqbs=false, and a
180-second bound. Host timing is workflow-only. The prior same-process 704
finite bit-exact outputs, strict failures and incomplete identity audit remain
unchanged and pinned. No global runtime/RTL edits, repack rebuild, installation
or commit. This is private functional acceptance, not hardware performance or
installed-runtime acceptance. Stop after this run and report for parent review.
