# Segment Boundary Nine: Exact Gap And One Full-Source Plan

2026-10-13. Static/archive review only. No live-process queries, RTL changes,
compilation, Spike, VCS, or repeated zero16 audit. **All nine RVV-18 records
remain unaccepted as original programs; no new current RTL bug is proved.**

## Exact Evidence

Path aliases: `C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`;
`R=/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix`;
`A=C/rvv_segment_alignment01`; `G=verification/fpga/current_board_review`.
Authorities: `G/CURRENT_SCOPE.md` RVV-18 row, `R/ISSUES.md:4177`,
`R/repro/STALL_TRIAGE.md` G, and `R/repro/ALL_FAILURE_REVIEW.md`.
This is NOT CAP-01's separate nine ordinary preparation-load SIGBUS records.

Every ELF below is `rvv_segment_alignment_<shape>`. Independently hashed three
copies per record: `C/rvv_recovery08_<recovery>/terminal_scene/<ELF>`,
`A/overlay/opt/ara-tests/<ELF>`, and `C/rvv_additions32/binaries/<ELF>`.
All 27 hashes match the original `A/manifest.json`.

| Recovery / shape / full configurations | Last retired / unqualified head PC | Last recorded trap (cause / PC / tval) | Original ELF SHA256 |
|---|---|---|---|
| 18 / e16_mf4 / 432 | 10718 / 1071c | 2 / ffffffff80907a2c / c0102573 | 4a4d90110888dda88834826dd0a65fc4dbc3ac567b1fde402ff8d307dee2ed0b |
| 35 / e16_mf2 / 432 | 10718 / 1071c | 15 / 10718 / 3fbb916000 | b6b0c2f4382e85246ce552611d49a50bde59b21bba6a64ea973323bc39f45ec7 |
| 36 / e16_m1 / 432 | 10718 / 1071c | 15 / 10718 / 3f8639d000 | 58489bb95780201262a84bba04a6e1b7afb96216f7162134251787b212dfa8dc |
| 37 / e16_m2 / 144 | 1071e / 10722 | 15 / 1071e / 3f853da000 | cfcdabf6e7a378d789c01dde8864e4beb16a133712090e805841cb24648db1df |
| 38 / e32_mf2 / 648 | 10704 / 10708 | 15 / 10704 / 3fae1c9000 | c99bbaf553620955f840f4a176aed40d8b6798b164c70f3c320f2dd7a23c199b |
| 39 / e32_m1 / 648 | 10704 / 10708 | 15 / 10704 / 3f8beaa000 | 915d1b55125923a45379f836f4c1002f5c16675f8c60ddd553376bf554759675 |
| 40 / e32_m2 / 216 | 1070a / 1070e | 15 / 1070a / 3f90f0f000 | 66099f6f1ace2abb2565a747bdc96aad20d3c56828b006838b5d3aeb77f41b03 |
| 88 / e64_m1 / 648 | 10706 / 1070a | 15 / 10706 / 3fbbdfd000 | 8b916a0dd4c4dee84ccbfa098b2664bc4cf4fee03b656d33d3717fc4fd390a3d |
| 89 / e64_m2 / 216 | 1070c / 10710 | 2 / ffffffff80907a2c / c0102573 | 09b447f99833b73b9e68457b6c565ce7aaafef838d3d704a8948c093293b4432 |

PC/tval columns are hex. Read both `batch_progress_000{1,2}/snapshot.json`
in each terminal scene: retirement, last/head PCs, trap count and trap fields
are unchanged while cycles advance; both DDR channels have zero outstanding
transactions/errors. `stall_disassembly.txt` and archived assembly identify
the boundary as `sd t3,0(a7)` (phase1) then **op_0, masked vlseg3**.
Seven last traps belong to the scalar phase store, not the vector target.
The other two are historical kernel cause2. Neither establishes the current
fault, accepted target, exact iteration, offset, VL, or predicate. No final
numerical marker exists. Do not label these proven active misalignment bugs.

## Acceptance Mapping And Current Risk

- NF2: `G/masked_translation/segment_review/nf2_remaining34_terminal_audit01/terminal01/REVIEW.md`
  accepts all40 failed-source geometries on M6, plus two separate controls.
  Its NF2 page-split/restart programs are not these NF3..8 alignment programs.
- NF7: `G/masked_translation/indexed_review/sv39/nf7_m6_terminal_audit02/terminal01/REVIEW.md`
  accepts96 indexed source trials on M6, not unit/strided alignment or Linux children.
- NF8: `G/masked_translation/nf8_strided_review/sv39_full192/terminal_resume20261011.md`
  accepts192 positive-stride fault-replay source geometries on **M4**, not an
  automatic M6 acceptance and not this resident alignment diagnostic.
