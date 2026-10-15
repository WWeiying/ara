# Recovery168 Returned Numeric Tuple: Coverage Deduplication

2026-10-12. **NO EXACT MATCH in accepted83 source singles or the measured natural prefixes listed below.** This is a returned-call numerical coverage gap, not recovery of the stopped tuple, a new DUT failure, or an authorization to launch.

Roots: `G=/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/gather_original_review`; `C=/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.

Only existing manifests, archived source/assembly, stored reference fixtures, and completed terminal/audit JSON/notes were read. No commit CSV (running or completed) was read, no raw oracle was rerun, and no simulation/build/Host/reference/RTL change or process/service query was performed. Existing independent terminal acceptance is reused, not reissued here. Only this new note is written.

## Identity Being Compared

- Original child: `rvv_permute_restart_e8_m4_ops3`, original Linux ELF SHA `a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b`.
- Returned numerical-error tuple: **SEW8 / LMULm4 / op3 VI31 / seed0 / scalar0 / VL256 / mask-mode0 / vstart128**. Raw complete DETAIL lines include elements0..3 expected91/actual177. The unfinished element4 line supplies no actual value.
- Under VLEN1024, cap512, this is source ordinal **66**, loop identity `[seed=0, op=3, scalar-slot=0, length-slot=4, mode=0, trial=1]`: `4*16 + 0*4 + 1 + 1 = 66`. The 65 preceding executed calls are within this opcode child; excluded ops0..2 loop iterations execute no helper. The archive snapshot does not independently measure vlenb/cap512; this ordinal remains a source/configuration mapping.
- Exact coverage requires the same source identity, SEW/LMUL/capacity, opcode/immediate, seed, scalar slot/value, VL, mask mode and vstart/trial. Equal reported expected/actual bytes or shared machine opcode alone is insufficient. An executed single and its natural-history prefix also have different history scope.

## Accepted83: Exact Absence

`inventory83.json` and `remainder75_01/coverage83.json` each contain83 records with the same unique sourcekey set. Normalizing their `rvv_small_gather_restart_*` names to `gather_*` exactly equals the disjoint8 audit members plus75 terminal members, with no duplicates. The8 audit results are PASS; all75 terminal results are PASS/numeric rc0. The coverage ledger's prepared75 status is a prelaunch snapshot, not a current failure; current acceptance comes from these terminal records.

Comparing `(SEW, LMUL, op, seed, scalar, VL, mask, vstart)` gives **0 exact matches**, and even `(8,m4,3)` gives **0 shape/op matches**. `rvv_permute_restart_e8_m4_ops3` is absent from both inventory83 and lineage83, not an alias to one of their accepted sources. No new record is added to the accepted83 count.

The nearest accepted e8 VI31 sources are:

| Accepted source single | cap | Selected tuple | Why not duplicate |
| --- | --- | --- | --- |
| `rvv_small_gather_restart_e8_m1_ops3` | 128 | seed0/scalar0/VL2/mask0/start1 | Different LMUL/cap/VL/start/source ELF |
| `rvv_small_gather_restart_e8_m2_ops3` | 256 | seed0/scalar0/VL2/mask0/start1 | Different LMUL/cap/VL/start/source ELF |
| `rvv_small_gather_restart_e8_mf2_ops3` | 64 | seed0/scalar0/VL2/mask0/start1 | Different LMUL/cap/VL/start/source ELF |

Their original failure bytes also include91/177; that value coincidence does not establish tuple coverage.

## Measured Natural Prefixes: No Exact Duplicate

The following terminal results/independent audits were inspected, not live tasks:

| Completed prefix | Calls / cap | Match or discriminator |
| --- | --- | --- |
| M5 `e8_m4_ops1`, `e8_m4_ops20` | 98 each /512 | Both include VL256/start128 at call66, but VX0 and indexed-e16 respectively, not VI31. Their target encodings differ from308fbc57. |
| M6 `e16_m8_ops1`, `e16_m8_ops20` | 98 each /512 | Different SEW/LMUL and opcode. |
| M6 `e16_m8_ops3` | 98 /512 | Same numeric VL256/start128 and immediate31, but halfword source31=32689, not byte177; different source ELF/SEW/LMUL. |
| M6 `e8_m8_ops1` | 66 /1024 | Different LMUL/cap/op; endpoint VL512/start256. |
| M6 `e8_m8_ops3` | 66 /1024 | Same VI31 encoding/source byte177, but different LMUL/cap. Its original lengths are0,1,2,3,512,1023,1024: **no VL256 call**. Call66 is VL512/start256, not this returned tuple. |
| M6 `e8_m8_ops2` | 112 /1024 | Existing terminal PASS VI0 prefix112; immediate0 and different LMUL/cap. Its linked op3 helper is not executed: terminal PC supplement counts all13 op3 PCs zero. Presence of a helper in an ELF is not coverage. |

M4 predecessor runs of the two98 prefixes are VX/EI16 as well; their TIMEOUT/CANCELLED/FAIL cannot become VI31 acceptance. Frozen regression48 identity was also checked: none of its exact members is this original child or its source-derived VI31 prefix. Generic `gather_original`, `gather_prestart`, and smoke coverage does not add an authentic match. This absence statement is limited to these authoritative inventories/results, not an exhaustive search of every experiment ever performed.

## Smallest Justified Future Scope, Not Launched

If separately selected for numerical-gap coverage, prepare **one source-faithful e8/m4/op3 single at `[0,3,0,4,0,1]`**, with cap512 validated by actual capacity/vlenb. Reuse the accepted83 successor technique (`prepare_successor.py`) to narrow only empty enumerations to this exact tuple; retain the complete original seed0 xorshift generation, ordinary indices plus indices16, predicate/output setup, original13-instruction `op_3`, returned-vstart0 check, original scalar oracle, both guards, statistics and exit. Define SEW8/restart1/op-mask8 and use the original m4 assembly, not the m8 assembly or a patched opcode in an existing ELF. Existing bounded integration single runtime/checker structure is reusable, but its hardcoded VL2/start1 expectation must not be reused as this tuple's oracle. Prepare in a fresh successor; no sealed helper edit.

Full expected512-byte result is **128 prestart91 +128 active177 +256 tail91**, plus both guards91. Original VI31 source is valid against cap, not VL. Require all512 result reads, both guards,13 original helper retirements, actual VL256/start128/mask all-on, full original setup, returned vstart0 and exit0/no error markers; an active-only comparison would miss the archived prestart corruption. A single has no65-call predecessor history and cannot prove a prefix or historical stall.

For bounded history coverage instead, the non-arbitrary alternative is this child's **first66 natural calls**, ending at the recovered returned tuple, with65 predecessors, **33792 fullcap results +132 guards**, and13 helper instructions66 times. This boundary is justified by the recovered returned call, not a guess about the unknown stall. Reuse the original-loop prefix insertion pattern from `e8_m8_ops3_prefix66_prepare01` with original m4 source/assembly and fresh cap512 model/checker; its current CAP1024/model/m8 vector-group code cannot be copied unchanged. `prepare_stall_prefix2.py` supplies the existing cap512 setup pattern but is fixed to98 and VX/EI16, so is a template, not a ready executable for this proposal.

No new runtime is measured. The existing300s single ceiling is only a proposed bounded attempt, not a predicted PASS time. If history is required, retain an explicit fixed budget reviewed against preparation costs; existing cap51298-prefix measurements are3046.56/3257.15s under9000s/case. They are order-of-magnitude evidence, not a VI31 timing guarantee or a reason to extend any timeout. No preparation or launch occurs here.

## Why the Unknown Stall Remains Open

The recovered DETAIL is after a returned helper, not an accepted marker for the terminal instruction. Neither original helper PC nor no-retirement snapshots locate a unique call. Missing GPR/current VL/vstart CSR/VRF/stack/call phase and acceptance identity remain missing. Even a future PASS of this single or first66 prefix could close only its explicit numerical scope on that image, not recovery168's stopped tuple, original Linux/predecessor context, full2688 child, full parent, or any of the11 historical stalls. The stopped tuple is still UNKNOWN; no new prefix is represented as its reproduction.

## Evidence Bindings

Fresh SHA256 of the existing files read in this review:

| Path (G-relative unless C-prefixed) | SHA256 |
| --- | --- |
| `gather_unknown_stall_recovery01.md` | 405c91647f44c076d751fa66cfa621f06c5995d24a3459176910cb87331bff70 |
| `inventory83.json` | b34521033bd677554c3c119fa4a57f2103ffd138fefac308ec9ca60fc38f1c93 |
| `lineage83.json` | 558e899c74922db64d20b775f7d03d179d105d8abd3544d1aba1e2adcb9fa8bc |
| `remainder75_01/coverage83.json` | 95358f6806c6f3f689c244ad7fcf0e9d9873d395a183f752e4fa41388ac964d4 |
| `acceptance_audit01/audit.json` | 9d0872258bc9737cd7bf8025d8f2d13a185a1585dc6970f758dfca98211064e6 |
| `remainder75_01/vcs_candidate04_01/complete.json` | 9b71c95ad9df4e32beb84d88407c40ff5368bfb311bdfa6ae4897de7afd551f6 |
| `gather_repair05/m5_successor01/prefix_terminal_audit01/audit.json` | e368d848ba691608b3349af5b7af73bd51c135b475dc756e5c04766ac43e23f8 |
| `e16_m8_ops1_prefix98_terminal_audit01/audit.json` | d22348024e99b1eb881192472128e8149ffe3b63041a7fe57aa25843b1d043f7 |
| `e16_m8_ops20_prefix98_terminal_audit01/audit.json` | 60e1c45a737e1850fc93061f8c419213f90053348de29e65be2b0f63796dbbd3 |
| `e16_m8_ops3_prefix98_terminal_audit01/audit.json` | 0e6aba788041a16f3279f97bd36fe759e67ff4c467c1209d6224b35853c74fa2 |
| `e8_m8_ops1_prefix66_terminal_audit01/audit.json` | 7840992136756479dd019a95eab8534a05d99ecb07998e83fa6c698f2eb4a6ee |
| `e8_m8_ops3_prefix66_terminal_audit01/audit.json` | 459a253763c1227d07efe65594a11d5e527b66f9f5c50a34c10c216519bfa8d4 |
| `e8_m8_ops3_prefix66_prepare01/host_expected.json` | 4e98477c5756e709a0e47a7cf0af4269692f445a1761961bcb7ef2e524a37b74 |
| `e8_m8_ops2_prefix112_vcs_m6_plan01/prepared01/complete.json` | 8826d619f64bf62524f64442f07c4eabc706738b019fdf4b1057c10122b990e3 |
| `extra_helper_terminal_gate01/terminal01/report.json` | 5049683b14ab80e04c739d2f0a167f7cc99defca4b0371969e13dcea718a80f2 |
| `C/rvv_permute_partitions01/manifest.json` | 6e6c083670aaf312e9eeb252e576ec88cd5fe3a94b415c3f619c2bb9e7c43e58 |
| `C/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c` | b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca |
| `C/rvv_permute_partitions01/rvv_permute_restart_e8_m4_ops3/operations.S` | 118a8c9572532a2b332749165cff3cea9323a49722641dcf64b14fd501ccd774 |
| `C/rvv_permute_partitions01/rvv_permute_restart_e8_m4_ops3/operations.h` | 886bbcff73cda9d52dd3ab7d152aa319d900959bffaf02de0345d9292a5e5cd4 |

Original UART/report/snapshot hashes remain bound by the prior recovery note; their conclusions are not expanded into target acceptance here. Accepted83 and all prior terminal records retain their original identities and scope.
