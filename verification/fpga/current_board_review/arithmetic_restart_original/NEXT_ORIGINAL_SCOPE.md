# Original Arithmetic Scope: Prefixes, Matrices and Stalls

2026-10-11. Bounded source/evidence audit and proposed next-test plan only.
No build, host/Spike/DUT execution, RTL edit, sealed-input change or live-prefix
polling was performed. Prefix5 is **running, parent-confirmed, not accepted**
at this handoff; its results must be assessed separately when terminal.

## Authorities and Identity

`C` below is `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
`R` is `/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix`.

- `R/ISSUES.md`, RVV-02, and `R/repro/ALL_FAILURE_REVIEW.md` explicitly keep
  the original22 arithmetic shapes **outside** the 198-stall inventory.
- `R/repro/STALL_TRIAGE.md`, group B, and
  `C/stall_family_triage02/triage.json` define the separate45-record set.
  Triage SHA256: `eb87f0ed9c07b3978e91e35ff5bcc0824388beb312510ba942ef061c0f63043f`.
- Original22 manifest `C/rvv_extended04/manifest.json` SHA256:
  `6cabb1e462113d3e4c26b29622c6abcfba7cbedbc52fe7b3bfc860678b8a8ce6`.
- Existing [recovery22/report.json](recovery22/report.json) SHA256:
  `b11efd30ec97318d8d4cb37468ae39fea7085f6235fd79a68589e2a6455b8266`.
- Frozen prefix5 plan SHA256 remains
  `34b4caf0f0810a3194449e58bc337b9cadb93d4a31847f70dc871b16c209e0b4`.

This audit freshly rehashed all22 archived arithmetic ELFs and all45 selected
stall ELFs plus their45 selected reports against their manifests/triage.
All matched. All45 have matching source-manifest ELF membership and surviving
generated assembly/header locations. Snapshot verification is inherited from
the historical triage, not repeated here.

## What Prefix5 Does and Does Not Cover

All262 calls execute seed0/op0 `vadd.vv v24,v8,v16,v0.t` (`00880c57`).
They preserve original initialization, predecessor calls, full-capacity oracle,
guards and returned-vstart checks. They are original enumeration positions,
not262 distinct opcodes or necessarily262 distinct numerical input tuples.

| Original shape | Prefix calls | Last zero-based trial | Last VL/start | Historical linkage |
| --- | ---: | ---: | --- | --- |
| e8/m4 | 56 | 55 | 512/256 | Drained `rvv_trace02` explicitly prints this boundary after55 completed trials |
| e8/m8 | 38 | 37 | 512/256 | Original shape stalled; this exact trial is source-derived, not a captured final tuple |
| e16/m8 | 56 | 55 | 512/256 | Original shape stalled; this exact trial is source-derived, not a captured final tuple |
| e8/m2 | 56 | 55 | 256/128 | Prefix of historically passing shape |
| e16/m4 | 56 | 55 | 256/128 | Prefix of historically passing shape |

Original e8/e16 target PCs are `0x1087c`/`0x108ae`; SoC PCs are
`0x80000818`/`0x80000852`. The e8/m4 diagnostic ELF SHA256 is
`00b5b0915c06221afe5432044f3824ab89e347c9ec2d93d515a18f46a2685c1b`.
The existing preparation checked all56 drained trace tuples and unchanged
assembly. A pre-call print plus stopped retirement is not proof of the
target's internal request/acceptance state. Linux tty-drain timing is absent
from the bare-metal runtime.

None of these five original ELF identities is a member of the45-record set.
Even a future prefix5 PASS cannot close a vmacc, vsmul, merge, compare or gather
stall by assumed common root cause.

## Full Original22 Gap

The complete Linux ELFs survive. Original C text does not have a verified
recovered copy: manifest hash is
`b2c21801fc8186d30fbe67d23f31bf5fb89dde1f838314e93c1224b6fdc58c44`;
the existing reconstructed C hash is
`7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91`.
Recovery22 records byte-identical rebuilds of **all22 complete original ELFs**
using original flags and archived assembly/header. This is binary-equivalent
source reconstruction, not recovered original C bytes or execution acceptance.

The archived VLEN1024 reference contains107100 calls across22 shapes:

| SEW | Exact original LMUL set | Shapes | Ops per shape | Calls per complete shape | Calls across shapes |
| --- | --- | ---: | ---: | ---: | ---: |
| e8 | mf8,mf4,mf2,m1,m2,m4,m8 | 7 | 25 | 4095 | 28665 |
| e16 | mf4,mf2,m1,m2,m4,m8 | 6 | 25 | 4095 | 24570 |
| e32 | mf2,m1,m2,m4,m8 | 5 | 35 | 5985 | 29925 |
| e64 | m1,m2,m4,m8 | 4 | 35 | 5985 | 23940 |

References: `C/rvv_extended04/reference_1024.json` SHA256
`4592488745e5158381b4255db779bd9a188b3cd528d3936d0e723c4e49166b9a`
and `reference_512.json` SHA256
`02d48088e4cd453e2dfca9241e7ec1ddf7262a2970cbbc960696fde3535dd135`.
These are historical QEMU results, not new Spike/current-DUT runs. RVV-02
records19 board-passing shapes totaling94815 calls and three stalled shapes.

If all five prefixes pass,106838 original call positions still lie outside
their coverage;17 shapes have no prefix here, and none of22 has full original
current-DUT acceptance. The counts follow the original three seeds, seven VL
positions and three predicate modes. Kinds0 have three start positions; kinds
1/2/3 have one. Duplicate zero-length/start positions must not be deduplicated
when preserving the original sequence and count.

The omitted work includes op1..24 for every current prefix, seeds1/2, later
op0 calls, all e32/e64 programs, and their ten FP operations. In particular,
the source overwrites a/b with FP patterns on entering the FP portion and
maintains the original seed/op/VL ordering. Splitting into unrelated direct
tuples does not preserve that history. Integration "arithmetic38" is a
different program set, including its accepted M4 replay; it closes none of
these complete22 programs by name alone.

## Exact45-Record Decomposition

Let `G = {e8_m4, e8_m8, e16_m8}`. Each name expression below denotes exactly
the listed original or partition ELF names in the triage, with `rvv_` prefix.
There are33 records with printed VL512/start256 and12 without a final trial.
The recorded retest statuses are24 `no_retirement_stall_observed` and21
`not_started`; the latter still have selected **older** stall reports. They
are not21 newly untested or unsupported programs.

| Exact name family | Records | Observed boundary instruction / linkage | Source directory under C |
| --- | ---: | --- | --- |
| `fixed_restart_{G}` | 3 | vsmul.vv; completed776 for e8/m4,e16/m8,520 for e8/m8 | `rvv_fixed_restart01` |
| `fixed_scalar_restart_{G}` | 3 | vsmul.vx; same printed counts | `rvv_fixed_scalar_restart01` |
| `integer_macc_accumulators_restart_{G}` | 3 | vmacc.vv v24,v8,v16; completed481/321/481 in G order | `rvv_macc_restart_disjoint01` |
| `integer_macc_accumulators_alias_first_restart_{G}` | 3 | vmacc.vv v24,v24,v16; same counts | `rvv_macc_restart_first01` |
| `integer_macc_accumulators_alias_second_restart_{G}` | 3 | vmacc.vv v24,v8,v24; same counts | `rvv_macc_restart_second01` |
| `integer_macc_accumulators_alias_both_restart_{G}` | 3 | vmacc.vv v24,v24,v24; same counts | `rvv_macc_restart_both01` |
| `fp_compare_restart_e16_m8` | 1 | vmfeq.vv at0x1062c; VL/start printed, no completed index | `rvv_fp_compare_restart02` |
| `fp_move_restart_e16_m8` and `_ops0` | 2 | vfmerge.vfm at0x10716 /0x10666; completed194; parent and partition identities remain separate | `rvv_fp_moves_restart01`; `rvv_fp_move_partitions02/op0` |
| `masks_cmp_alias_restart_{G}` | 3 | vmseq.vv v8,v8,v16; VL/start printed, no completed index | `rvv_mask_alias_restart01` |
| `masks_scalar_restart_{G}` | 3 | vmseq.vx v24,v8,t3; VL/start printed, no completed index | `rvv_mask_scalar_restart01` |
| `permute_restart_{G}` and `permute_restart_{G}_ops0` | 6 | vrgather.vv; VL/start printed, no completed index; three parent/partition pairs | `rvv_permute_restart01`; `rvv_permute_partitions01` |
| `permute_restart_{G}_ops4`, `_ops5`, `_ops6`, `_ops7` | 12 | vmerge.vvm, vmerge.vxm, vmerge.vim -16/+15; **no final trial printed** | `rvv_permute_partitions01` |

This is45 ELF records, not45 independent bugs or disjoint trial sequences.
The historical mask-supply explanation remains a record-level candidate;
the unqualified head PC is not target-acceptance evidence. Prior numerical
errors in a stalled program must remain failures even if its eventual stall
now disappears.

### Source Readiness

All45 exact ELF/report hashes and source-manifest membership verified here.
Generated S/header files exist for all45. Source availability is more limited:

- **16 partition records have exact current C/generator hashes** against their
  own archived manifests: fifteen permutation partitions (three ops0 plus
  twelve ops4..7) and the e16/m8 FP-move ops0 partition. In R,
  `permutation_oracle.c` hash is
  `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca`;
  `fp_move_oracle.c` hash is
  `27442058b1d14241b93f8d0e7d8c1662d524ff39f509d23434c2f17d6dc37efb`.
  Matching generator/support hashes were also checked. New adapters still
  require unchanged instruction/setup and full-oracle reference validation.
- **29 parent records do not have matching current C bytes**. These are the18
  fixed/macc, six comparisons, three gather parents, one FP comparison and one
  FP-move parent. Their current oracle hashes differ from their historical
  source manifests. No adjacent archived C copy was found in the checked build
  roots; this is not a claim that no older copy exists anywhere. The old
  compiled ELFs, generated S/headers and manifest hashes survive. Require an
  exact old C copy or separately demonstrated byte-identical original ELF
  reconstruction before calling a new port original-source faithful.
- Representative required old C hashes: macc `oracle.c`
  `496a4ddbfa9a4b7c29e71287981d10860f76fcdd5c4bb55830e08bed8bd04222`;
  fixed `oracle.c`
  `b50d3298db2c10f35a5a286f4db01d8b32603afdfc0a0ad1a5b0d3df087e56bc`.
  The existing22-ELF reconstruction proves neither of these different suites.

The accepted scalar19 and alias19 numerical singles **both omit all three G
shapes**. Their PASS does not cover any of the six corresponding large-group
stall records. Accepted FP-move47 comprises ops2/3/4/5/6 at VL2/start1, not
these vfmerge ops0 records. Accepted gather83 comprises small numerical
single ports; it is not these six VL512/start256 parent/partition sequences
or the separate11 gather-stall group. Directed comparison/NV controls likewise
do not replace the original FP-comparison parent prefix.

## Unsupported, Excluded and Untested

| Category | Correct treatment |
| --- | --- |
| Shapes absent from original22 | `build.py:39..41` filters by `64*LMUL >= SEW`; they are outside this ELEN64 original inventory, not failed/skipped original22 records |
| FP16 in the basic arithmetic matrix | Original e8/e16 headers have25 ops; only e32/e64 add10 FP ops. FP16 is outside this particular original suite, not evidence of unsupported current hardware |
| Restart on basic ops19..23 | Kinds1/2/3 run only start0 in the original oracle. Do not manufacture nonzero-start variants to fill an apparent coverage hole; no restart acceptance for those operations follows |
| Later suites deliberately using vstart0 | Explicit historical coverage exclusion in RVV-02; neither a fix nor acceptance of the restarted original |
| e8/m8 vrgatherei16 | Permutation manifest excludes reserved index EMUL16. Preserve this source exclusion; it is not one of the valid ops0/4/5/6/7 records here |
| Missing final trial for12 merge records | Unknown trigger, not unsupported. The assembly/ELF and oracle are available; use original-sequence evidence, not an asserted fabricated boundary |
| Current source differs from old manifest | Provenance gap, not hardware capability failure; no relabeling as PASS/SKIP |
| Programs/trials outside accepted prefixes | Untested by these prefixes, even if another shape or a related opcode passed |

## Bounded Next Preparation Plan

This is a proposal, not launch authorization or a newly prepared manifest.
Parent retains scheduling; FP2's separate late-abort hold is not changed.

1. **Finish prefix5 acceptance first**, without polling here. Use its exact
   terminal/raw identities and actual elapsed/reference-instruction costs to
   calibrate a next budget. A failure stops arithmetic expansion and requires
   that exact source call/sequence to be diagnosed; do not raise timeouts or
   replace the oracle speculatively.
2. **Next original22 preparation batch: at most two complete small shapes**,
   `rvv_matrix_e8_mf8` (4095 calls) and `rvv_matrix_e32_mf2` (5985 calls).
   Use recovery22's binary-equivalent C with original S/header; runtime-only
   adaptation, all three seeds and all ops retained. These are historically
   passing controls that establish feasibility of complete-source execution
   across integer-only and integer+FP matrices, not substitutes for the three
   failed shapes. Host/Spike must prove exact counts/full oracle and provide
   costs before a parent-reviewed DUT budget. Do not launch all22 at once.
3. **In parallel preparation, recover one new stalled opcode only**:
   `rvv_integer_macc_accumulators_restart_e8_m4`, original ELF SHA256
   `608e941760443563f055058d60f18ce466a06d016fb277989fc332ed9cdb347d`.
   S/header: `C/rvv_macc_restart_disjoint01/`; ELF:
   `C/rvv_additions42/binaries/`; original scene:
   `C/rvv_recovery08_14/terminal_scene/`; latest selected report is
   `C/rvv_failure_retest01/supervisor44/terminal_recovery238.json`.
   Target `vmacc.vv v24,v8,v16,v0.t` at0x108e0, next csrr0x108e4,
   seed0/mask0/VL512/start256/completed481. First prove the old-source binary
   identity, then prepare original calls0..481 inclusive (482 calls), retaining
   all accumulator patterns, RNG/state and CSR checks. Confirm that the traced
   counter maps to this exact call in recovered C before fixing that prefix
   length. The original complete suite has22400 calls and five input seeds;
   the current vadd helper/oracle cannot stand in for it.
4. **Only after those bounded preparations are reviewed**, extend complete22
   coverage to e8/m4, e8/m8, e16/m8 and then the remaining17 shapes (the two
   small-shape controls plus these three account for five of22). Each complete
   shape must preserve all original calls. If costs require partitions, retain
   predecessor execution/state; report tuple coverage separately from full
   contiguous-program acceptance. Do not claim a reset partition is the full
   original sequence. Software-reference instruction counts and measured
   comparable costs are prerequisites, not guessed short simulation budgets.
5. **Then process the45 ledger by evidence tier**, with explicit parent/child
   accounting: macc's remaining11 identities; fixed six; comparison six and FP
   comparison one; FP-merge parent/partition two; gather parent/partition six;
   merge twelve. Each batch gets a recovered source, exact original prefix or
   full original partition, full oracle, and raw target/completion evidence.
   This order is not an assertion that they share a cause or that one passing
   representative closes the rest.

For the next fixed-point representative, the exact available identity is
`rvv_fixed_restart_e8_m4`, SHA256
`ca6937f7969cb2664becfe53fac5e49111415929e96220874568964b293b85cc`,
target vsmul.vv at0x1094e, completed776; a future777-call prefix must preserve
vxrm and sticky vxsat as well as data. Scalar counterpart SHA256 is
`e3cc6bbc47f50d700e89711d37dfe38baf42f68c8a68a6ca28271ffa930dd7d0`,
target vsmul.vx at0x10aee. Neither source recovery nor port was performed here.

The source-ready FP-merge partition has SHA256
`d8abfc1bfebe188b1045a786e2ce17ba571e523c363b365ed28b805c99881710`.
Its completed194 print suggests195 calls through the boundary, but scalar
choice/boxing/fflags and loop mapping must be verified before declaring that
an exact prefix. For the twelve untraced merge partitions, start with a
source-preserving full2688-call partition feasibility measurement, not a
claim that a chosen VL512 singleton reproduces the historical stall.

## Closure Rules

Maintain separate outcomes for (a) exact prefix/tuple acceptance, (b) all
original source configurations with predecessor state, (c) full unmodified
Linux ELF on a pinned deployed image, and (d) measured internal root cause.
Pure arithmetic source programs are suitable for existing bare-metal SoC VCS
once provenance and reference gates pass; Linux syscalls are not needed for
their scalar mathematics. Original ELF/tty-drain/OS timing closure still
requires Linux/board or a separately authorized Linux-capable environment.
No source-port PASS silently satisfies that requirement.
