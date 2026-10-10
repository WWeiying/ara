# Inline Operand Requester Observer Review

Date: 2026-10-04. Status: **SOURCE REVIEW ONLY; NOT APPLIED**.

Machine-readable evidence: [inline_requester_evidence.json](inline_requester_evidence.json).
This is a separate review of the 776 candidate native `linebb` objects in
`verification/out/gap35-analysis-20261004-01/inline-requester-candidates.json`.
It does not extend the existing 88 operand-flush, 6 scalar-toggle or observer
policy. No existing policy, audit, RTL, report, script or running pins changed.
No VCS, DVE, URG or Verilator was started.

## Decision

There are two independent decision axes. Source eligibility is not a native
exclusion directive, saved DVE point identity, or evidence of application.

| Decision within the 776 candidates | Per lane | Four explicit lanes |
|---|---:|---:|
| Waivable from product RTL coverage scope, with observer/checker retained | 776 | 3,104 |
| Not waivable due to identified functional feedback or mixed functional statements | 0 | 0 |
| Source identity/process/fanout unproven within reviewed source closure | 0 | 0 |
| Native DVE exclusion identity/application unproven | 776 | 3,104 |
| Applied exclusions | 0 | 0 |

"Read-only" means no feedback into product execution, not absence of local
debug state or simulation side effects. One block packages writeback traces
consumed by a checker that can call `$fatal`. That block is verification
instrumentation, but its wiring, trace output and checker behavior must remain
enabled and unchanged. None of the 776 is approved for removal from execution.

This decision rests on complete block statement membership, inspected assignment
targets and consumer paths, not on the `FOR_VERIFY` name, plusargs being disabled,
or a missed coverage bit. No whole-module, whole-guard, line-range, branch,
condition, toggle or FSM exclusion is authorized by this review.

## Fixed Inputs

- Plan: `verification/out/repaired-aligned-600-20260930-01/plan.json`.
- Build: `verification/out/repaired-aligned-build-20260930-01`.
- Source: `hardware/src/lane/operand_requester.sv`, SHA256
  `327291850e6d77797ab9e67c8d24dd7e8bca9019139d85518b0075fd80f5bca2`.
- Native source file ID `552`; definition ID `-46`; definition checksum
  `2909207138`; line shape checksum `900008355`.
- Native line shape SHA256:
  `70d031cd99b85e25904d30aab3cc71d4876b5d311d94deee8df07d9b331a9e15`.
- Baseline: the fixed 625 inputs of
  `verification/out/gap35-control-current-20261004-01/combined-bits.json` and
  `combined-dve/summary.csv`. New finishing/running batches are not included.

The literal instance scopes are:

```text
ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[0].i_lane.i_operand_requester
ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[1].i_lane.i_operand_requester
ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[2].i_lane.i_operand_requester
ara_tb.dut.i_ara_soc.i_system.i_ara.gen_lanes[3].i_lane.i_operand_requester
```

All 458 compile-manifest source hashes were checked with no drift. The candidate
input hashes, sourceinfo, design hierarchy, native shape, block attributes and
statement lists were rechecked. The four requester line vectors were independently
OR-merged from all 625 pinned line-testdata files and matched the cached union.

The 1,250 native linebb objects have explicit XML `index` values within 1,271 raw
positions. Block `id` is not the raw index. This review uses explicit linebb
indices, not branch-vector order or the frozen helper's missing-point labels.
XML `chksum`/`bbsig` are retained as source/block evidence; they are not fabricated
as saved DVE `nativepointchecksum` values. All new saved pointchecksums are null.

## Complete Candidate Inventory

Ranges identify the manually reviewed processes, not exclusion ranges. Every
candidate's own file ID, statement lines, generate information, checksum, raw
index and proof group are individually recorded in the JSON `blocks` array.
Control/join linebb objects with empty signatures are included only when their
native process and all recorded statement lines are inside the reviewed process.

