# Remaining Historical Scope Reconciliation

2026-10-14. Static documentation/identity reconciliation only. No DUT, Spike,
Host tests, builds, live-process queries, RTL edits, or accepted large-trace
parsing. Existing terminal audits are cited, not independently replayed here.
Only this report is new. Paths below are relative to current_board_review;
C denotes /home/wangwy/fpga_runs/ara_hw_campaign_20261007_01.

## Decision

| Priority scope | Still missing | Existing PASS must not be substituted |
| --- | --- | --- |
| Gather11 historical stalls | Exact unreturned ordinal/context for all11; then accepted-request/owner evidence | 83 numerical singles and accepted natural prefixes |
| Three Linux CSR waits | Actual task/PTE/frame and accepted CSR/PE/flush timeline | Full16 source-derived zero-stride Sv39 programs |
| NF8 extra41 | Per-check attribution of original169 versus same-ELF128 errors, Linux signal/context/history | Full192 geometries accepted on M4 |
| RVV-02 full arithmetic22 | Remaining17 complete original shapes,82845 call positions | Accepted5 full shapes,262-call prefixes, integration38, fixed777 or MACC482 |

These are evidence gaps, not four newly proved current-RTL defects. The
original871 failed/198 stalled/47 mixed/124 unexecuted records are not counts
of independent bugs. RVV-01/02 are supplemental to those inventories.

## Gather11: Historical Trigger Still Unknown

Authority: [exact mapping](gather_original_review/gather_exact_trigger_mapping20261014.md).
Canonical ELF root is C/rvv_permute_partitions01/release/binaries/;
each name below has prefix rvv_permute_restart_. Original reports/serial are
C/rvv_recovery08_R/terminal_scene/. Exact per-file identities are in
gather_original_review/gather_stall_exact_trigger_review01/evidence.json.

| Recovery R | ELF suffix |
| --- | --- |
| 154,155,168,169 | e8_m4_ops1, e8_m4_ops2, e8_m4_ops3, e8_m4_ops20 |
| 171,172,173 | e8_m8_ops1, e8_m8_ops2, e8_m8_ops3 |
| 175,176,177,178 | e16_m8_ops1, e16_m8_ops2, e16_m8_ops3, e16_m8_ops20 |

The reused mapping rechecked139 archival hashes and recovered0/11 exact
unreturned triggers. DETAIL is printed after helper return; a printed wrong
tuple, fixed helper PC or global retired counter cannot identify the stall
ordinal. RNG initializes per seed, not per call. Returned ordinal66 for most
records and49/50 for e8/m8 are not recovered stalled ordinals.

Available source: C/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c,
SHA b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca.
R168 ELF SHA a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b.
Existing r168_context_decoder01 requires authentic same-incident PC/SP/RA and
loop/argument GPRs plus actual SP..SP+31 bytes containing mode/seed/cap+1/count.
Those inputs are not in the reviewed local snapshots. External locator:
D:\fpga_runs\ara_rvv_recovery08_20261009_168, with analogous other R roots.
No external capture is asserted to exist. This line remains on HOLD awaiting
the already requested material; no arbitrary longer prefix is recommended.

## Linux CSR Three: Symbols Recovered, Runtime State Missing

Authority: [diagnostic identity](masked_translation/linux_kernel_nf8_remaining_diagnostic01.md),
[original Image symbols](masked_translation/original_image_kallsyms_recovery01/REPORT.md),
[signal availability](masked_translation/save_v_state_archive_signals01.md).
Full original names are rvv_fault_replay_strided_zero_stride_e64_mN.

| Recovery / N | Original ELF SHA256 |
| --- | --- |
| 12 / 2 | 3fc3207f555099fce31489fa5e4e93b0aa178bef89b3ad11cb30caa600babf60 |
| 41 / 4 | f9ef7eecca757fe9f006a325e73fcd814afc89ea6b615afbd20fc357846b30ec |
| 76 / 8 | 1979cc198f109b637048ec55c35f57e6ae8686910632166ccf6d5d93f5029744 |

