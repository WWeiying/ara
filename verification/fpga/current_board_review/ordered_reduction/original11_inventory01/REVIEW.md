# RVV-07 Original11 Inventory And Next Discriminator

2026-10-11. Read-only source/evidence review. Only this new directory is written.
No compile, Host/Spike/DUT execution, live query, RTL or sealed-file change.
The running M6 VI0 first112 campaign was not queried. Reading CURRENT_SCOPE's
existing statements is not a new observation of any running campaign.

## Conclusion

The `/11` means **11 failed original Linux program/shape records**, each with a
board-confirmed one-call reduction. It does not mean11 unique fixture indices,
11 rounding modes or11 independent roots. The reduced cases all select the
same coordinates: scenario3, length slot4, mode3/0x24, frm0, ordered op0,
sticky0, at11 SEW/LMUL shapes.

CURRENT_SCOPE's substantive remaining gap is real: no source-faithful SoC
single for the other10 shapes was found in the reviewed current evidence.
However its F4/M2-only description of `reduction_fflags` is stale: the same
e32/m1 source-derived single is independently accepted through **M6**, with
the complete CSV unchanged from its M4 control. Reuse it; do not rerun it just
to fill an11-row table. All11 full6720-call Linux parents remain outside that
acceptance. No new RTL bug is established by this inventory.

Machine-readable [inventory.json](inventory.json) contains all11 records,
original/reduced ELF identities, six source/header pins per record, fixture
entries, first/terminal board output, current coverage classification, proposed
membership and150 freshly computed SHA256 bindings. No published PASS is
silently upgraded from reference or module evidence.

## Archived Source Chain

Use these roots:

- `C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`
- `H=C/rvv_verified_handoff03/rvv_small_redspecial02`
- `R=/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix`
- `G=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review`

`H/source_manifest.json`, `symptoms.json`, `original_report.json`,
`board_report.json` and each `H/rvv_small_fp_redspecial_<shape>/case.json`
provide the source-to-original-to-reduced chain. Each case directory contains
`original.elf`, `scenario.elf`, `scenario.c`, `operations.S`, `operations.h`,
`fixtures.h`, `input_bits.h`, `fp_reduction_inputs.h`.

The actual original C is **R/fp_reduction_oracle.c**, not a guessed
`original.c`. Its current SHA f92ffb3af070febf3dfebb85b0a25f6c5612b95044e2aa1262d600687926eb4f
matches both original campaign manifests. A read-only diff against the common
archived scenario.c shows exactly one inserted inner sticky-loop selector.
Fixture selection/index increment and all original checks are unchanged.
All11 scenario.c hashes match fd6870fa4eed43bd660136c9d90577f5cfbe99d7ba834a14fedad96237cd251a.

Full original Linux binaries also remain at:

- e16: `C/rvv_fp16_redspecial01/overlay/opt/ara-tests/rvv_fp_redspecial_<shape>`;
- e32: `C/rvv_fp_redspecial03/overlay/opt/ara-tests/rvv_fp_redspecial_<shape>`.

All11 freshly computed full-original and handoff-original ELF hashes agree;
all11 reduced ELF hashes and66 scenario-source/header hashes agree with the
handoff manifest. The archive records byte-identical original rebuilds; this
review checks retained identities, not a new rebuild. Corresponding fixtures.json
files remain at `C/rvv_small_redspecial02/rvv_small_fp_redspecial_<shape>/`.

The11 selected records in recovery202's actual `terminal_scene/report.json`
are JSON-identical to H's original-report records. Recovery216's11 reduced
records are likewise identical to H's board-report records. Whole report
hashes differ because snapshots/wrappers contain other state; this is not an
ELF or selected-result mismatch. Their run IDs are respectively
69dbca9c7803589118d7625f30051734 and2fb2e25b34a49228a30265fe80da8347.
These archived snapshots may say a broader campaign was running; that does
not negate the explicit completed exit1 results of the selected11 children.

## Exact Eleven

Names expand to `rvv_fp_redspecial_<shape>` and
`rvv_small_fp_redspecial_<shape>`. All reduced records are exit1, cases1,
flags_seen0, errors1, expected_flags16. No reduced raw result bits were printed.

| Shape | VLMAX at1024 | Selected VL | Original full errors /6720 calls | Current source-derived SoC single |
| --- | ---: | ---: | ---: | --- |
| e16_mf4 | 16 | 8 | 60 | Not found; proposed first discriminator |
| e16_mf2 | 32 | 16 | 64 | Not found |
| e16_m1 | 64 | 32 | 66 | Not found |
| e16_m2 | 128 | 64 | 66 | Not found |
| e16_m4 | 256 | 128 | 66 | Not found |
| e16_m8 | 512 | 256 | 66 | Not found |
| e32_mf2 | 16 | 8 | 60 | Not found |
| e32_m1 | 32 | 16 | 64 | reduction_fflags accepted through M6 |
| e32_m2 | 64 | 32 | 66 | Not found |
| e32_m4 | 128 | 64 | 66 | Not found |
| e32_m8 | 256 | 128 | 66 | Not found |