| Group / proof | Requester source lines | Blocks per lane | Hit per lane |
|---|---:|---:|---:|
| Writeback trace packaging / WB | 179-204 | 1 | 1 |
| LDU print / PRINT | 208-214 | 3 | 2 |
| Address debug counter / ADDR_COUNTER | 343-348 | 3 | 3 |
| Four debug selectors / DEBUG_LATCHES | 626-674 | 243 | 63 |
| VZEXT reshuffle print / PRINT | 676-686 | 27 | 18 |
| VFMV print / PRINT | 690-717 | 72 | 18 |
| MaskB print / PRINT | 719-747 | 72 | 18 |
| Fixed-point print / PRINT | 749-760 | 27 | 18 |
| Multi-reader WAR print / PRINT | 762-782 | 27 | 18 |
| Segment/mask print / PRINT | 784-805 | 72 | 18 |
| Address print / PRINT | 807-835 | 72 | 18 |
| Dependency/group print / PRINT | 837-885 | 144 | 36 |
| Writeback dependency print / PRINT | 1101-1112 | 8 | 2 |
| MFPU debug counter/print / MFPU_COUNTER | 1114-1137 | 5 | 4 |
| Total | | 776 | 237 |

The generated debug-selector and display processes account for 756 blocks:
nine explicit `requester_index` replicas (0 through 8), 84 blocks per replica.
The other 20 are non-replicated processes. All four lanes have the same candidate
membership and group hit counts. Hit and miss candidates receive the same
semantic review; hit status does not decide eligibility.

## Reference And Fanout Evidence

### WB: Writeback Trace Is An Active Checker Input

`operand_requester.sv:180-203` writes only `verify_wb_valid_o`, `verify_wb_id_o`,
`verify_wb_addr_o`, `verify_wb_wdata_o` and `verify_wb_be_o`. It observes actual
post-arbitration grants plus the matching writeback payload. It does not write
those grants, request signals or payload sources.

The complete inspected consumer chain is:

```text
operand_requester.sv:180-203  verify_wb_*_o
  -> lane/lane.sv:434-438    output-to-output named connections
  -> ara_system.sv:208-212  hierarchical lane output reads into verify_wb_* buses
  -> ara_system.sv:259-263  ara_commit_monitor.wb_*_i inputs
  -> tb/ara_commit_monitor.sv:215-240  $fdisplay or verification $fatal
```

`lane.sv:115-119` declares these ports as outputs. `ara.sv` instantiates `i_lane`
using named connections, without connecting these verification output ports to
product logic. `ara_system.sv:122-126` declares the monitor buses. The monitor's
ports at lines 31-35 are inputs; it has no output/inout ports or force/release
feedback. `wb_valid_i` at line 218 and `wb_id_i` at line 219 select trace metadata
or the untracked-write `$fatal` at line 235. Address, byte enables and data feed
the trace at lines 225-226 and 232-233. The temporary `id` is a local automatic
variable, not an architectural state write.

Therefore the trace packer is outside product execution coverage scope, but it
is **not side-effect-free**. Excluding code coverage must never suppress checker
execution, diagnostics, trace generation or verification failure. This review
does not waive any monitor assertion or functional writeback coverage obligation.

### Local Debug State: No Product Consumers

All references below are in `operand_requester.sv`, within the inspected
`FOR_VERIFY` regions. No external source references were found for these names.
Declaration lines are separate from reads/writes in this table.

| State | Declaration | Writes | Reads and terminal consumers |
|---|---:|---|---|
| `debug_addr_opreq_cycle_q` | 341 | 345, 347 | 347 self-increment; 764-765 WAR print window; 823 address print throttle |
| `debug_maskb_target_q` | 621 | 628, 651, 653 | 652 local clear guard; 733 display guard |
| `debug_group_hazard_q` | 622 | 629, 660, 662 | 661 local clear guard; 872 display guard |
| `debug_vfmvfs416_q` | 623 | 630, 669, 671 | 670 local clear guard; 706 display guard |
| `debug_vzext_reshuffle_q` | 624 | 631, 641, 644 | 642 local clear guard; 677 display guard |
| `debug_mfpu_cycle_q` | 1099 | 1116, 1118 | 1118 self-increment; 1120 display throttle; 1122 display argument |

The four selector flags read command fields, handshake signals and `state_d`
to select diagnostics. They never write command readiness, state, metadata,
stall, hazard, arbitration or queue outputs. Counter rollover can alter logging,
not the functional pipeline. These stateful probes are observational relative
to the design, despite having their own state updates.

### PRINT: Terminal Display Calls