Source fault_replay_oracle.c SHA
631da853fe5939e2a812145d23155767d4e803f3d9aa22133187d6455905588a.
Each original full16 retains unmapped0/1, load/store, masksff/aa/24/00,
VL8, stride register t3=0,12 expected faults and4 all-off cases. The source
ports already pass: m4 M6, m2/m8 M7 offline acceptance. They are not Linux waits.

All three historical head PCs are0xffffffff80013a18, now identified from the
actual original Image as save_v_state+0x180, csrr a0,vstart. Image SHA
716aef49389b25a0a3f4deac47de0bb69467a10f1057041cecd0f0621fbbf285.
The m2/m8 prior kernel traps are scalar usercopy stores; m4's prior trap is
the user masked vlse64 at0x10846. Prior trap is not proof of the current owner.
Do not repeat the obsolete claim that function-level symbolization is missing.

Six one-row75-field snapshots show no retirement/trap-count growth over
roughly5.5..5.8e8 cycles; no head-valid, CSR acceptance/response, PE-by-ID
running/done, exception-flush state, task/PTE/frame or historical ILA is present
in the searched archive. Zero external DDR outstanding does not settle these.
Original raw Image/boot blobs exist; local vmlinux is mismatched. Exact deployed
bit/LTX and runtime capture remain external-material gaps. A standalone CSR
loop or repeated Sv39 PASS cannot replace original Linux signal/context evidence.

## NF8: Extra41 Is Not41 Located Failing Tuples

Original rvv_fault_replay_segment_nf8_strided_e32_mf2 ELF SHA
c90e2ac2ab90fba392ca887842ce07c78244405ef41428f7e8f760373e658282.
Source/assembly-to-ELF linkage is identity57; original target PCs109c4/10a4e,
opcodes e9c56c07/e9c56c27. See
[NF8 scope](masked_translation/nf8_strided_review/nf8_remaining_scope_review01.md).

Recovery12:192 cases/192 signals/169 errors; same-ELF retest:192/192/128.
Both exit1. Reference Linux:192/144/0. Aggregate error counters include signal
metadata, saved prefix, return status, data/memory/guards: the difference41 is
neither numerical-only nor a set of41 missing Sv39 geometries. Assuming intact
counters, one handler entry per completed case implies signals in all48 all-off
cases; actual signal PC/check attribution is not recorded. Batch predecessors
differ between original and retest; causality remains unlocalized.

All192 source-derived geometries already pass M4 in48 four-case programs:
594288 comparisons,144 expected faults,48 no-fault all-off cases. This is not
current-M9 replay, continuous192 Linux history, PROT_NONE/siginfo/vector-frame
save/rt_sigreturn equivalence, or explanation of169 versus128.

Existing bounded Linux diagnostic, not yet execution evidence:
masked_translation/nf8_strided_review/nf8_linux_prefix13_diagnostic01/fatal_successor01/build01/nf8_linux_prefix13_diagnostic.elf,
SHA e7ce9267d6bdba32cdfe23af2f511bf50e7c0be662b19eebdf3a72438f283659.
It retains12 predecessors and trial12=(u0,load,b1,mode3,gap1,split0), mask00,
VL8, stride36; expected13 cases/12 signals/0 errors. Missing evidence is a
matching-ABI Linux execution with exact PC/frame/check output, not another
bare-metal run. This diagnostic is not itself a reduction of all extra41.

## Arithmetic22: Latest Count Is5 Full Shapes, Not4

Latest CURRENT_SCOPE plus
[e8/mf4 terminal review](arithmetic_restart_original/full_e8_mf4_m9_terminal_review01/TERMINAL_REVIEW.md)
supersede older2/22 and4/22 inventories. Accepted full source programs:
e8/mf8,e16/mf4,e32/mf2 on M6; e64/m1 on M7; e8/mf4 on M9.
Total24255 original calls. This mixed-image union is not22-shape M9 acceptance.

Remaining17 full shapes,82845 original call positions:
- e8/{mf2,m1,m2,m4,m8}:5*4095.
- e16/{mf2,m1,m2,m4,m8}:5*4095.
- e32/{m1,m2,m4,m8}:4*5985.
- e64/{m2,m4,m8}:3*5985.

