# Candidate02 NF2 Terminal Acceptance

Parent-authorized run `vcs_preflight01` completed with
`CANDIDATE02_NF2_FOUR_PASS`; observer result is `NF2_CSV_ORACLE_PASS`.
This update only reads terminal artifacts, hashes and the existing CSV. No
simulation, build, RTL/helper/ELF edit or oracle rerun was performed.
`reference01`, the initial preparation reports and preflight remain unchanged.

## Identity Recheck

Independently rehashed **664 distinct pinned files, zero mismatches**, combining
preflight pins, image files, worker review pins and all **539 frozen sources**.
The executed input ELF matches the original reference SoC ELF; the executed
image ledger matches preflight. Analysis hash matches complete.json. Console
contains exactly one `SEGMENT_SV39_PASS` and no `SEGMENT_SV39_FAIL`.

| Artifact | SHA256 |
| --- | --- |
| Accepted/executed SoC ELF | 2ddce29de6d035fb02616f7924235b03e8863a74dfad161c3b2a4219ced61a67 |
| Candidate02 image.json | 384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810 |
| Frozen snapshot.json | b185f9fd8cc4a75ce5ab5ef240fb621511affd673bbc8b43fb7a2e8d64bad8a9 |
| vcs_preflight01/complete.json | 371edac27a0ad49ae6981680f38b550a1864b91207c79f929f07d7724fcca6f3 |
| vcs_preflight01/csv_analysis.json | cf729be143e20afbc9b7be7fe37974db2ef42937463f49f2b00cd3fdc00681cd |
| vcs_preflight01/preflight.json | a7cbfc2106e7d1338be7041b4b26ca9d77a2259c75c344085e4ba34b5d0e2756 |
| vcs_preflight01/parent_review.json | 05aec0c72799cbf17384e891d45c7a9cc650e74042eaaf582e8dcf8ec84480f6 |
| run/tests/nf2_segment4/commit_trace.csv (under vcs_preflight01) | 34bb577df8b0e3d351728e767773af83ce6a7c0d2094d5432adf88e7d6606c8a |

Image path: `/home/wangwy/fpga_runs/current_board_memory_candidate02/campaign/image`.
Simulation elapsed **1590.9373 seconds**, worker including observer **1640.4592
seconds**; these are host times, not RTL performance ratios. Last recorded
cycle **1446260**, **4133** firmware checks, four cases and eight checkpoints.

## Actual Fault And Field Identities

All cases: NF2/e16m1, VL8, vtype8 (tu/mu), v24/v25, mask0x24, initial vstart0.
P=0x40001000. Active elements are 2 and 5; fields have addresses base+4*i+2*f.
All four fault records show vstart5, VL8/vtype8, fcsr117/vcsr5. The original
b3 alternate protected-field allowance was not used: actual address was P+6.

| ID / source status | Base | Fault field/address | Cause / mepc | Handler-entry cycle | Retry target retirement |
| --- | --- | --- | --- | ---: | ---: |
| 0 b3 load, archived failing single | P-14 | element5 field0, 0x40001006 | 13 / 0x800010bc | 129144 | 275411 |
| 1 b3 store, archived failing single | P-14 | element5 field0, 0x40001006 | 15 / 0x800010c4 | 443456 | 605376 |
| 2 b5 load, archived passing trial | P-22 | element5 field1, 0x40001000 | 13 / 0x800010bc | 775378 | 920117 |
| 3 b5 store, archived passing trial | P-22 | element5 field1, 0x40001000 | 15 / 0x800010c4 | 1087869 | 1249755 |

Actual target opcodes: load `20055c07`, store `20055c27`. No trapping target
retirement appears in this monitor; fault identity is established by captured
handler CSR reads and matching stored records, not an invented retirement.
For b3, inactive element3 straddles P and must not cause the early historical
fault. For b5, element5 field0=P-2 is accessible and field1=P is protected.
The DUT oracle permits field0 partial completion; this CSV alone does not expose
its vector data or prove its precise pre-fault completion cycle. Spike's
observed partial access is separately retained in REFERENCE_REPORT.md.

## Checkpoints And Retry Ordering

| ID | Fault checkpoint cycle / total checks | SFENCE / retry MRET cycles | Final checkpoint cycle / total checks | Case-local checks |
| --- | --- | --- | --- | ---: |
| 0 | 274823 / 303 | 274864 / 275280 | 418341 / 759 | 756 |
| 1 | 604816 / 1061 | 604855 / 605223 | 750314 / 1517 | 758 |
| 2 | 919661 / 1817 | 919692 / 919999 | 1062727 / 2273 | 756 |
| 3 | 1249213 / 2575 | 1249244 / 1249612 | 1394632 / 3031 | 758 |

Each observed sequence is handler -> fault checkpoint -> PTE repair ->
addressed SFENCE -> vstart5/unchanged-PC retry -> successful target -> younger
marker -> terminal ecall handler -> final checkpoint -> case completion.
Both completed element2 fields are poisoned before retry. Exact final checks
cover both fields, inactive/prestart/tail elements, v23/v26 neighbors, snapshot
and output guards, both data pages, mask source and all page-table entries.
Partial-state allowances are confined to the fault checkpoint.

Terminal ecall handler cycles: 276562, 606509, 921250, 1250888; each has cause9,
mepc0x80001168, mtval0 and vstart0, VL8/vtype8, fcsr117/vcsr5. Final common
seed/guard/CSR restoration checks complete after the last per-case checkpoint.
CSV records completion magic `0x7365677376333904` at cycle1445872 and CTRL=0
at cycle1446251; final mx_checks is 0x1025 (4133), errors/unexpected remain0.

## Acceptance Limit

This is actual candidate02 DUT acceptance of four selected original-source
Sv39 derivatives, not full Linux ELF/signal-frame/sigreturn acceptance, all40
NF2 failing singles, all429 replay records, NF7 indexed, or all segment shapes.
Original Linux identities and reconstructed adaptation boundaries remain in
`../SELECTION.md` and `reference01/linux_provenance.json`. Old preparation-only
statements describe their historical stage; they are not rewritten as DUT runs.