The PRINT processes have no assignment targets. Their only system calls are
`$display`, `$test$plusargs` and `$time` (some processes use only a subset).
The reviewed candidate processes contain no `$value$plusargs` output argument,
force/release, ref/inout helper, DPI or user-task side effect. Signal reads such
as `stall`, requester state/metadata, hazards, readiness, requests and grants
are display arguments or guards, not writes back to those signals.

### Bank Annotations: Not Part Of The 776

The assignments at requester lines 1090-1094 write `bank_vld`, `bank_rd_vld`,
`bank_wr_vld`, `bank_rd_vid` and `bank_wr_vid` from grants and VRF address/write
signals. `bank_rd_vld`/`bank_wr_vld` feed only their respective VID annotations;
the remaining annotation signals have no consumers outside that local debug
chain. However, these assignments have **no linebb in this candidate set**.
They are not additional waiver points and do not change any reported count.

## Retained And Unproven Objects

- All 474 other mapped blocks per lane remain outside this authorization.
  They are listed as `OUTSIDE_CANDIDATES_RETAIN_NOT_AUTHORIZED`, not implicitly
  classified as observers by proximity to a debug process.
- The actual grant forwarding at lines 169-174, result tracking/flush at
  228-249, source lifetime logic at 326-335, requester FSM/hazard/stall/queue
  logic at 351-619, payload/request logic at 894-971 and VRF arbitration/output
  logic at 1016-1087 remain retained. Reachable Linux/RVV/QBS/AKV behavior is not
  excluded merely because debug processes observe it.
- The 21 raw positions without a linebb mapping per lane remain unproven and
  retained. Their exact indices are in each JSON instance entry. They are not
  attributed to `FOR_VERIFY`, assigned invented signatures or removed.
- All 776 candidate native exclusion mappings/application states per lane
  remain unproven. This review emits no exclusion directives and no application
  policy. Any later independent export must establish exact DVE point identity
  and acceptance without overwriting running or frozen artifacts.

Raw diagnostics below are **not DVE scoring units or percentages**:

| Lane | Raw hit / positions | Candidate hit / blocks | Other mapped hit / blocks | Unmapped hit / positions |
|---|---:|---:|---:|---:|
| 0 | 648 / 1271 | 237 / 776 | 390 / 474 | 21 / 21 |
| 1 | 675 / 1271 | 237 / 776 | 417 / 474 | 21 / 21 |
| 2 | 678 / 1271 | 237 / 776 | 420 / 474 | 21 / 21 |
| 3 | 678 / 1271 | 237 / 776 | 420 / 474 | 21 / 21 |

The raw DVE report and all of its percentages are unchanged; report SHA256 is
`2579b53bf7f8a614be87d38760915f58c4f15fb1c0ccec7b25b90d32f194069d`.
No adjusted percentage or improved coverage conclusion is calculated.

## Method, Limits And Validation

The reference inventory scanned 615 actual source files: the union of relevant
HDL/C/header files in the compile manifest and all nonempty native sourceinfo
paths. The empty synthetic sourceinfo entry ID `612` is recorded, not treated
as a missing file. Watched identifiers occur only in requester, lane and
ara_system source; monitor input aliases were then followed separately.
Exact-token occurrences include path, line and text in the evidence. Literal
string references to watched identifiers were also checked; none were found.

This is a manual source assignment/port/sink review supported by a lexical
reference inventory, not a formal elaborated netlist proof. It is limited to
the pinned image and captured source connectivity. It does not prove the
absence of arbitrary future VPI forces or dynamically constructed external
names. Current scan hashes for vendor/tool files outside the compile manifest
are not represented as compile-time SHA pins. Changed sources, connections,
parameters, instrumentation or native point identities require a new review.

Twelve read-only standard-library tests passed: candidate membership; complete
native attributes/process boundaries; counts/hits; input and protected-file
hashes; exhaustive disjoint raw partition; no application/percentage change;
assignment/sink closure; and rejection of five corruptions (wrong file ID,
mixed functional statement, block-ID/raw-index confusion, wrong proof group,
fabricated saved native checksum). They were executed in memory; no test runner
or script file was added. They check evidence consistency, not DVE acceptance.

The JSON preserves all 776 individual definitions and their four explicit
instance memberships, all 474 retained mapped blocks, unmapped indices, full
reference records, source hashes, 625 line-testdata hashes and prior review
file hashes. `waivers_applied` and `policy_changed` are false;
`adjusted_percentages` is null. Only this document and its new evidence JSON
were written for this bounded task.
