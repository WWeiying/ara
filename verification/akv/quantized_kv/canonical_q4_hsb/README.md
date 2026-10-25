# Canonical Q4 H/S/B

New same-ELF paired experiment only, not continuation of an old ELF or its cycle
measurements. No whole-model, hardware-only or deployment acceptance is implied.
Parent approved this boundary despite timed main changing from 713 to 717 static
sites. Timed source SHA-256 is preserved, but timed machine identity is false.

Only these three files are owned here: `run.py`, `test_run.py`, `README.md`.
The frozen consumer receipt is
`verification/out/q4-untimed-verify-fixed-layout-20261025-01/consumer-evidence.json`,
SHA-256 `1275b929a431f877ee437bae878f6b85c3338ff2d2ef14d4a40925bada7bfbbc`.
ELF SHA-256: `8203039cf8f16afabc6d76b0d28f148af551f95300df34a912ddd561b503ff1d`.
Timed source: `88e43efe2b0cbd5f184b6f3fdd1693a063b3fb39fd1e03ff64d79bc3c63f1064`.
Canonical build02 receipt:
`e554e706c54298aaf98ff6cfafc23e2c1fd23c6eba4da44c8b80be0da5103724`.

Admission verifies the fixed schema/state and typed flags, complete artifact map,
all before/after/after-link maps and digests, all sixteen unchanged nonmain object
pins, explicit 32-data-symbol/36-function layout evidence and accepted main
machine difference. It recomputes the exact source render/inverse/provenance and
binds the actual Q4 capture gold to the linked tensor payload. These are review
evidence checks, not a new compiler/disassembler run or an independent ELF audit.
Only `canonical_runtime_v2.checked_soc` admits the current actual image. No old
`checked_build`, historical image validator or old-live-header comparison runs.
Pin merges reject collisions; all consumed sources, helper modules, scripts,
program evidence and current image inputs are rechecked before/after execution.
Shell tools use `/usr/bin:/bin` with pinned `/usr/bin/readelf`; shell startup and
Python startup overrides are removed from the inherited execution environment.

The original `check_threeway_attention.check_log` is loaded unchanged and runs
against actual Q4 capture gold and current canonical VLSU schema. It checks all
six H/S/B/B/S/H trials, 768 outputs each, repeats, FCSR/VCSR, work counts and all
sixteen QBS records. Simulation argv is the old three-way argv, with only the
new ELF/image/work paths. The unfiltered UVM checker requires events, backend,
AXI and AXI writes; its raw log/trace hashes and ELF/image identity are bound.
Manifest checks bracket execution; `check-sim-l2.sh` runs before the simulator.
Existing direct `Execution` owns foreground phases and cleanup. There is one
10,800-second simulator attempt, no timeout extension, retry or repair. Failure
reports retain partial raw evidence and never claim acceptance.

Offline preparation, after parent review:

```sh
python3 -B verification/akv/quantized_kv/canonical_q4_hsb/run.py \
  --output verification/out/NEW_Q4_PREFLIGHT --preflight-only
```

Preflight performs no subprocess/EDA phases and yields
`CANONICAL_Q4_HSB_PREFLIGHT_NOT_RUN`, not simulation PASS. The CLI accepts only
`--timeout 10800`; `--soc-build` defaults to the pinned build02. Without
`--preflight-only` the command executes EDA, requiring separate parent approval
and an independently owned service/output after the existing worker finishes.
This implementation task does not authorize that execution.

Host verification:

```sh
python3 -B -m unittest discover \
  -s verification/akv/quantized_kv/canonical_q4_hsb -p 'test_*.py' -v
```

Tests use offline receipt inspection and mocked phases. Synthetic transcripts
are checker tests, not numerical DUT evidence. Freeze these files after review;
use a successor directory for later changes once a consumer pins them.
