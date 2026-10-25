# Reader Fault Recovery

This successor recovers only the completed baseline simulation in
`verification/out/reader-held-ar-run-20261025-01`. That worker remains **FAIL**:
its frozen log parser interpreted the simulator's command header as an unknown
injection record. The baseline simulator exited zero, but its worker never
completed the actual UVM or waveform checks. Neither shim PASS nor log-only
acceptance is overall acceptance.

No existing file, RTL, test stimulus, ELF, image, or raw record is rewritten.
The reviewed build is `reader-held-ar-build-20261025-02`, SHA256
`2ee6fc2d5e8372f7a22f938055c9648038d3694aeecfe2485383f491c5402aba`.
Its original 71-command program and weights at `0x80002e80` (432 bytes) are
unchanged. There is no build command and no baseline simulator invocation in
this worker. Only the candidate simulator may be invoked, once per invocation,
after baseline UVM, waveform, source/image identity and semantic checks pass.
There is no automatic retry or resume after a candidate attempt.

## Identity And Recovery

The exact old FAIL reason, baseline-only variant, zero simulator/manifest/L2
exits, terminal child state, reviewed build association and old source pins are
required. Original console argv is independently reconstructed from the reviewed
build/prepare recipe and checked together with cwd, timeout900 and exit0.
Existing candidate output under run01 is forbidden. The adapter verifies one
leading command header against that argv; only the semantic parser receives its
body. **Actual UVM always reads the original unfiltered log and vector trace.**

Offline preflight hashes the completed baseline log, trace, FSDB, console,
command/exit receipts, old status/result, original source inventory, and consumed
diagnostics. This is explicitly a new post-termination seal, not an original
clean-worker acceptance. It also verifies current build/image/source graphs and
exporter tool inventory. A later run requires the exact approved preflight SHA
and matching full input inventory. Changed raw evidence fails closed.

Baseline postprocessing writes only into the fresh successor's `baseline-audit/`.
FSDB export uses the original pinned profile and 0..250000ns range. Required
signals, settled negedge samples, the independent AXI ledger, fault/drain,
resident-context preservation and PERF/wave association remain the original
checks. The same full checks then apply to the fresh candidate. All71 command
records are compared field by field; a difference produces REGRESSION, never an
aggregate-only PASS. MMU, PPA, deployment and performance gains are not claimed.

## Offline Preparation

Host tests do not launch any EDA tool:

```sh
python3 -B -m unittest discover -s verification/akv/reader_fault_recovery -p 'test_*.py' -v
python3 -B verification/akv/reader_fault_recovery/run.py \
  --preflight-only \
  --output verification/out/reader-held-ar-recovery-preflight-20261025-01
```

Preflight performs only Python parsing, hashing and identity checks, not VCS,
GNU, UVM execution or FSDB export. `preflight.json` is not functional acceptance.
Freeze all five recovery files (including the parent's adapter/test) before
preflight; do not add or edit files while the consumer runs.

## Reviewed Launch Only

The following is a recipe, not an authorized or executed launch. Use the exact
reviewed `preflight.json` SHA in place of `PREFLIGHT_SHA`.

```sh
OUT="$PWD/verification/out/reader-held-ar-recovery-20261025-01"
systemd-run --user --unit=reader-held-ar-recovery-20261025-01 --service-type=exec \
  -p WorkingDirectory="$PWD" -p KillMode=control-group -p TimeoutStopSec=30 \
  -p RuntimeMaxSec=5400 \
  -p StandardOutput="append:${OUT}.worker.log" \
  -p StandardError="append:${OUT}.worker.log" --setenv="PATH=$PATH" \
  /usr/bin/python3 -B verification/akv/reader_fault_recovery/run.py \
  --approved-preflight verification/out/reader-held-ar-recovery-preflight-20261025-01 \
  --expected-preflight-sha256 PREFLIGHT_SHA --output "$OUT" --timeout 900
```

The Python worker directly owns the service and inherited subprocess cleanup.
Bounds remain simulator900s, UVM600s per variant, export300s per variant,
manifest300s and image contract180s. Failure of baseline postprocessing stops
before candidate launch. Cancelled/timed-out jobs retain their evidence; do not
automatically launch another candidate. Active service stdout, status and final
self-receipt are excluded from closed output evidence.

The final receipt labels `original_worker_state=FAIL`,
`original_clean_pass=false`, baseline reused and candidate freshly executed.
It binds the original raw inputs and new UVM/export/semantic artifacts separately.

Ownership: `adapter.py` and `test_adapter.py` are parent-owned;
`run.py`, `test_recovery.py` and this README are sidecar-owned. The original
13-file reader_fault_gate directory remains frozen.