- Therefore none of these acceptances closes any of the nine exact ELFs.
  The newly passed M6 zero16 is also a different source/program.

Current working RTL has relevant handling: dispatcher empty-segment reservation
release (`hardware/src/ara_dispatcher.sv:5981`), illegal-memory completion balance
and segment reservation cleanup (`:5303`), segment-store ownership (`:5940`),
masked alignment handling in `hardware/src/vlsu/addrgen.sv`, and fault-load done
barrier (`hardware/src/ara_sequencer.sv:1026`). These are static paths, not a
measured explanation of RVV-18, and current RTL must not be called frozen M6.
Discriminator: correlate scalar phase-store trap/return and CVA6 head validity
with `acc_req` acceptance, dispatcher state/pending segment, segment field
request/response, AddrGen exception/ack, VLDU/VSTU/MASKU owner/done and final
architectural completion. If no target acceptance occurs, investigate scalar
page-fault/vector-context recovery rather than attributing a field deadlock.

## One Candidate, Full Scope Preserved

Select **e16_m2 / recovery37**, the smallest complete original program (144).
Source `R/segment_alignment_oracle.c` matches manifest SHA
`dd99ad9ba59c451dc01891b2badcd182a2453ceb6651dd1cb683bd8f6b5a8bb0`;
generator `R/segment_alignment.py` matches
`4ddb4103829436036c57b6943a3bad1b48856426f6b646c66a6cafb173413ab7`.
Use archived `A/e16_m2/operations.S` SHA
`148e306376c55a260c109a9ff917e789cadf03139d3b02fb8374e79fb73e23bc`
and `operations.h` SHA
`333a64555c43af7f8831bf2c48307e7cabcad866b8ec3a197a7f4d2d57ebb50f`.
Current transitive `segments.py` hash differs from the manifest: do not claim
whole-generator identity or regenerate through it without checking the archived
assembly/header. No source equivalence is inferred from an NF2 fixture.

Preserve eight operations (NF3/4 x unit load/store and strided load/store),
original positive/negative-stride enumeration, offsets0/1, VL0/1/cap128 at
VLEN1024, both ff/all-off masks, vstart0, all144 configurations in order.
Retain all8192-byte input/memory/output/expected initialization each time,
128-byte masks, full8192-byte result-or-memory oracle, helper return vstart,
phase stores and original aligned staging/readback. Linux `clone(17)` isolates
each child: a continuous direct-call port must restore the parent's memory
semantics rather than accidentally retain child store results. Shared scene
mapping and Linux demand/COW/context effects are not equivalent to a resident
Sv39 replacement; an invented permanently protected phase page is not original.

Oracle accepts either correct numerical completion or **only** a target SIGBUS
when offset!=0, VL!=0, mask active, and phase==1. Preserve capability exit77
separately from numerical success; VL0/all-off traps, phase-store faults and
other failures cannot be waived as unsupported alignment. Historical
`A/reference_1024.json` records144 numerical passes/96 no-active passes/zero
SIGBUS for this exact ELF in QEMU Linux, not DUT or current Spike evidence.
On a numerical path full144 requires1,179,648 byte comparisons. If all24
eligible misaligned active configurations trap, the120 numerical cases still
require983,040 comparisons; do not invent readback for terminated children.

## Three-Hour Admission: Blocked, No Reference Run

Read actual archived e16_m2 ELF disassembly using the existing non-ZCC objdump.
The8192-iteration initialization loop is `0x10302..0x10386`:28 retired
instructions/byte for stores,37 for loads (the latter include the nine load-only
instructions, including0x10372). There are72 configurations of each kind.
Thus initialization alone costs **38,338,560 instructions**. A successful
byte comparison at `0x104a0..0x104c4` costs7 instructions, adding8,257,536 if
all144 complete numerically. These exclude mask setup, expected-value edits,
helpers, system calls, page faults and process management: not a full upper bound.

The newly reported zero16 runtime3143.888s and its pinned reference2165648
firmware records give a limited proxy of689 records/s; negative-store's
851704/1111.624555705 gives766/s. **Initialization alone projects13.9..15.5h**,
not <3h; at273/s it is39h. These are cross-program estimates, not measured
alignment timing or a universal speed bound. Even initialization would need
3550 records/s to fit3h, with no allowance for the actual oracle or Linux.

Accordingly there is no evidenced <=3h full-original M6 VCS admission here.
Next complete-program route is the unchanged e16_m2 ELF on a compatible Linux
target, with bounded phase/acceptance diagnostics and a hard3h stop, after
explicit environment/resource approval. It preserves the actual fork/shared-page
boundary; runtime feasibility is not yet established. A software-only full144
port may be prepared later, but must first declare its Linux limitations and
derive a finite reference bound. Do not launch a knowingly over-budget VCS,
drop checks, guess a stalled VL, or silently substitute an op_0 prefix.

