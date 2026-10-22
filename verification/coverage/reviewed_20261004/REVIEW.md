# Current-image waiver migration review, 2026-10-04

## Decision

**REVIEWED_OFFLINE_NOT_APPLIED.** The previously reviewed **88 operand-flush
points, 6 scalar constant toggle objects, and 10 observer instances** are
reusable for the exact current compiled image below. Rejected existing objects:
**0 points, 0 observer instances**. Applied to the current report: **0**.

This is a source/identity/state migration review, not a new coverage export or
an increase in exercised functionality. Native current-image DVE acceptance
remains **NOT RUN**, not PASS. The existing report's
`NOT_APPLICABLE_UNREVIEWED_DESIGN` status is unchanged. The old frozen exporter
does not acquire approval from this directory.

The exact, expanded object list is in [audit.json](audit.json), with a separate
old/current mapping, source identity, native signature and 625-test state for
each point. [policy.json](policy.json) is a declarative, audit-hash-bound exact
allowlist for a later independent exporter. It is not installed, not a DVE
exclusion file, and does not execute or load any tool.

## Evidence Boundary

- Raw report: `verification/out/gap35-control-current-20261004-01/combined-dve/summary.csv`.
- Authoritative image plan: `verification/out/repaired-aligned-600-20260930-01/plan.json`.
- Current image: `verification/out/repaired-aligned-build-20260930-01/sim/simv.vdb`.
- Current design SHA256: `6ba9f4af477f14793ca1967e7d9aa3fc8274864d897dee88de267597cd3be3be`.
- Old accepted design SHA256: `59c11cb1ae975762be2d8b8df2b9e5c2bf713e5873a3ca71c0f4259d633a490e`.
- Old acceptance: `verification/out/dve-waiver-reviewed-598-20260929-01/waiver_status.json`, status `APPLIED`, with its hashed native `exclusions.el` and original `points.el`.
- Scope authority: `verification/coverage/reviewed_20260929/`, its referenced `waivers/operand_flush.el`, and the old accepted exact saved exclusions. No new candidates were added.

The 626-line input list contains one design and 625 unique test VDBs. Its test
set exactly matches the existing 625-entry PASS-only ledger, including
`vdb_valid=true` and no VDB rejection. This review does not rerun architectural
checkers or reinterpret their PASS results.

All 66 original image files, 66 wrapper-image files and 23 design files match
the supplied plan. All 458 files in the actual compile source manifest match
their captured SHA256. The resolved source paths are recorded, not inferred
from the shell working directory or the plan's broader source inventory.
In particular, an `ara_dsa/...` entry elsewhere in that inventory is not a
substitute for the `ara_dsa_signoff_integration/...` compiled source path.

Between old and current compile manifests, seven shared RTL files changed:
`control_mvp.sv`, `defs_div_sqrt_mvp.sv`, `div_sqrt_top_mvp.sv`,
`norm_div_sqrt_mvp.sv`, `nrbd_nrsc_mvp.sv`, `valu.sv`, and `vmfpu.sv`.
The two build-local filelist/object paths also moved, retaining their respective
contents. None of the reviewed point definitions, constant connections,
observer definitions, or configuration proof sources changed. Global design
and metric-file hashes nevertheless differ; this is why adding a fingerprint
to the old policy would not have been an adequate review.

Compile command/filelist evidence confirms four lanes, VLEN=1024, QBS=1,
AKV=1, AKV v2=1, L2=2097152 bytes, `FOR_VERIFY`, AXI delay verification and
UVM CVXIF verification. The captured filelist contains `TARGET_VERILATOR` as
a source-selection define; no Verilator executable was run by this review.
The auxiliary `verilog.instance_parameters.txt` is hash-checked, but is not
misrepresented as a complete queue-parameter listing. Parameter evidence uses
the elaborated toggle shapes plus unchanged RTL declarations and connections.

## Reusable Operand Points

Let `S = ara_tb.dut.i_ara_soc.i_system`. For each **literal lane 0, 1, 2, 3**,
the scope is
`S.i_ara.gen_lanes[LANE].i_lane.i_operand_queues.i_operand_queue_QUEUE`.
These are an enumeration, not wildcard authorizations.