Original ELF root: C/rvv_extended04/overlay/opt/ara-tests/rvv_matrix_<shape>;
assembly C/rvv_extended04/rvv_matrix_<shape>.S and per-SEW operations.h.
Exact22 identities/counts: arithmetic_restart_original/full22_remaining_inventory01/inventory.json;
its old acceptance booleans must not override newer terminals.
Original C text was lost. recovery22/reconstructed_oracle.c SHA
7483f9dfde7012f7b800314fe1765f8cee9836fbcfbdc16fc641554397884e91 rebuilds
all22 original Linux ELFs byte-identically per recovery22/report.json; it is
not a claim of recovered byte-identical C. Original rvv_trace02/ISSUES follow-up
distinguishes19 historical board passes from these three historical stalls:

| Original full shape | Original ELF SHA256 | Accepted bounded scope only |
| --- | --- | --- |
| e8/m4 | 5b77ae16b4316cb33e507d488103b9a31a12db6e371e60cec95092858f382ad8 | M4 prefix56 |
| e8/m8 | ee9874270f50735cb04da599bb477d3d9da2bbeba0e77cbec9e1eb1ea0f8310f | M4 prefix38 |
| e16/m8 | 68fc999069ab1f830f6dc4c572f1ebe851c8511b412aa355cd5e0fabe9a4ef7d | M4 prefix56 |

Five M4 prefixes total262 calls, also including e8/m2 and e16/m4. They retain
full original oracle at that scope but do not close any of these17 full shapes.
The separate fixed777/MACC482 and integration38 cannot be counted as arithmetic22.
Missing: each full ordered source-port's own full oracle/reference/cost and DUT
acceptance, then separately original Linux/board closure. Existing cap32 M9
7872.941s proves only e8/mf4 cost; it is not a <3h guarantee for larger shapes.
No new test or budget extension is proposed here.

## Other Residual Boundaries And Stale Entries

- FP alias first700 now PASS M9 (including retained call50 and681..700), not
  pending first50/682. Full17920 parent and historical cause remain unclosed.
- Whole continuous1134 now PASS M9; older twelve-hour HOLD/partition-only wording
  is superseded. Original Linux execution and366 excluded cases remain separate.
- Small-exceptions all20 now PASS M9; next14 and finaltwo are not pending.
  NF2 forty source singles, NF7 full96, negative40 and zero-stride source scopes
  already have accepted evidence; do not use their older pending text as new gaps.
- The broader85 slide/45 boundary/42 extension/9 segment-boundary stall records
  still lack blanket original-program/root-cause closure. Selected repairs,
  full fixed/MACC programs and directed extension matrices do not prove every
  inventory record. No per-record recount or new trigger recovery was attempted
  here, so no new numerical remainder for those groups is asserted.
- Accepted comparison19/scalar19/FPmove47/ordered-reduction11/Gather83 singles
  remain scoped source ports, not their full parents or original Linux ELFs.
  Mixed/unexecuted records and CAP-01 setup faults remain exclusions, not fixes.

## Read Snapshot Identity

These hashes identify documents read, not a fresh DUT pin audit. Concurrent
parent updates after this snapshot are not drift failures of running tests.

| Input | SHA256 |
| --- | --- |
| CURRENT_SCOPE.md | 822a9100c94a14615a7b73bb854ca9a14340d425383395fa6e666cc96996d75c |
| RESUME_20261014.md | 1c8c551d383444b77f179ae4b3c07007c9fb51c2117324c89c8d470244694b61 |
| Original repro/ALL_FAILURE_REVIEW.md | c72e20fc1f85d6ca670c9b182dac85bf366c141dbe79d890e57f71282a54caaf |
| Gather exact mapping | 2a209bf0fa214de483724e3cd2fcaa06ba46051902c378f50a351daee364a695 |
| Linux/NF8 diagnostic | 026f8c97e4cfd2d797f2d1148f71fa6153e26abe6c7664ba218c82e9afd7de43 |
| NF8 remaining scope | 9d029d1eaa432a8687d19c119f119663eb440833764b64895cb67eaa0d55315d |
| Arithmetic22 inventory.json | f3b835903b25743ce9de048467631d3bd3b852442049df3410533f5b687e6984 |

No root index, sealed inputs, historical results or production files changed.
