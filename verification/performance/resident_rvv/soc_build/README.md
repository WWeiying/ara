# Resident PV SoC Build Only

This successor harness is deliberately inert until the parent declares production
edits ready. Only this directory is owned here. No prepare/snapshot, EDA launch,
simulation, synthesis, stage, or commit is authorized by creating these scripts.
The script has no simulator execution path. Synthetic host tests are independent
of the live overlay and can run while the parent edits production RTL.

## Frozen Base

All non-overlay inputs come from
`chain_soc_20261107_01/source`, its frozen `sources.f`/plan/compile command,
and `chain_soc_admitted_20261107_01/build.json`/source pins. Their reviewed
SHA-256 anchors are explicit in `build.py`.

The original worker failed in its Python report writer. The admitted receipt
separately audited the compiled image; it did not relabel the original worker
PASS and did not execute firmware. This successor preserves that distinction.
The admitted source and image identities are checked before any copying.

No Git archive of the whole project, copytree of the repository, Bender command,
dependency fetch, or live dependency reconstruction is used. Explicit compiler
sources, include inventories, adjacent literal headers, baseline build metadata,
the frozen TB, frozen DPI loader object, four UVM sources, and boundary monitor
are copied individually from admitted bytes. Thus forked CVA6/fpnew/common-cell
and fpu_div_sqrt dependency deltas remain exactly those of the frozen base.
No patch is reapplied to the already patched frozen dependency files.

The inherited TARGET_VERILATOR target define is preserved with the baseline
filelist; no Verilator executable is invoked. `uvm_macros.svh` is an explicitly
recorded vendor-tool include from the unchanged `-ntb_opts uvm-1.2` setup. VCS
wrapper and compiler-backend binaries are pinned. User RTL/includes cannot fall
back to live dependencies or resolve outside the private source closure.
The three missing OpenPiton-generated includes in frozen ariane_pkg/wt_cache_pkg
are recorded separately as inactive only when their exact PITON_ARIANE guards
remain present. PITON_ARIANE itself is forbidden; no general missing-header
exception or generated replacement header is accepted.

## Explicit Live Overlay

Exactly thirteen existing RTL files are replaced:

```text
hardware/include/ara_pkg.sv
hardware/include/akv_pkg.sv
hardware/src/ara_dispatcher.sv
hardware/src/cva6_accel_first_pass_decoder.sv
hardware/src/ara_sequencer.sv
hardware/src/lane/lane_sequencer.sv
hardware/src/lane/operand_requester.sv
hardware/src/lane/vector_fus_stage.sv
hardware/src/lane/lane.sv
hardware/src/lane/vmfpu.sv
hardware/src/ara.sv
hardware/src/vlsu/vlsu.sv
hardware/src/vlsu/akv/akv_engine.sv
```

Exactly six new modules are inserted before the existing engine entry:

```text
hardware/src/lane/akv_resident_pv_lane.sv
hardware/src/vlsu/akv/akv_resident_pv_group.sv
hardware/src/vlsu/akv/resident_payload_fanout.sv
hardware/src/vlsu/akv/akv_resident_pv_reader.sv
hardware/src/vlsu/akv/akv_resident_pv_import.sv
hardware/src/vlsu/akv/akv_resident_pv_control.sv
```

Live `Bender.yml` is copied separately to `inputs/audit/Bender.yml` and checked
for those new entries, but is not used to generate the filelist. The source
closure's Bender/lock/Makefile/config metadata stays frozen baseline provenance.
No live `hardware/tb`, `hardware/deps`, software/SDK assembly, or application is
admitted. In particular, dirty `hardware/tb/ara_tb.sv` and fpuDiv never enter the
overlay. Repeated baseline source entries and source order are preserved.

Configuration remains four lanes, VLEN1024, shared integer multiplier enabled,
shared FMA disabled, 16 MiB simulated L2, pure CVA6 (`ideal_dispatcher=0`), with
the same ara_tb/UVM/passive-monitor and assertion setup. The only added define
is `ARA_AKV_RESIDENT_PV_ENABLE=1`. Resident PV capability remains zero, including
when admission is compiled in, for experimental wrapper direct calls only.