| QUEUE | Tie line in operand_queues_stage.sv | Exact native points per lane | Four-lane count |
| --- | ---: | --- | ---: |
| alu_a | 82 | Block 7; Block 172; Toggle flush_i; Branch 2 (0); Branch 7 (0) | 20 |
| alu_b | 112 | Block 7; Block 172; Toggle flush_i; Branch 2 (0); Branch 7 (0) | 20 |
| mfpu_a | 144 | Block 7; Block 172; Toggle flush_i | 12 |
| mfpu_b | 172 | Block 7; Block 172; Toggle flush_i | 12 |
| mfpu_c | 200 | Block 7; Block 172; Toggle flush_i | 12 |
| mask_b | 292 | Block 7; Block 172; Toggle flush_i | 12 |
| Total | | 48 blocks + 24 scalar toggle objects + 16 true branch vectors | 88 |

Each of these six queue connections is explicitly `.flush_i(1'b0)`. The
unreachable operations are `ibuf_usage_d = '0` at operand_queue.sv:127 and
`select_d = '0; elem_count_d = '0` at lines 543-544 under `if (flush_i)`.
The normal reset assignments and normal completion assignments are distinct
objects and remain covered/in scope.

The queue module definition checksum remains `1532764271`. The relevant full
metric definition XML, not only its checksum, is semantically identical
between the old accepted image and current image. Native identity details:

| Object | Metric checksum | XML identity | Native saved identity |
| --- | --- | --- | --- |
| Block 7 | 3998926456 | id=7, index=7, line=127, chksum=1270893570, `ibuf_usage_d = '0;` | `Block 7 "3393845244" "if (flush_i)"` |
| Block 172 | 3998926456 | id=172, index=176, lines=543/544, chksum=362722431, `select_d = '0;` | `Block 172 "3393845244" "if (flush_i)"` |
| Branch 2 (0) | 1417162425 | spec=2, vector id=0, vector=01, expr=flush_i, source line=127 | `Branch 2 "949433246" "flush_i" (0) "flush_i 1"` |
| Branch 7 (0) | 1417162425 | spec=7, vector id=0, vector=01, expr=flush_i, source line=542 | `Branch 7 "949433246" "flush_i" (0) "flush_i 1"` |
| Toggle flush_i | 2109767059 for ALU/MFPU; 885747700 for mask_b | scalar input, file_id=551, line=35, excluded=0 | `Toggle flush_i "logic flush_i"` |

**Do not conflate nativepointchecksum with linebb.chksum.** The original input
file used the assignment signatures. Old DVE accepted it and saved the native
Block signatures shown above. This review preserves both layers through the
hashed old input/saved files and unchanged complete metric definitions. The
new policy uses the accepted saved signatures. For Toggle objects the saved
syntax has no separate integer point checksum: `nativepointchecksum=null` is
intentional, with definition/metric checksums and scalar signature retained.

Parameter cross-check: all reviewed queues have NrLanes=4, VLEN=1024 and
NrSlaves=1. ALU A/B have CmdBufDepth=4, DataBufDepth=5, FPUSupport=0,
AccessCmdPop=0, integer extensions 2/4/8 enabled and reduction enabled;
SupportNtrVal is respectively 0/1. MFPU A/B/C have depths 4/5, FPUSupport=56,
AccessCmdPop=0, IntExt2 enabled, IntExt4/8 disabled, reduction enabled and
SupportNtrVal respectively 0/1/1. MaskB has depths 3/3, FPUSupport=0,
AccessCmdPop=1, IntExt2/4/8 enabled, reduction and neutral-value fill disabled.
Shape names sometimes coalesce parameter variants; the unchanged instance
declarations in operand_queues_stage.sv disambiguate A/B/C, rather than
inventing a value from an omitted shape-name field.

## Branch and Raw State