There is no e64 failed record in this11 and no e16/mf8 member to invent.
Original logs print19 DETAIL lines per parent because printing is guarded by
`errors<20`. Visible lines cover scenario3/op0/mode3 at cap/2 with all five frm
and sticky0/1, then cap-1 with a truncated last rounding/sticky pair. The final
60/64/66 error counts exceed the printed detail window. Do not assign every
unprinted error to this one root, infer its tuple, or treat errors as numbers
of independently proven causes. `flags_seen=21` across a whole parent also
does not mean each ordered operation correctly delivered NV.

## Fixture Indices And Full Oracle

Original order is scenario8 x length7 x mask4 x rounding5 x op3 x sticky2:
6720 helper calls per full parent. The reduced selector leaves one call,
not a3091-call prefix. Its full-parent ordinal would be3091; the preceding3090
target calls are absent from this already board-confirmed reduced reproducer.

At the selected point the within-scenario index is
`((4*4+3)*5+0)*3+0 = 285`. Therefore:

```text
bank = (vlenb == 128) = 1
row = scenario*420 + index = 3*420 + 285 = 1545
flattened [2][3360] index = 3360 + 1545 = 4905
```

All11 use this same row number in **different shape-specific tables**.
The freshly read fixtures.json entries are0x7e00/NV16 for e16 and
0x7fc00000/NV16 for e32. In bank0 (VLEN512), e16/mf4 and e32/mf2 instead use
VL4 and expect +Inf/flags0: selected negative infinity at element5 does not
exist. Accidentally using bank0 would make the smallest discriminator useless.

Scenario3 sets seed +Inf and alternating +Inf/-Inf input. Mask bytes0x24
select elements2 and5 in each8-element block: the first selected -Inf is index5.
Original helper op0 has21 instructions, with these preserved operations:

1. m1 full-register seed v16 and old-vd v24 loads; original data-LMUL vset,
   fullcap v8 load and vlm v0; requested-VL vset.
2. Save frm/fflags, set requested frm and sticky, execute
   `vfredosum.vs v24,v8,v16,v0.t`.
3. Read vstart and fflags, return `(flags<<32)|vstart`, restore old frm/fflags;
   switch to m1, store the entire destination register, return.

The C checks returned low32 vstart0 and exact flags, then **all144 output
bytes**. At VLEN1024 this is8 left guard bytes,128 destination bytes,8 right
guard bytes. Only destination element0 changes (2 or4 bytes);126 or124
remaining destination bytes and both guards must stay0x5b. No active-only,
first-element-only, flags-only or shortened tail oracle is acceptable.
Actual trace validation should additionally bind all21 helper retirements,
selected fixture address/values, setup arrays, mask, vsets and save/restore CSR
values. It must preserve rather than replace the original144-byte check.

## Existing Evidence And Documentation Drift

**Historical reference:** `C/rvv_small_redspecial02/reference_{512,1024}.log`
contains genuine Linux-on-QEMU PASS11 at each VLEN with the required Zfh/Zvfh
configuration. These are references, not current RTL passes. The earlier
small_redspecial01 default-CPU FP16 illegal-instruction setup failure remains
separate. Its e32/m1 scenario/assembly/fixture/reduced-ELF identities match02,
so integration's use of01 for that e32 case is not a different stimulus.

**Module repair:** `G/ordered_reduction/MEASURED_20261010.md` and retained
`/tmp/ordered-reduction-extended-after-20261010-01/status.json` record166/166,
compile/run0, no failures. Of these,110 are11 source VL/width labels x5frm x2
prior-NX settings. They are real VMFPU/FPnew tests with modeled masks/transport/
sticky CSR, not original helper/dispatcher/VRF/SLDU/CSR ELF executions. The
matched before/after suite reports132 corrected flags, no result/cycle changes.
The common measured root is low-slot compacted FP operands versus unshifted
exception-enable mask. Current and frozen M6 vmfpu hashes match and the OSUM
path at2519 still uses `be(1,vsew) & {StrbWidth{osum_active}}`.
This proves the local repair's scope, not all unprinted parent failures.

