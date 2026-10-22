# DVE coverage waivers

## Trusted execution leaves (2026-10-08 review)

The user authorizes whole-module integration-scope waivers for independent,
reliable execution IP, including locally modified arithmetic modules when
their functional boundary and validation evidence justify this choice.
Unchanged source is useful evidence, not an absolute eligibility condition.
Apply this policy to other independent execution/helper IP with comparable
boundaries and existing functional evidence, not only the initial names below.
Local edits do not by themselves disqualify a module. Record each actual
compiled instance, evidence and exclusion reason in the approved manifest;
do not silently expand an exclusion to a parent containing scheduling or
architectural state. This is a coverage-scope decision, not a claim that a
module is bug-free. A known unresolved failure in a candidate's function
places that candidate on hold until the failure is localized or resolved.
This is a separate `TRUSTED_IP_INTEGRATION` policy,
not a proof that the excluded logic is unreachable or exhaustively verified.
Retain the full-design raw report and the existing qualified797 policy
(Toggle73.18%, FSM81.09%). Publish any successor with its exact excluded
instances and reasons; do not overwrite or compare the two denominators as
new stimulus gains.

Initial candidates, pending compiled-instance and native roundtrip review:

- `fpnew_classifier`: independent combinational floating-point classification.
- `fpnew_rounding` with `EnableRSR=0`: independent deterministic rounding;
  no stochastic-rounding/LFSR implementation is approved by this condition.
- `common_cells/lzc`: independent combinational zero counting, subject to
  pinned source/configuration and matching existing verification evidence.
- `simd_alu` and `simd_mul`: independent lane arithmetic, subject to explicit
  operation/result/flag regression evidence and review of unresolved failures.
- `serdiv`: the arithmetic division core only, not its lane issue/completion
  wrapper or request scheduling.
- `fpnew_fma`: independently reusable floating-point arithmetic/pipeline IP;
  its flush, ready/valid, tags and flags require an explicit validation owner
  and relevant existing regression evidence before whole-scope approval.

Parent review confirmed these source files have no local diff in their
dependency repositories. The local `fpnew_pkg` changes concern FP16/INT8
conversion-lane selection, not classification or rounding definitions;
the candidate packet must still bind the actual compiled source/configuration.
No candidate is applied merely by being listed here. Each approved scope
must retain its source identity, parameters, compiled checksums, functional
evidence and explicit validation owner. DVE must accept and preserve the
precise scope exclusions across save/reload, reset to the original metrics,
and leave every unselected scope unchanged.

Do not extend leaf approval to `vmfpu`, `valu`, their issue/completion logic,
operand/result queues, exception/flag integration, or QBS/AKV controllers.
`fpnew_cast_multi`, `fpnew_divsqrt_multi`, `fpnew_opgroup_multifmt_slice` and
C910 rounding currently remain in scope: modified conversion/integration
and previously problematic paths need separate review, not automatic trust.
The integration wrappers and parent-side request/result/flag interfaces
remain covered even when a child execution IP is excluded. Whole-module
approval never disables its functional tests, scoreboards or assertions.
Known failures and unresolved checks remain visible regardless of coverage
scope. Existing functional comparisons and assertions are not disabled.

## Current-image review (2026-09-29)

The FP16-repaired image has a separate, design/shape-bound policy in
`reviewed_20260929/`. The frozen campaign exporter is not changed while its
two combined AKV tests are still running. The new runner snapshots the
exporter and applies native DVE exclusions in an independent output directory:

```bash
DVE_COVERAGE_TIMEOUT=1800 python3 verification/coverage/run_reviewed_dve_20260929.py \
  /absolute/path/to/new-report --inputs-file /absolute/path/to/validated-vdbs.txt
```

This policy reapproves the 88 exact operand-flush points, excludes ten
observational instances (including `cva6_rvfi_probes`), and adds six scalar
input-toggle objects: `ipi_i`, `time_irq_i`, and `debug_req_i` in CVA6 and its
CSR module. These inputs are tied to zero in this compiled SoC. No interrupt
branch, debug state, CSR operation or functional module is excluded. Native
checksum checks and exact saved-exclusion checks remain required. Only an
`APPLIED` report is a completed result; `PREPARED` is not acceptance.

Linux and llama.cpp are the primary workload targets, not a justification to
exclude any untested instruction. Configuration-disabled functions and
provably constant inputs can be waived for this configuration. An implemented
but unsupported feature must instead be identified as outside the validation
scope; it must not silently disappear from raw coverage. MMU/page faults,
privilege transitions, exceptions, software interrupts, memory ordering,
RVV execution and QBS/AKV error/resource paths remain in scope. The reachable
`FENCE.T` controller FSM cannot be waived merely because Linux or a benchmark
does not currently exercise it. PMP arrays, vector constant-input objects and
scan/testmode descendants remain deferred pending exact native-object review.

The independent 598-PASS export is under
`verification/out/dve-waiver-reviewed-598-20260929-01/`; raw input databases
and the archived unwaived report are unchanged. This review changes coverage
scope, not RTL functionality or test PASS status.

