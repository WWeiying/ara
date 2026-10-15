# Timeout Classification In The Current Verification Runner

## Evidence And Cause

The e16/m8 sentinel durable monitor outcome records timed_out=true,
cancelled=false and actual return255 after10800.076115955133 seconds. The
campaign wrapper subsequently sets its shared abort event. The frozen runner
checks that event before its already captured timed_out result, so the public
case status becomes CANCELLED. See
`arithmetic_restart_original/m8_sentinel_mask_static_review_hilbert01/TERMINAL_FAILURE01.md`.

This is a verification-result classification defect, not an RTL defect or a
numerical failure. The original outcome and all historical reports stay intact.

## Current-Source Fix

In `verification/ara_verify/runner.py`, classify the captured timeout before
checking the later batch cancellation flag. A cancellation without a monitor
timeout remains CANCELLED. Existing TIMEOUT returncode representation and
protocol-evidence capture remain unchanged.

The frozen M9 image, its runner copy, approved replay scripts, ELFs and sealed
evidence were not modified. Future campaigns that explicitly consume the
current runner get the corrected label; historical CANCELLED labels must still
be interpreted using their durable monitor receipts.

## Verification

Command from this worktree root:

```sh
env PYTHONPATH=verification python3 -m pytest -q verification/tests/test_runner_contract.py
```

Actual exit0:32 tests passed in3.12 seconds. This includes timeout with and
without a sticky batch abort, protocol evidence retained on timeout, and a
genuine external cancellation retaining CANCELLED and its actual return code.
Tests use bounded mocked monitor outcomes, not VCS, Spike or RTL simulation.

Broader runner and signal-handling regression:

```sh
env PYTHONPATH=verification python3 -m pytest -q verification/tests/test_runner.py verification/tests/test_runner_signals.py verification/tests/test_runner_contract.py
```

Actual exit0:58 tests passed in23.73 seconds. This total includes the32 contract
tests above; the two totals are not additive. No RTL simulator was launched.
