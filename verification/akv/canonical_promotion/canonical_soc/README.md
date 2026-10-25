# Canonical SoC Compile Preparation

No EDA was invoked to prepare these helpers. Current canonical RTL/Makefiles and
all existing sealed helpers remain untouched. This worker never runs simv,
synthesis, Verilator, coverage, containers or a simulator acceptance test.

## Admission

The first operation checks the exact accepted coherent plan and ALL nineteen
canonical after hashes. An unpromoted/partly promoted tree fails before output
creation, tool discovery or any subprocess. Only the actual signoff root is
admitted, never snapshot03. Bender.lock, config/default.mk, config/sram.mk and
the installed Bender binary retain their explicitly locked hashes. Missing or
nonexecutable Bender is fatal. `make -o /absolute/hardware/bender` additionally
disables the inherited bootstrap/download recipe; the worker never downloads it.

After separate promotion/build authorization, the only build command is the
original `hardware/Makefile` `compile` target. Absolute independent `buildpath`
and `sim_dir` point into a fresh output, with all four original canonical UVM
sources. The exact settings are qbs=1, akv_v2=1, qbs_vrf_continuation=1,
sim_l2_mb=16, nr_lanes=4, vlen=1024, no_fsdb=1, verify_source_manifest=1,
verify_uvm_cvxif=1, fail_on_assert=1 and verify_axi_delay=0. Other model/coverage
overrides are explicitly disabled. No old objects are reused; DPI objects are
built by the same Makefile in the independent directory using /usr/bin/g++.

The pinned old Bender list is used ONLY as an ordered dependency/define template,
not as an old source-hash validator. Its four promoted SV additions follow the
accepted dependency order. Include fragments remain includes, not source units.
The two inherited duplicate units are retained at their exact path/hash/count;
additional duplicates, private-engine readers, snapshot paths or graph changes
reject. The actual Bender-generated filelist must match this template exactly.
The `script verilator` output format and legacy DPI header location do NOT mean
Verilator is invoked.

Before make, current source/header closure, DPI source/installed headers, Bender
metadata, plan targets, tools, helpers and compile-admission evidence are pinned.
Closure/inventory and hashes are checked afterward. The generated manifest must
name the actual root, exact new filelist/DPI object and four canonical UVM sources;
every nongenerated compiled input must already have a pre-build pin.

The only reused compile admission is `executor_common.check_soc_compile`: exact
full argv, exactly two historically reviewed monitor PCWM lint blocks and the
unchanged strict legacy/TLB checker. No old checked_soc/checked_build/checked_image
or original-root-hash waiver is called. The old log/manifest are retained as
lint-provenance bytes, not asserted to describe the promoted image.

The inherited direct Execution owner supplies bounded subprocess-group cleanup.
Maximum compile walltime is7200s; signals/timeouts/nonzero exits cannot produce
PASS. Success is `CANONICAL_SOC_BUILT_NOT_EXECUTED`, with actual generated config,
full executable image inventory, source-manifest, artifacts and pre/post pins.
It is not a functional/runtime/promotion acceptance receipt. Later runtime gates
need a new canonical receipt consumer and the separate historical-input archive
for frozen-ELF baseline provenance, not old checked_soc.

## Commands For Later Review

Host tests (no EDA):

```sh
python3 -B -m unittest discover -s verification/akv/canonical_promotion/canonical_soc -p 'test_*.py' -v
```

Only AFTER actual promotion, a fresh preflight (no compiler invocation):

```sh
python3 -B verification/akv/canonical_promotion/canonical_soc/build.py \
  --output verification/out/canonical-soc-preflight-REVIEWED
```

After explicit authorization, a direct-owned service could execute:

```sh
systemd-run --user --unit=canonical-soc-build-REVIEWED \
  --property=Type=exec --property=KillMode=control-group \
  --property=RuntimeMaxSec=7800 --property=TimeoutStopSec=30 \
  --property=WorkingDirectory=/home/wangwy/openproject/ara_dsa_signoff_integration \
  /usr/bin/python3 -B verification/akv/canonical_promotion/canonical_soc/build.py \
  --execute --timeout 7200 --output verification/out/canonical-soc-build-REVIEWED
```

These commands have NOT been launched. No permission to promote or compile is
implied by this preparation. The host negative test deliberately checks the
currently unpromoted real tree; after promotion that one preparation-era test
must be treated as historical, not weakened to allow a before-state build.
