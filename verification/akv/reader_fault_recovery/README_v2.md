# Packed-Member Recovery V2

This is a fixed successor for build02, original run01 and recovery01. The original
13 gate files and the e68824e5 recovery `run.py`, `test_recovery.py`, `README.md`
remain byte-identical. V2 imports their helpers without monkeypatching. All old
source pins are verified in full; there are no source-hash exemptions or archive
substitutions. Both original FAIL receipts remain FAIL.

Only the existing baseline simulation and recovery01's successful actual UVM
are reused. Required recovery01 state is terminal FAIL at `EXTRACTING`, exit1,
UVM exit0, baseline variant, zero baseline/candidate simulation launches. Its
full source inventory must equal the exact approved preflight01 closure. The old
UVM command, cwd, timeout600 and exit0 must match all four checker switches and
the original unfiltered log/trace, ELF and baseline image. The UVM result must
bind those raw hashes and contain actual contract/backend/AXI read/write evidence.
Old extraction command/exit and the raw input seal are also checked and pinned.

`member_profile.successor()` creates new `profiles/baseline.json` and
`profiles/candidate.json` under each fresh output. Only the 45 packed-member
paths change from slash selectors to dotted struct selectors. Aliases, formats,
required flags, clocks, negedge sampling and all other signals remain unchanged.
Prepared source profiles, capture TCL, snapshot, ELF and images are not changed.

Formal execution re-exports baseline's original FSDB into its new `baseline-audit`
directory using the full 0..250000ns window and original strict wave checker.
`--no-events` suppresses only unused events.csv; cycles, raw CSV, metadata and
every sampled signal are retained. Parent's successful complete-window syntax
probe is supporting evidence, not substituted for formal worker validation.
Baseline is not simulated again and its UVM checker is not executed again.
Only after baseline wave/PERF/identity checks pass is candidate simulated once,
with its original capture TCL and the same ELF. Candidate gets fresh actual UVM
on unfiltered files, successor-profile export and unchanged strict semantics.
All71 command records must still match field by field.

## Offline Preparation

```sh
python3 -B -m unittest discover -s verification/akv/reader_fault_recovery -p 'test_*.py' -v
python3 -B verification/akv/reader_fault_recovery/run_v2.py --preflight-only \
  --output verification/out/reader-held-ar-recovery-preflight-20261025-03
```

Preflight hashes and parses only; no GNU, VCS, UVM process or exporter is invoked.
It seals both generated profiles and the reused UVM evidence. It does not accept
the baseline wave or execute candidate. Freeze all files before preflight/run.
Host tests also exercise non-preflight finalization with synthetic external
results: profile paths must be sealed as files, semantic profiles stay separate,
and offsetting per-command cycle differences must retain a REGRESSION receipt.

## Parent-Reviewed Launch Only

Recipe only; no launch authorization is implied. Substitute the reviewed
preflight SHA, and keep service stdout outside the sealed output inventory.

```sh
OUT="$PWD/verification/out/reader-held-ar-recovery-20261025-02"
systemd-run --user --unit=reader-held-ar-recovery-20261025-02 --service-type=exec \
  -p WorkingDirectory="$PWD" -p KillMode=control-group -p TimeoutStopSec=30 \
  -p RuntimeMaxSec=5400 -p StandardOutput="append:${OUT}.worker.log" \
  -p StandardError="append:${OUT}.worker.log" --setenv="PATH=$PATH" \
  /usr/bin/python3 -B verification/akv/reader_fault_recovery/run_v2.py \
  --approved-preflight verification/out/reader-held-ar-recovery-preflight-20261025-03 \
  --expected-preflight-sha256 PREFLIGHT_SHA --output "$OUT" --timeout 900
```

Existing phase bounds and direct service ownership/cleanup are inherited.
There is no automatic retry. A baseline wave failure prevents candidate launch.
The final receipt explicitly distinguishes reused baseline simulation, reused
recovery01 UVM and freshly executed candidate. It claims neither MMU coverage,
production promotion, PPA nor performance improvement.

Parent owns `adapter.py/test_adapter.py` and `member_profile.py/test_member_profile.py`.
Sidecar owns only the three new `_v2` files. No old file is edited by V2.