No frozen `vcs_point_audit.py` decoder is imported or used. Its forward-order
`missing` labels are not an exclusion authority. Raw branch positions are
mapped by **reversing branch_vector order within each branch_spec**, not by
reversing the whole instance. Native vector ID 0 remains native vector ID 0.

For every one of the eight ALU queue instances in the exact 625-test union:

- spec 2: B=4, N=2, raw[4:6]=`10`; native true vector 0 is raw index 5=`0`, false is index 4=`1`.
- spec 7: B=97, N=2, raw[97:99]=`10`; native true vector 0 is raw index 98=`0`, false is index 97=`1`.
- Corresponding independent linebb indices 7 and 176 are both `0`.

Thus forward order would falsely report all 16 reviewed true vectors hit,
contradicting both the true-body line state and tied-zero source. Reverse
within each spec gives zero such contradictions in this reviewed set. This
is independent confirmation for these points, not a claim to have repeated
Carver's wider 57-branch SLDU experiment.

All 48 reviewed blocks are unhit, and all 24 flush scalar toggle objects have
raw transition flags `00`. No status is taken from the 620-test
`gap35-rvv-20261004-01/baseline_checked.json`. The audit directly reread 1,875
line/branch/toggle testdata files from this report's 625 inputs, checked every
file against the PASS ledger hash, checked all selected instance checksums
and widths, and accumulated the raw flags. Selected objects required no
checksum inheritance. These flags are diagnostics, not DVE scoring units or
new percentages.

## Reusable Scalar Toggles

Only these six scalar objects are approved. Both scopes are literal paths.

| Scope | Signal | Definition / toggle metric checksum | Raw flag indices | State |
| --- | --- | --- | --- | --- |
| S.i_ariane | ipi_i | 376119937 / 1939539040 | 264,265 | 00 |
| S.i_ariane | time_irq_i | 376119937 / 1939539040 | 266,267 | 00 |
| S.i_ariane | debug_req_i | 376119937 / 1939539040 | 268,269 | 00 |
| S.i_ariane.csr_regfile_i | ipi_i | 1371260681 / 1176918775 | 3750,3751 | 00 |
| S.i_ariane.csr_regfile_i | time_irq_i | 1371260681 / 1176918775 | 4,5 | 00 |
| S.i_ariane.csr_regfile_i | debug_req_i | 1371260681 / 1176918775 | 3752,3753 | 00 |

ara_system.sv:183-185 explicitly ties these three inputs to zero. The same
inputs are forwarded to csr_regfile_i by cva6.sv:1193,1250,1251. Native saved
signatures are `Toggle SIGNAL "logic SIGNAL"`; old source-file input syntax
used `net SIGNAL`. Source file IDs 419/428, scalar input type, exact shapes,
parameters and source hashes match. No interrupt/debug/CSR branch, CSR bit,
software interrupt operation, or functional debug behavior is excluded.

## Reusable Observer Scopes

These are the same ten saved native instance exclusions, with the same module
definition checksums, resolved source paths and line/branch/toggle definition
shapes/parameters. Every scope has **zero elaborated descendants**, so its
previous recursive setting cannot swallow a queue, memory model or AXI driver.

| Literal scope (S as defined above) | Native definition checksum | Scope reason |
| --- | --- | --- |
| S.i_ara.i_dispatcher.i_ara_fault_vstart_probe | 1623180263 | Input-only bound trace |
| S.i_ara_acc_contract_monitor | 3628195876 | Input-only protocol checker |
| S.i_ara_commit_monitor | 182875116 | Input-only trace/scoreboard/watchdog |
| S.i_ariane.i_cva6_rvfi_probes | 1089031276 | Verification RVFI packaging |
| ara_tb.i_llm_perf_monitor | 4011875712 | Input-only performance counters |
| ara_tb.vrf_perf_monitor[0].u_vrf_perf_monitor | 3494332113 | Input-only bank counters |
| ara_tb.vrf_perf_monitor[1].u_vrf_perf_monitor | 3494332113 | Input-only bank counters |
| ara_tb.vrf_perf_monitor[2].u_vrf_perf_monitor | 3494332113 | Input-only bank counters |
| ara_tb.vrf_perf_monitor[3].u_vrf_perf_monitor | 3494332113 | Input-only bank counters |
| uvm_custom_install_verdi_recording | 2787408814 | Vendor recording infrastructure |

