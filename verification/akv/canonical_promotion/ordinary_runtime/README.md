# Actual Canonical Ordinary Runtime Gate

Preparation only. No EDA, canonical edits, baseline rerun or new ELF construction.
This new directory consumes the frozen `ordinary_baseline.Consumer`; it does not
modify that consumer or any old worker. No old overlay `checked_soc` is called.

## Identity And Work

The reviewed canonical build result SHA is required explicitly. Its state must be
`CANONICAL_SOC_BUILT_NOT_EXECUTED`, schema `canonical_soc_v1`, actual-root identity,
terminal compiler exit zero, and strict typed post-pins/execution fields. All19
promoted after hashes are checked through the frozen canonical builder guard.
The original lock/config/Bender identities, compiled source graph, exact UVM/DPI
extras, complete executable/config/manifest/shared-library inventory, and required
build artifacts/helper pins must match. The generated source manifest is rescanned
against the actual canonical root. Compile-log admission is replayed using the
unchanged strict two-lint/TLB validator. This is not a snapshot receipt adapter.

The historical consumer retains the original same-ELF/crop/image/UVM/raw proofs
and translates only the fixed five hardware/build and two software identities.
Those archived pins are merged with the independently checked current canonical
pins without substituting new bytes for historical hashes. All other old pins
still require their exact bytes. No source/image checks are waived.

The exact original `ordinary_resource.run.simulation_command` is reused. The ELF
executes RVV/generic/paired/paired/generic/RVV on the captured KV128 derived
four-head subset, 512outputs/call; no full-model claim. Original raw/protocol/compare
functions are called unchanged. All3864 per-command records/fields and summary
must match the baseline, corresponding checksum/FCSR/VCSR/work must match, and
each complete-call cycle count must not regress. One slowdown fails this strict
resource gate; valid functional measurements and comparison are retained. A
faster other call cannot offset it, nor can opposite hardware-counter changes.

The independent UVM checker requires actual event/backend/AXI read/write evidence
on the unmodified raw log/vector trace and current image. `contract.protocol`
binds that proof to the original ELF and exact raw hashes. Commit trace is also
sealed. Actual simulator exit zero is mandatory. Pre/post source-manifest checks,
all input pins and image inventory checks precede final acceptance.

## Ownership And States

The original foreground Execution owner provides process-group timeout/signal
cleanup. Simulator timeout is1..10800s (default9000s); use a direct systemd service
with a10800s overall bound and cleanup grace. The worker launches one simulator,
never a baseline rerun or retry. UVM/manifest/image-contract commands are bounded
host verification phases. Preflight launches NO process at all and reports only
`CANONICAL_ORDINARY_PREFLIGHT_NOT_RUN`, simulations_launched=0, without a simulator
exit/acceptance claim. An unpromoted canonical tree is rejected.

Success is `PASS` with acceptance `CANONICAL_ORDINARY_SAME_ELF_PASS`. It is a
functional/resource regression gate, not automatic deployment approval or PPA.
FAIL/TIMEOUT/INTERRUPTED cannot yield this acceptance. On nonregression failure,
the complete raw/functional evidence and comparison remain available.

## Host Tests And Future Commands

```sh
python3 -B -m unittest discover -s verification/akv/canonical_promotion/ordinary_runtime -p 'test_*.py' -v
```

Tests use synthetic receipts and mocked external execution, never RTL execution.
They cover strict typing, missing pins, image/source/manifest drift, rejection of
overlay receipts, exact command/checker flags, no-process preflight, formal
PASS/FAIL receipt finalization, offsetting regressions and interrupted/failed
execution. These tests do not establish an actual canonical build or runtime PASS.

Only after actual promotion, canonical build review and separate authorization:

```sh
python3 -B verification/akv/canonical_promotion/ordinary_runtime/run.py \
  --soc-build /absolute/new-canonical-build --expected-soc-sha256 REVIEWED_RESULT_SHA \
  --preflight-only --output verification/out/ordinary-canonical-preflight-REVIEWED

systemd-run --user --unit=ordinary-canonical-REVIEWED \
  --property=Type=exec --property=KillMode=control-group \
  --property=RuntimeMaxSec=10800 --property=TimeoutStopSec=30 \
  --property=WorkingDirectory=/home/wangwy/openproject/ara_dsa_signoff_integration \
  /usr/bin/python3 -B verification/akv/canonical_promotion/ordinary_runtime/run.py \
  --soc-build /absolute/new-canonical-build --expected-soc-sha256 REVIEWED_RESULT_SHA \
  --timeout 9000 --output verification/out/ordinary-canonical-REVIEWED
```

Use fresh outputs; existing outputs cannot be resumed or overwritten. These
commands have not been executed by this preparation. Baseline/build selection is
fixed by the reviewed consumer, not caller-selectable and not a cross-model test.
