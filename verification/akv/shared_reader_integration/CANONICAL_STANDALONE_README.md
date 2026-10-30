# Canonical-source standalone preparation

Preparation for a future canonical promotion, not a promotion or RTL acceptance.
Only new files are introduced. No original TB, canonical RTL, old composer/runner,
snapshot, or pinned source is changed. No VCS invocation is needed for host tests.

## Frozen port contracts

`standalone_port_contracts/{qbs,akv}_engine_legacy_header.svh` archive only the
original engine parameter/port header. They were extracted from the independently
accepted composed wrappers, NOT guessed or regenerated from a promoted engine.
`manifest.json` records header hashes, original TB/vector hashes, original composer
hash, and the accepted wrapper/result/source-manifest provenance. Historical
origin paths are documentation only: normal preparation/execution never reads
the old output directories, snapshot03, or an old canonical engine header.
These header fragments are not compilation units and must not enter Bender.

`compose_canonical_standalone.py` validates the archive and reuses the unchanged
`compose_standalone.compose(header, kind)`. The resulting complete wrappers are
byte-identical to the accepted wrappers. Each instantiates one externalized
production engine plus one real shared reader, not a legacy private-reader engine.
The old counter observation contract is test-only: while owned, use engine
counters; after terminal ACK, expose real physical single-client reader counters.
It does not prove inactive-client metric zeroing or dual-owner arbitration.

Only module naming and `dut.*` hierarchy prefixes change in the supplied TB.
The exact original TB hash is mandatory; QBS also requires the exact reviewed
36-case vector file. No original assertions, expectations, tasks, or vectors are
rewritten. Future legitimate suite changes require separately reviewed contracts.

## Explicit source graph

`run_canonical_standalone.py` requires an explicit repository source root and
flattened absolute filelist. Both Bender-style (defines/include lines) and manual
QBS-style lists are supported. It validates the selected-root external engine,
absence of a private reader instance, one shared reader source, and AKV's unified
storage sources. It rejects nested `-f`, search libraries, relative paths, duplicate
source units, SoC TB/UVM units, and `SYNTHESIS` defines that disable assertions.
The only admitted duplicate is the inherited CVA6 `mock_uart.sv` test model at
its exact declared path, twice, with SHA256
`1bd632e6e7ec0f8395b30378e2c2a0a7b138a4bf4c89e95f6e4f092919c5c470`.
The accepted predecessor already compiled both references and reported the same
OPD declaration warning. Both entries and their order are retained, and the
admission is recorded in the prepared manifest. A changed file, third reference
or any other duplicate is rejected; this does not waive a test result or RTL
behavior. No source flags are silently filtered. Supply a production-only graph.
Whole-line comments are omitted only from a temporary inventory-parser input;
the original filelist is pinned and passed unchanged to VCS.

The existing source-inventory utility pins the declared sources/include headers,
the selected root's Bender/Makefile/config metadata, and DPI dependencies. The
successor also inventories source-local headers. Header additions and symlink
retargeting are checked by rescanning before and after execution. Explicit TB,
vectors, archive, composer/runner/tests, inventory utility, Python/compiler tools,
and generated wrapper/adapted TB are independently pinned. There is no dependency
on snapshot03's input pins or on historical canonical source hashes.

The selected repository root must provide `Bender.yml`, `Bender.lock`,
`hardware/Makefile`, `config/default.mk`, and `config/sram.mk`, as required by the
existing inventory utility. Extra external library sources/headers can be pinned;
the engine/shared-reader/storage modules themselves must belong to the selected
root. A current unpromoted/private-reader graph is deliberately rejected.

## Commands after review and promotion preparation

Host-only tests, including fake source roots/filelists, never execute fake RTL or
fake compiler fixtures and do not represent a hardware PASS:

```sh
python3 -B -m unittest discover -s verification/akv/shared_reader_integration \
  -p test_canonical_standalone.py -v
```

Preparation only (the filelist must already describe the intended new sources):

```sh
python3 -B verification/akv/shared_reader_integration/run_canonical_standalone.py \
  --source-root /absolute/repository --filelist /absolute/production-only.f \
  --kind qbs --tb /absolute/original/qbs_engine_tb.sv \
  --vectors /absolute/original/qbs_command_vectors.txt --output /fresh/qbs-unit
```

For AKV use `--kind akv --tb /absolute/original/akv_engine_tb.sv`, omit vectors,
and choose a separate fresh output. Preparation invokes no compiler/simulator.
After a separate explicit execution authorization and review of the prepared hash:

```sh
python3 -B verification/akv/shared_reader_integration/run_canonical_standalone.py \
  --output /fresh/qbs-unit --execute-reviewed MANIFEST_SHA256
```

Compile and suite each have a 600-second bound with process-group cleanup on
timeout/signals. Use direct systemd ownership when scheduling long execution.
Nonzero exits, error text, duplicate/missing final markers reject; QBS additionally
requires each case 0..35 and all four distinct fault records. Pre/post pins and
header inventory must match. Partial/terminal attempts cannot rerun in place.
No performance, synthesis, PPA, SoC, or production-promotion approval is inferred.

## Real pre-promotion layout fixture

`prepare_canonical_standalone_fixture.py` can consume an accepted storage snapshot
once, without altering it or the current canonical tree. It copies its complete
source closure, then maps these seven byte-identical support files:

| Snapshot support | Fresh fixture destination |
| --- | --- |
| qbs_akv_shared_reader.sv | hardware/src/vlsu/qbs_akv_shared_reader.sv |
| akv_legacy_repacker.sv | hardware/src/vlsu/akv/akv_legacy_repacker.sv |
| akv_q_store.sv | hardware/src/vlsu/akv/akv_q_store.sv |
| akv_unified_context.sv | hardware/src/vlsu/akv/akv_unified_context.sv |
| shared_reader_types.svh | hardware/include/shared_reader_types.svh |
| vlsu_shared_reader.svh | hardware/include/vlsu_shared_reader.svh |
| admission_assertions.svh | hardware/include/admission_assertions.svh |

Source/include paths are mechanically remapped from the already filtered
production filelist. Defines and source order are retained. The receipt records
snapshot/helper/source/artifact pins; it explicitly says NOT_PROMOTED. Bender
metadata is copied unchanged, not regenerated or claimed to implement promotion.
The fixture preparer has an explicit snapshot input; the standalone runner itself
does not. This is preparation/copying only, never a compiler or simulator launch.

```sh
python3 -B verification/akv/shared_reader_integration/prepare_canonical_standalone_fixture.py \
  --snapshot verification/akv/shared_reader_integration/snapshot-03 \
  --output verification/out/canonical-standalone-layout-20261025-01
```

Use that fresh directory as `--source-root`, its `canonical_sources.f` as
`--filelist`, and the original explicit TB/vector paths with the runner's default
preparation mode. Choose separate outputs outside the fixture for QBS and AKV.
Before execution, review the layout receipt and both prepared runner manifests.