No Host/Spike preparation was started: reliable original sources exist, but the
requested complete-source/three-hour VCS combination lacks budget evidence.
Manifest SHA: `c9d7eafaa356ebab465b81ed8330632c98e8b6a0923dc80b576bad3d404066ee`.
Historical QEMU1024 report SHA: `abe8aa29d82f3dc687d43348f299de7faf5f95ca34d11cb2fe275e2ed9044b9c`.

## Follow-Up: Per-Record Mapping And Measurable Next Gap

Read the nine terminal `batch_uart.bin` files and `report.json`/`state.json`
metadata, not any active run. All nine have the named ELF's PREP/START only,
zero `RVV_SEGMENT_CAP_DETAIL` lines, and no completed segment numerical result.
The empty `console.log` is not the UART evidence. Recovery18/35 START indices
are22/9; the other seven are0. These are **batch ELF indices**, not internal
configuration indices, and cannot establish offset0/VL0/all-active.

Exact-source mapping (all cells remain non-matches):

| Original record | NF2 M6 (e16/m1, unit NF2) | NF7 M6 (e32/mf2, indexed NF7) | NF8 M4 (e32/mf2, positive-stride NF8) |
|---|---|---|---|
| recovery18 e16/mf4 | SEW only; different LMUL/NF/source | Different SEW/LMUL/NF/addressing | Different SEW/LMUL/NF/source |
| recovery35 e16/mf2 | SEW only; different LMUL/NF/source | Different SEW/NF/addressing | Different SEW/NF/source |
| recovery36 e16/m1 | Same SEW/LMUL, but NF3 target/phase/fork untested | Different SEW/LMUL/NF/addressing | Different SEW/LMUL/NF/source |
| recovery37 e16/m2 | SEW only; different LMUL/NF/source | Different SEW/LMUL/NF/addressing | Different SEW/LMUL/NF/source |
| recovery38 e32/mf2 | Different SEW/LMUL/NF/source | Same SEW/LMUL, but indexed NF7 != unit NF3 | Same SEW/LMUL, but strided NF8 != unit NF3 |
| recovery39 e32/m1 | LMUL only; different SEW/NF/source | Different LMUL/NF/addressing | Different LMUL/NF/source |
| recovery40 e32/m2 | Different SEW/LMUL/NF/source | Different LMUL/NF/addressing | Different LMUL/NF/source |
| recovery88 e64/m1 | LMUL only; different SEW/NF/source | Different SEW/LMUL/NF/addressing | Different SEW/LMUL/NF/source |
| recovery89 e64/m2 | Different SEW/LMUL/NF/source | Different SEW/LMUL/NF/addressing | Different SEW/LMUL/NF/source |

NF2's accepted error-context singles and NF7/NF8's accepted remap/retry
contracts test related VLSU mechanisms, not this scalar phase-store/Linux
child boundary. Even a later matching NF7/8 suboperation in a full alignment
ELF would not identify its observed NF3 stall or replace its full oracle.

**One explicitly narrower alternative, for scope review only:** recovery37's
observed PC identifies `op_0`; the original source calls that helper in its
first12 configurations (offset0/1 x VL0/1/128 x ff/all-off, reverse0).
Covering all12 in original order avoids choosing an unknown failing tuple.
Preserve each original full initialization, mask128, aligned preparation,
phase1/2 stores, target/helper, vstart return and all8192 checked bytes:
98,304 result-byte checks on the all-numerical path. Four configurations are
active; two of those are misaligned and may take the original allowed
capability branch instead of numerical completion. Do not fabricate outputs
or successful return-CSR reads for a child terminated by SIGBUS.

This is an **original op_0 source-block diagnostic**, not full144 acceptance
or an exact reproduced historical failure. Linux fork/shared-page/vector-context
effects remain unproved by a direct-call Sv39 port. Do not force an artificial
phase-page fault to imitate the recorded last trap. Full144 remains the
complete-program candidate and retains the budget block above.

Static minimum for this12-call block: 12*8192*37 =3,637,248 initialization
instructions, plus12*8192*7 =688,128 successful comparison instructions.
Total4,325,376 excludes expected-value construction, wrapper and traps.
At the measured zero16-derived689/s proxy that subtotal is105min (126min
with20% margin); at273/s it already exceeds4h before margin. Thus a <=3h
run is plausible with the closer proxy, **not yet admitted or guaranteed**.
Next preparation, only if this explicit reduced scope is accepted: reuse
archived assembly/header and original oracle, derive the adapter's actual
static upper bound, then one bounded Host/Spike reference to measure full
firmware cost and allowed-trap behavior. Decide VCS admission from that cost;
no automatic timeout growth, no partial-oracle PASS and no DUT launched here.