## Parent-Controlled Stages

Host tests only, safe now:

```sh
python3 -B verification/performance/resident_rvv/soc_build/test_build.py
```

Only after the parent finishes editing and explicitly requests preparation:

```sh
python3 -B verification/performance/resident_rvv/soc_build/build.py prepare \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/UNIQUE_SOC_BUILD \
  --parent-ready
```

This produces PREPARED_NOT_BUILT, immutable source/helper copies, complete
`source-pins.json`, `closure.json`, `overlay.json`, `sources.f`, `command.json`,
and experimental `selection.json`. It does not invoke VCS, including version
queries. Parents review the explicit overlay identities and source-pins hash.
All pinned originals, including these three harness files, must then stay frozen.
A failed/partial preparation directory is never overwritten or reused.

After separate parent build approval, print (do not execute implicitly) the
direct-owner transient service command:

```sh
python3 -B verification/performance/resident_rvv/soc_build/build.py service-command \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/UNIQUE_SOC_BUILD
```

The parent runs that reviewed command. It invokes only the frozen
`OUT/inputs/build.py build --parent-reviewed --review-sha256 HASH` and checks
that the Python worker itself is systemd MainPID in the expected service cgroup.
Do not wrap it in a short-lived launcher. Service stdout/stderr are separate
files; the service owns VCS and children until completion, with a 7200-second
compiler timeout and 7500-second service bound. Inspect `systemctl --user status`
and the actual vcs1 process: wrapper launch/license preparation is not evidence
that an executing compiler has reached RTL elaboration.

Compilation writes closed compile/test logs and full simv/daidir image pins,
then rechecks source hashes and complete include/closure inventories. Timeout,
signal, failure, or drift preserves the failed directory; no automatic retry or
fallback to other inputs occurs. Live stdout/stderr/status are excluded from
artifact hashes. No simv invocation, firmware load, URG, or synthesis occurs.

## Software Image Contract

The new build receipt uses `RESIDENT_PV_SOC_BUILT_NOT_EXECUTED`, never a baseline
PASS identity. It exports standard `sim/simulator.conf` fields, schema-1
`sim/vcs_source_manifest.json` compatible with the existing read-only collector,
`image-pins.json`, source inventory hash, and this software contract:

```text
NrLane=4 VLEN=1024 AXI=128 L2sim_bytes=16777216
shared_integer_multiply=true EnableSharedFma=0
```

Extra manifest fields distinguish resident-PV admission enabled from capability
advertisement disabled. Existing exact-baseline `chain_profile.run_case.checked_soc`
must reject this new identity; a future parent-owned software runner must verify
this receipt/schema explicitly. Do not weaken that old checker to reuse its
baseline acceptance. The standard ELF/L2/capability image-contract shell check
can consume simulator.conf for memory and existing AKV-v2 geometry checks.
Build-only success is not numerical, protocol, performance, SoC or FPGA acceptance.

## Read-Only Checker Follow-Up

No checker is modified by this harness. Before execution evidence is classified:

- `verification/ara_verify/uvm_coverage.py:custom_instruction_activity` currently
  maps every custom-2 funct3=7 to `akv_v2_column`; it must distinguish funct7=2
  resident PV from funct7=0/1 column/panel, and not treat unknown funct7 as PV.
- `uvm_coverage.py:bins_for` and its completion-name set need independent PV
  allocation/completion bins so a PV run cannot inflate old column coverage.
- `verification/ara_verify/trace.py:is_vector_instruction` already accepts
  opcode 0x5b, so generic CVX request/retire matching needs no opcode widening.
- `verification/ara_verify/vector_commit.py:_uses_mask_predicate`,
  `_architectural_compare_mask`, and `_architectural_byte_effect_masks` apply
  ordinary RVV vm/VL/tail rules. Full architectural PV comparison needs a
  separate reviewed policy for unmasked internal VL256, four clobberable result
  registers, fixed 128-halfword head stride, and active D/H output only. It must
  still check failure leaves the entire destination unchanged and must not hide
  group-outside writes. Generic instruction bits must not supply PV's vm policy.

These are future checker design obligations, not authority to change or relax
any accepted checker, and not additional component-gate dispatch requests.