## Purpose and boundaries

The DVE exporters retain the unmodified `summary.csv` and additionally produce
`summary_waived.csv`, `exclusions.el`, and `waiver_status.json`. Exclusions are
applied by DVE, not by arithmetic adjustment of percentages. Input VDBs and
historical reports are not overwritten. No RTL is modified or recompiled.

The policy is automatically enabled for two reviewed coverage designs:
`vcs-dve-coverage-20260927-01` and `repair-closure-coverage-20260927-01`.
Their exact `verilog.design.xml` SHA-256 values are pinned in
`prepare_dve_waivers.py`. The fingerprint binds compiled source checksums and
instance hierarchy, including the reviewed configuration. A new design does
not automatically inherit waivers: its status is
`NOT_APPLICABLE_UNREVIEWED_DESIGN`, and only the raw report is generated.
Do not simply add a new fingerprint without reviewing the matching RTL,
configuration and point identities. DVE checksum checks remain enabled.

## Approved observer exclusions

Only instances of these observational verification modules are excluded:

- `llm_perf_monitor` and `vrf_perf_monitor`: performance observation.
- `ara_commit_monitor`: verification trace monitor.
- `ara_acc_contract_monitor`: verification protocol monitor.
- `ara_fault_vstart_probe`: bound verification probe.
- `uvm_custom_install_verdi_recording`: UVM recording infrastructure.

These are product code-coverage scope exclusions, not removal of their checks
or claims about assertion coverage. Memory models, AXI delay drivers, CVA6,
QBS, AKV and queue instances are not excluded wholesale. The remaining top
hierarchy still includes testbench/model logic; use the intended DUT hierarchy
for product reporting and do not call the top score pure RTL signoff coverage.

## Approved constant-input points

The approved functional-point exclusions are in `waivers/operand_flush.el`:
four lanes, each with ALU A/B, MFPU A/B/C and MaskB queues, whose `flush_i`
inputs are tied to zero. This excludes 48 line blocks, 24 scalar input toggle
objects and 16 true branch vectors (the branch database retains these points
only for the eight ALU queue instances). No false branch, whole condition,
whole queue, FIFO child or dynamic LSU flush path is excluded. Each point has
its native checksum/signature and a source annotation. Both approved designs
have the same relevant point mappings. Complete metric-shape fingerprints
are also checked before application. Missing or additional native exclusions
in DVE's saved file fail finalization.

## Deferred candidates

PMP-disabled paths, tied-low interrupt/debug paths, optional arithmetic modes,
and illegal FSM encodings need exact covered-object review before point-level
exclusions. A configuration limitation does not waive the same function in a
Linux/FPGA system with different connections. In particular, software-visible
illegal instruction/descriptor handling, AXI errors, queue backpressure,
supported MMU behavior and load/store exception flush must remain covered.
Low coverage, difficult stimuli or a benchmark not using a feature are not
waiver justifications. `NA` is not a missed coverage point.

## Automatic use

Use the existing `run_dve_coverage.sh` or
`dve_hierarchy/run_dve_coverage.sh` with a fresh output directory as before.
The default is `DVE_WAIVERS=auto`. Set `DVE_WAIVERS=off` to export raw coverage
only. `APPLIED` is written only after successful DVE export and output checks;
`PREPARED` is not a completed result. Never publish `.partial` reports.

For manual DVE loading after opening the corresponding design/tests:

```tcl
gui_exclusion_file -load -file {/absolute/report/path/exclusions.el}
```

Use DVE's Recalculate action after loading. Do not use `-bypass_checks` or
force migration to another design. The generated `.el` includes instance
checksums and annotations and can be archived with the report.

## Native validation

The current 21-PASS design completed unattended native export in
`verification/out/dve-waiver-current-20260927-04/`. Its status is `APPLIED`;
the saved file contains exactly the 88 approved points and nine observer
instances. Its raw CSV is byte-identical to the prior unwaived report.

The historic 427-PASS design independently completed in
`verification/out/dve-waiver-427-20260927-02/`, with `APPLIED`, exactly 88
points and eight observer instances. Its raw top percentages match the
previous report. These two designs were not merged. Excluding highly covered
verification observers can lower a percentage; exclusions do not imply new
functional coverage. The five top percentages (line/condition/branch/FSM/toggle)
are:

| Design | Raw (%) | Waived (%) |
| --- | --- | --- |
| Historic 427 PASS | 75.63 / 77.82 / 75.61 / 45.42 / 58.86 | 75.54 / 77.82 / 75.61 / 45.42 / 59.41 |
| Current 21 PASS | 55.81 / 60.51 / 56.86 / 32.68 / 46.71 | 55.65 / 60.50 / 56.84 / 32.68 / 47.18 |

Load the point file before adding observer scope exclusions: DVE replaces
in-memory scope exclusions when loading a file. The exporter then recalculates,
saves the combined native file and verifies its exact contents. No dialog
automation or checksum bypass is used. For large full-hierarchy exports, set
`DVE_COVERAGE_TIMEOUT=600`; a timed-out export is not a valid result.
