# Remaining38 Negative Stride: Parameter Readiness

Prepared exact source inventory, ten batch configuration headers and native
original-C oracle cross-checks. **Not Sv39 reference-ready or DUT-ready.**
No new Spike, SoC compile, VCS, image build, RTL edit or live-task query.
No existing sealed package was changed.

## Exact Coverage

Archive:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_negative_stride_handoff01`.
`prepared01/manifest.json` contains all40 exact case.json records, absolute
source directories, individual ELF/source pins, historical actual/expected
fault context and unique original helper byte locations. Exact two exclusions:

- `e16_m1_u1_s0_b3_m2_f0_g3`: accepted M6 load.
- `e16_m1_u1_s1_b3_m2_f0_g3`: accepted M6 store.

The40 singles are all e16/m1, NF1, VL8, CAP64. Their C differs ONLY in the
single selected-tuple filter. Normalized C SHA256:
`0cf993e21646ff1ab1bdff21f3e8d402503ba67a561e706359259edc2afcbe6b`.
All40 archived ELF executable segments contain the exact capacity3 and both
replay10-instruction byte strings already established in the accepted pilot
source proof. Targets remain masked `vlse16.v` 09c55c07 / `vsse16.v` 09c55c27.
This proves helper identity, not full Linux ELF identity for a new adapter.

Historical provenance is deliberately not promoted: the archive calls these
`single_current_oracle_trial`, original source equivalence confirmed, but
original per-trial failure equivalence unproven and parent rebuild identity
false. They are measured failed archived singles, not all96 parent cases.
The archive's `board_reproduction_confirmed:false` remains unchanged.

| Remaining subset | Count | Required fault behavior |
| --- | ---: | --- |
| b1/m2, both gaps, both u, load/store | 8 | first active fault at2, not1; no completed active prefix |
| b3/m2, both gaps/u/directions minus pilots | 6 | first active fault at5, not3; completed element2 only |
| b1/3/5 m3, both gaps/u/directions | 24 | all-off: no page fault, no retry, no poison |

With P=VA+4096, stride=-2*(1+gap), original target is
P-boundary*stride-2. Fault addresses: b1/g1=P-6, b1/g3=P-10,
b3/g1=P-10, b3/g3=P-18. The original all-off `expected_start=8`
is a sentinel, NOT an expected trap vstart. Return vstart remains0.
Do not attribute archived handler_errors or all-off unexpected faults to
independent numerical errors.

## Actual Host Evidence

`prepare.py` verifies all40 case/manifest/source/ELF identities, then extracts
the original address functions, initialization and final wanted-value loops
into a native C observation program. Only the Linux environment and comparison
sinks are replaced for this Host cross-check; no RVV executes on the Host.
An independently written Python model checks every emitted row for all40:
**177400 rows = 40 x4435**, each native child exits0. Covered: exact fault
geometry, input128/unused offsets128/mask16/output allocation130 initialization,
64 final output values, all4096 original/final memory halfwords. Original two
guard positions and extra allocation sentinels are retained in the parameters.
Native output hashes and actual numeric child receipts are in `host.json`;
full native stdout is not retained, and is not claimed as vector evidence.

Ten Host tests passed, including13 oracle-row mutation locations, truncation,
duplicate/reordered rows, invalid tuple/type rejection, start2 vs5, all-off,
gap changes, u0 no-refill vs u1 refill, and store poison36 versus load poison.
These are parameter/oracle tests, NOT execution tests of a future Sv39 handler,
page-table setup or CSV checker. `HOST_RECEIPT.json` records actual tool exits.

## Necessary Reuse Changes

The existing fixture/observer/checker are reliable for their pinned u1/b3/m2/g3
single, but NOT already generic. Their literal base4118, stride-8, vstart5,
fault4078, mask0x24, poison halfword2051, two trap records, unconditional
2048-halfword refill and action/count constants must not survive as defaults.
For example old `csv_check.py:7,115,149,176,179` fixes checkpoint counts, arguments,
retry and total17274; old store observer fixes17275 and one prefix read.

Implement one shared successor fixture/checker with a per-member case context:

1. Keep exact original64 input values, all128 offsets, sixteen mask bytes,
   all130 initial outputs and full8KiB memory initialization for EACH member.
   Use unchanged archived assembly; independently establish new ELF helper PCs.
   Grouping adds no predecessor dependency: these archived singles each select
   one independent mmap-backed trial. Execute each group's original order with
   fresh case state, not the original full96-parent program.
2. u0 models PROT_NONE then permission restoration without refill; u1 models
   absent mapping then lower-page remap and2048-halfword refill. Bind concrete
   PTE semantics and mstatus/MXR/SUM in the new Sv39 reference before acceptance.
   Both become load/store page faults, not Linux signal-frame/si_code equivalence.
3. Sparse traps retain actual PC/base/stride/VL8/vtype8/start2 or5. Verify saved
   original vector prefix and each active completed store before repair, then
   poison ONLY completed active addresses. At b1 there is no completed active
   address: never perform the pilot's unconditional element2 prefix read/poison.
   Retry via MRET at the SAME original target PC, preserving GPR/vector context;
   do not call/reload the original helper a second time.
4. At the fault boundary the original handler checks only i<expected_start.
   The pilot's exact whole-vector/whole-memory intermediate snapshot must not
   be generalized into invented constraints on the unfinished suffix. Record
   that suffix; retain the original prefix requirements and full final oracle.
   Final vectors, neighboring registers, guards and full8KiB remain mandatory.
5. All-off must finish its original helper with the lower page still protected,
   zero memory-fault records and no repair/retry. Observe this state before the
   cleanup that the original C performs in `if(!faults)restore_page()`; only
   afterward restore/refill and check the complete memory oracle. Supervisor
   ecall used to return to M mode is not an architectural target fault.
6. Reuse scalar RVFI decoder and numeric outcome/first-failure/raw-veto pattern,
   but derive checkpoint/check counts from the concrete member ledger. Preserve
   exact code/helper interior coverage, target request/trap/retry multiplicity,
   actual vset/CSR values, full scalar memory reads, CTRL0 and pins. No synthetic
   vector values from expected data; Spike and DUT evidence remain distinct.

## Cost And Next Gate

Existing measured references (not rerun): load836971 firmware instructions,
15.256142s Spike; store858371,12.753125s Spike. Actual accepted M6 simulator
times are996.679668s and1111.624556s respectively. Complete/status files are
included in this preparation's input pins; no current trace was read.

Proposed fixed archive-order membership: groups00..08 contain4 members each,
group09 contains2. At the slower measured pilot time plus20%, estimates are
5335.798s per four-member group and2667.899s for the last group. Proposed inner
budgets7200s/3600s are below3h; these are estimates, NOT new-group measurements
or launch authorization. All-off has fewer fault checkpoints, but do not assume
a speedup until the real reference measures it. A four-member reference is
roughly3.43M instructions using the larger pilot, before new fixture overhead.

Next concrete work is the one parameterized Sv39 fixture and reference/CSV
observer, then build/reference each of ten groups once with durable numeric
wait receipts and full oracle. Gate budgets on those actual instruction costs;
if any group cannot fit3h, reduce members per ELF, never CAP, initialization,
oracle or a single member's retry history. Report the ten reference results and
costs together before a separately authorized M6 batch. No per-point approval
documents or generic scheduler are needed.

## Bindable Preparation

- manifest SHA256 `30f48bba795dc7a17abe448e0e84b5d6539dd546af4ea8c0c744c2c53189e449`
- input pins SHA256 `2e948801ee88d559f873cebf6bab205ab8a814052f5331b9284bc0c39dc2f8ea`
- Host result SHA256 `711a2011c83d6101afb22813532bd132d0bc5dc8ff7d0679de31173b9c757593`

No new38 reference PASS, no new38 ELF, no DUT acceptance and no parent/Linux
closure are claimed. Existing two accepted M6 singles remain excluded.