The RVFI probe is not falsely described as output-free: its output goes through
cva6.sv:1957 to ara_system.sv:195 and the verification i_cva6_rvfi at lines
215-230, whose trace output feeds i_ara_commit_monitor. It does not drive the
execution datapath. `i_cva6_rvfi` itself is **not** newly excluded.
Monitors' assertions, errors, watchdogs and finish/fatal behavior are preserved;
scope exclusion is not deletion of these checks or a waiver of checker failures.

The vendor UVM source is outside the 458-file project compile SHA manifest.
This limitation is explicit in audit.json. Its old/current sourceinfo records
match, its current on-disk mtime matches the recorded timestamp 1709614667,
its native definition and complete metric shapes match, and it has no product
descendants. These establish the existing image's observer scope identity.
The recorded current source SHA256 is **not** called a compile-time source pin
or used to approve a future rebuild.

The branch checksum `1223333544` is shared by several unrelated definitions.
The new reader requires module/definition identity as well as checksum. It
does not resolve observer points by choosing the first checksum match.

## Unavailable or Refused

| Item | Decision |
| --- | --- |
| Existing 94 points and 10 observers on this exact image | Offline migration usable; enumerated above and expanded in audit.json |
| Current native APPLIED result / adjusted summary | Unavailable: DVE load, review status, recalculate and save were not run |
| Old frozen policy enabled merely by adding this fingerprint | Refused |
| Branch exclusions based on frozen forward-order missing labels | Refused |
| Whole queue/module, descendant FIFO, false vector or condition exclusions | Refused |
| Reachable Linux/MMU/privilege/trap/CSR/FENCE.T/RVV/QBS/AKV functionality | Retained; no new exclusion |
| Dynamic LSU exception flush and its dependent state | Retained |
| operand_requester inline FOR_VERIFY candidates | Outside this review; no policy entry or automatic waiver |
| A future image, source change, parameter change or broader observer match | Not approved by this review |

Later native acceptance must use a fresh independent output directory, retain
the raw report, enable native checksum checks, require zero checksum mismatch,
zero need-review and zero unmappable objects, and compare the exact saved
exclusion set. Never use bypass/forced migration. This review neither starts
that export nor changes running campaign pins, input databases or outputs.
The user's newly running ten-test campaign is not part of this frozen
625-test evidence set.

## Raw Coverage Preserved

The original top `ara_tb` row is unchanged:

| Score | Line | Condition | Branch | FSM | Toggle |
| --- | --- | --- | --- | --- | --- |
| 68.66% | 76.90% | 78.96% | 77.24% | 50.54% | 59.63% |

No waived percentages are calculated or claimed. This top hierarchy still
contains verification/model logic; it is not relabeled as pure DUT signoff
coverage. The conclusion is identity/scope reuse, not a percentage target.

## Reproduction and Tests

Only the new directory contains writes. No frozen script, RTL, old report or
running pin file was edited. No URG, Verilator, VCS or DVE process was started.
The reviewer used Python standard-library XML/JSON/CSV/hash readers only.

Read-only re-audit (prints counts, writes nothing):

```sh
python3 -B verification/coverage/reviewed_20261004/audit_readonly.py
```

Artifact integrity and negative mapping/policy tests:

```sh
python3 -B -m unittest discover -s verification/coverage/reviewed_20261004 -p test_review.py -v
```

Result: **15 tests passed**. Tests cover per-spec reverse order (not whole
instance reversal), native-vs-XML signatures, Block 172/index 176, exact
94-point cardinality, checksum/definition disambiguation, scalar input
identity, rejected missing/duplicate/extra/altered directives and scopes,
rejected APPLIED/percentage mutations, audit-policy SHA binding, observer
descendant boundaries, original raw percentages, and rehashing all captured
image/design/source/testdata evidence. `--write` is only for initial creation
and refuses to overwrite existing audit.json or policy.json.
