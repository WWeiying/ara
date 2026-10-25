# Standalone Makefile Packaging Proposal

New preparation files only. Neither Makefile, canonical RTL/Bender, old composer,
testbench, vectors, accepted fixtures, nor the parent's promotion/wrapper files
are edited. This is not production promotion, compilation or hardware acceptance.

`standalone_makefiles.py` renders exact, invertible changes to
`verification/{qbs,akv}/Makefile`. Its output includes both prospective Makefiles,
a two-file patch and a before/after/helper hash receipt. Apply only as part of the
parent's coherent promotion after the live-pin barrier. It does not apply patches.

`generate_standalone.py` invokes the immutable archived-port-contract composer.
It checks the original TB hash, byte-identical accepted composed-wrapper hash,
and selected-root externalized engine/unified AKV dependencies before generating
`standalone/{composed_engine.sv,original_suite.sv,generation.json}` inside each
build directory. No original header is taken from the new canonical engine.
Only the DUT module name and `dut.*` hierarchy change in the TB; all original
tasks/assertions/expected data remain. The test-only wrapper observes actual
engine counters while owned and real physical reader counters after ACK, as in
the accepted original-suite compatibility fixture. No counters are fabricated.
Generation is repeatable for `make` and refuses unrelated files/symlinks in its
dedicated directory. The receipt pins generator inputs/output but is explicitly
NOT a complete compiler-source manifest; formal acceptance still needs the
canonical standalone runner or a separately reviewed full-inventory worker.

## Preserved Interfaces

- Original target names, `-top` names, timescales, vector filenames/arguments,
  run timeout variables, PASS/error grep checks and all non-engine QBS recipes.
- QBS `RTL_ENGINE_DEFINES`, `RTL_EXTRA_SOURCES`, configurable block adapter,
  FP/half/context/tile-context targets, and their generic/macro flags.
- AKV generic `RTL_EXTRA_DEFINES` and `RTL_EXTRA_SOURCES`, existing Bender targets
  and defines, generic/macro build directories and `RTL_MACRO_VCS_FLAGS`.
- Requested consistency fix: AKV macro and `synth-wrapper-compile` also consume
  `RTL_EXTRA_DEFINES`/`RTL_EXTRA_SOURCES`; wrapper compilation also consumes
  `RTL_MACRO_VCS_FLAGS`. Their extra sources are explicit prerequisites.

QBS's manual list gains the one shared reader after `qbs_read_engine.sv` and
`hardware/include` on the include path. AKV still uses Bender's production list;
the parent's dependency-ordered shared-resources patch must be applied together.
No duplicate shared module is appended to the AKV compile command.

The existing AKV `MACRO_MODEL` already points to
`verification/qbs/qbs_context_sram_macro_model.sv`, which declares **64/76/96/128
x256** functional models. The unified Q store's64x256 model is thus already
included once; do not add a second64x256 declaration. Tests enforce these names.
The parent's future `akv_engine_synth_wrapper.sv` replacement remains separately
required. This proposal changes only its compile recipe flag plumbing, not the
wrapper, DC scripts, synthesis filelists or PPA expectations.

## Host Preparation

```sh
python3 -B -m unittest discover -s verification/akv/canonical_promotion \
  -p test_standalone_makefiles.py -v
python3 -B verification/akv/canonical_promotion/standalone_makefiles.py \
  --source-root "$PWD" \
  --output verification/akv/canonical_promotion/standalone_package
```

Tests execute only Python and GNU `make -n`, never compiler/simulator commands.
They check inverse patches, target/run recipe preservation, flag/extra-source
routing for QBS, AKV generic/macro and wrapper compilation, all macro depths,
original-TB inverse, accepted wrapper hash, and malformed/private-engine rejection.

For an existing immutable future-canonical layout, generation can be checked
without changing that fixture:

```sh
python3 -B verification/akv/canonical_promotion/generate_standalone.py \
  --source-root verification/out/canonical-standalone-layout-20261025-02 \
  --kind qbs --tb verification/qbs/qbs_engine_tb.sv \
  --output verification/out/canonical-makefile-packaging-20261025-01/qbs
python3 -B verification/akv/canonical_promotion/generate_standalone.py \
  --source-root verification/out/canonical-standalone-layout-20261025-02 \
  --kind akv --tb verification/akv/akv_engine_tb.sv \
  --output verification/out/canonical-makefile-packaging-20261025-01/akv
```

The layout's Bender.yml is historically unchanged, so use its accepted flat
`canonical_sources.f` for any dry-run AKV command inspection; do not mislabel a
fresh Bender extraction from that fixture as the promoted source graph. No VCS
or synthesis execution is part of these commands. Actual compile/suite evidence
after applying the coherent package is a separate authorization and gate.