**Source-faithful SoC acceptance:** reuse
`G/gather_repair05/m6_regression48_terminal_audit01/REPORT.md` and its pinned
audit.json, plus `repair06_regression48_prepared01/complete.json` and
`original38/tests/singles__reduction_fflags/` actual logs/ELF/CSV. They show:

- PASS, numeric simulator rc0, elapsed21.174716s; raw exact original marker
  `RVV_FP_REDSPECIAL_PASS sew=32 cases=1 flags_seen=16 errors=0` and normal exit.
-5324 retirements,5381 CSV rows, last cycle9435. Note5381 is rows, not retired
  instructions. Full CSV SHA7ad44189a21591dcbb742de6678e34bd3882f7e2d2526ec5d0395dce4336357a
  agrees with the accepted baseline; the terminal audit compared it bytewise.
-M6 image SHA a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0,
  private ELF SHA c2c0e8d6373e08815325d38130762c62194b21f774fdb7207c8e3ba68fbe3978.

This review freshly hashes these files and reads existing terminal acceptance;
it does not rerun all48 validators or fabricate outer-service exit facts.
The older full16 acceptance explicitly leaves historical outer service exit
unavailable after GC, while accepting actual child functional results.

Searches of current verification/apps source references and review docs,
integration/fast adapters, ordered reduction sources, campaign handoff and
relevant archived artifacts found no further source-faithful SoC shape among
the other10. The negative search is bounded to these available records, not
a claim that no unindexed private experiment exists anywhere. Generic reduction
smokes, unordered/widening epoch tests and166 module cases are different scopes.
CURRENT_SCOPE need only advance e32/m1 throughM6 and describe the remaining10
source singles precisely; this review does not edit that shared document.

## Shortest Useful Next Preparation

**First:** one original e16/mf4 reduced scenario, VL8, fixture[1][1545],
frm0/sticky0/mask0x24. It introduces FP16 plus fractional-LMUL decoding and
actual CSR/mask/VRF/slide integration absent from the accepted e32/m1 single.
It uses the smallest board-confirmed trigger, not a synthetic replacement.
Do not repeat the local before/after experiment or the accepted e32/m1 single.

**Then, only to close the remaining original-single membership:** the other9
unaccepted shapes in the table, each one original helper call and full oracle.
Together these10 new singles plus the existing accepted e32/m1 would cover
the11 reduced triggers, still not11 full6720-call Linux programs. Larger e16/m8
and e32/m8 add real source-group allocation/length; e32/mf2 adds its fractional
decode at VL8. These are integration dimensions, not ten newly independent roots.

Keep original source/headers/ELFs immutable, namespace each helper, and bind the
21 original instruction encodings. Use separate one-case ELFs initially, so
each begins from its own runtime and a combined cross-shape history is not
mistaken for original behavior. There is no need to replay the3090 omitted
full-parent predecessors to reproduce the archived **already reduced** single;
conversely, a one-call pass cannot close that omitted history.

For short execution, reuse the reviewed integration_fast selection-bound proof
as a pattern, not an unproved source rewrite: selected scenario3 initializes
every subsequently read input/seed, selected mode3 writes all64 mask bytes,
and the helper establishes/restores its CSR state. The original fixture cursor
must advance by285 before the retained fixture access. Never advance to the
wrong bank/row, remove the fullcap loads, or remove the unused destination bytes.
Future host/reference validation must independently check every new shape's
full setup/oracle equivalence before using this narrowing. Leaving all reduced
empty loops intact is correct but performs3360*64 mask-byte assignments; the
short timing estimates below do not apply to that unoptimized traversal.

Provisional budget, **not an authorization or measured new result**:

- Reference per new ELF: <=5M steps,120s,768MiB per log; unchanged complete
  fixture/21-helper/144-byte/CSR/exit vetoes, with true FP16 support.
- DUT per narrowed single: fixed600s, no retry; pilot first, stop on first
  failure. The existing e32/m1 takes21.2s/5324 retirements. Larger source setup
  and ordered length warrant roughly20..300s planning range, not a guarantee.
  Require the new reference's actual retirement count before final admission;
  approximately100k retirements already implies about400s at the existing
  observed252 retired/s rate, before differing vector-cycle costs.
- At most2 future workers,10 total new singles: worst5 waves*600s plus
  teardown/checking fits a proposed3600s outer bound. No build or service is
  started here; any image and resource admission is a separate parent decision.

Do not immediately expand to all five frm/sticky modes, other scenarios,
min/max or whole6720 parents merely to inflate case counts. Those are distinct
remaining scopes; the original visible logs and local110 mode points should
guide any subsequent hypothesis. The first new source-faithful FP16 single
is the shortest missing discriminator, while ten singles is the smallest
membership-complete supplement without repeating the accepted e32/m1.
