# RVV-04: Next Exact Failure Scopes

Read-only selection, not preparation or execution. Recommend at most two archived
singles: **e8/scenario0 first**, then **e64/scenario5**. Both have measured board
failures and intact source/ELF identities; neither is an invented parameter tuple.
No currently failing M6 root cause is established. Existing fixes plausibly cover
both, but the exact source/width scenarios lack architectural acceptance.

## Paths and Original Eight Records

`G = /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review`

`C = /home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`

`S = C/rvv_small_exceptions01`; `E = C/rvv_exception_symptoms02`.

`CURRENT_SCOPE.md` RVV-04 and the original `ALL_FAILURE_REVIEW.md` count **eight
ELF records**, not eight scenarios or eight independent roots: four original
programs and four detail programs. Each executes 16 rounds x six scenarios.
`E/original_report.json` records exit1, cases96, expected_sigsegv16, errors80 for
each. Detail outputs attribute 16 unexpected signals each to scenarios0/1/2/3/5;
scenario4 has zero unexpected signals and is an intentional first-element fault.

All eight actual ELF hashes below were rechecked against report input identities.
Their common directory is `C/rvv_recovery08_202/resume/binaries/`.

| ELF basename | SHA-256 |
| --- | --- |
| rvv_exceptions_e8 | 72c515419c18aa875b5ff55c03151bab9b58c1ec6ed8d50db58beea07260237f |
| rvv_exceptions_detail_e8 | 089535a7a846b2f44ae370bff43cc9a1467984f58e74b9932c564f2395eaf67c |
| rvv_exceptions_e16 | 330b561011310b5f62e51af0ff61f0b88abf0fc976194f05ec49d1136a9a04c3 |
| rvv_exceptions_detail_e16 | d7f8507da5afaf4c4683bb5b35861f6f99cd71bcbf06f6622a791d9786c55923 |
| rvv_exceptions_e32 | b251d575cde5c3c349f2c123fd5f7548a064f02429d835654d9f507c9b7ce90a |
| rvv_exceptions_detail_e32 | cca475b5d09f5edef71240702336f5087072ef0c11cca70cf749e165e6b49421 |
| rvv_exceptions_e64 | 929f8754e4c45976e00e99bb37ddf8ebd0bdb06ab7a318093a3d42bef42932cf |
| rvv_exceptions_detail_e64 | b499484a88001e0e2fac94934f23dc33c56161b1689c23913918656370b36e73 |

Keep source generations distinct. `rvv_exceptions01/manifest.json` names original
C hash `189e96e0060dfeacd5d116e6d11d9062277f4b4e1e3935587038b1af34a6439c`.
`rvv_exception_detail01/manifest.json` names detail C hash
`af36b5d8475b2949e09957ad742bbb863d0b5a59c5cf9cd959edc2dc6bc86794`, matching
the current archive-side `hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/exception_oracle.c`
under `/home/wangwy/openproject/ara_dsa`. They are NOT asserted text-identical.
The selected reduced C files differ from that verified detail C only in the
one-round/one-scenario loop limits; their assembly is byte-identical to the
corresponding `rvv_exception_detail01/rvv_exceptions_detail_e{8,64}.S` files.
The reducer's recorded original rebuild identity is not a new rebuild here.

## Actual Coverage, Not Inherited PASS

| Source scenario | Required behavior | Accepted source-derived H/I coverage |
| --- | --- | --- |
| 0 | FOF across page boundary, maskff; shorten VL8 to4 without trap | I e16 `fof_shorten`, M2 |
| 1 | Ordinary load across boundary, mask0f; VL8, masked suffix intact | No exact H/I scenario1 member |
| 2 | FOF across boundary, mask0f; VL8, masked suffix intact | I e16 `fof_masked_suffix`, M2 |
| 3 | Ordinary load at protected-page base, mask0; no trap/change | H e16 `alloff_fault`, M2, plus separately identified active/valid controls |
| 4 | FOF first active element inaccessible; expected signal | Historical positive control, not one of the five failing scenarios; no archived single4 in S |
| 5 | FOF at protected-page base, mask0; VL8/no trap/no change | No exact H/I scenario5 member |

`S/manifest.json` and `E/symptoms.json` identify 20 reduced failed singles:
SEW8/16/32/64 x scenarios0/1/2/3/5. H/I provide three matching e16 semantic
source scopes, not all20, and not their original Linux executions. No exact
e8/e32/e64 counterpart appears in H/I. Do not rerun the accepted e16 scenarios
merely to obtain another PASS.

H's actual M2 `campaign/sv39/summary.json` is summarized in
`masked_translation/COMBINED02_ACCEPTANCE.md`: three cases,709 checks each,
331.95/331.84/294.37 seconds. I's actual
`masked_translation/sv39_extended/candidate02_extended8_02/complete.json` is
`CANDIDATE02_EXTENDED8_PASS`, child0,1251.499 seconds,6227 checks. Its two FOF
members are explicitly tied to e16/scenario0 and e16/scenario2 in
`sv39_extended/vcs_plan01/ORIGINAL_EXCERPTS.md`. Other I members are unit/stride
derivatives, not additional RVV-04 scenario identities.

M6 `gather_repair05/m6_regression48_terminal_audit01/audit.json` accepts exactly
38 arithmetic programs plus10 smokes; the actual member list contains no H/I
Sv39 or FOF program. Pinning old extended8 evidence as a prerequisite is not an
M6 replay. Current M6 NF2/NF7/indexed/negative-stride acceptance is distinct
source coverage and must not be relabeled as these protected-page FOF singles.
The AddrGen local all-off FOF controls in `masked_translation/successor/README.md`
also are not architectural source-program acceptance.

## 1. e8/scenario0: Four-Byte FOF Prefix

Source directory: `S/rvv_small_exceptions_e8_scenario0/`.
ELF: `S/binaries/rvv_small_exceptions_e8_scenario0`.

| Input | SHA-256 |
| --- | --- |
| ELF | 24f4844318a01f821681aa568aee42c1560b0f1705218dca0efa44eed34c9cbe |
| scenario.c | 9883b8afe63695b104ca0915da15f565885b99310803fefcb1baef24e67cc07b |
| scenario.S | d99047d4adb47d622c32a675ab485cd1f5c4cccd2e805f5b419056b25ab0d715 |

Exact tuple: SEW8/m1/tu/mu, round0/scenario0, VL8, fresh vstart0,
base P-4, mask[0]=255 and other15 bytes0. The first four readable bytes are
11,48,85,122. Original helper `load_1` has11 instructions, including the target
`01050c07` (`vle8ff.v v24,(a0),v0.t`), immediate VL/vstart reads, and VL8 restore
before the original output store. Capacity helper has3 instructions. Preserve
the unused ordinary helper, initialization of all130 output bytes to0x5b,
16-byte mask, two-page setup and the complete source oracle.

Measured failure: `E/sampled_report.json` exit1,0.639674 seconds;
`E/symptoms.json` confirms PC0x10498, cause13/SIGSEGV11, base0x3f8825fffc,
tval0x3f88260000 (base+4), opcode01050c07. The corresponding detail parent
matches the opcode/cause/boundary and reports16 unexpected signals for scenario0.
The reduced result is `cases=1 expected_sigsegv=0 errors=1`.

Full original oracle: no page-fault signal, returned VL4/vstart0; out[1..4]
equal11/48/85/122; out[0] and out[9] remain0x5b. **Out[5..8] is explicitly
excluded after fault shortening; do not demand old-vd there.** All130 initial
output bytes, original mask/source setup and the VL8 output-store instruction
remain present. Optional extra storage/page/neighbor checks must be labeled
supplemental and cannot tighten that permitted four-element result region.

Why useful: I tested the e16 eight-byte prefix, not this e8 four-byte prefix.
At four lanes, only four valid bytes have accumulated before the FOF marker.
This distinguishes partial-word byte enables/FIFO drain from merely suppressing
the architectural exception. Hypothesis to falsify, not a measured current bug:
correct shortening metadata but premature response or wrong partial writeback
could lose this smaller prefix.

Discriminating signals: target VID/PC; AddrGen remaining byte len and
`addrgen_exception_vstart_o=4`, `addrgen_fof_exception_o`; ordered exception
descriptor after four active elements; VLDU `vrf_word_byte_cnt_q`,
`result_queue_cnt_q`, per-lane BE, accepted/final grants, exception state;
same-VID `vinsn_done`, sequencer `memory_load_completed_d`, response exception/
FOF fields, dispatcher VL update, and first following CSR retirement.
Expected architectural page-fault trap count is0, even though an internal MMU
fault and terminating descriptor occur. Scalar prefix reads distinguish bad
data from wrong trap/shortening/completion metadata.

## 2. e64/scenario5: All-Off FOF at First Protected Address

Source directory: `S/rvv_small_exceptions_e64_scenario5/`.
ELF: `S/binaries/rvv_small_exceptions_e64_scenario5`.

| Input | SHA-256 |
| --- | --- |
| ELF | a688dbfe9f1887fa028764d2e7decbdcfb3fd55460aa1e572b89f88b1c85a316 |
| scenario.c | 3fd4798e476ad168f5795d13ff3c770e00ff555616f603a5ef5c6b51fcbfac4b |
| scenario.S | 79ac02eb05e4dcbb0788c8d65f912168c85416256f84309c82c63f2f5e958c04 |

Exact tuple: SEW64/m1/tu/mu, round0/scenario5, VL8, fresh vstart0, base P,
all16 mask bytes0. Preserve the four preceding-page initialized words even
though this target cannot read them. `load_1` is the original11-instruction
sequence, target `01057c07`; old-vd is the uint64 value0x5b, not repeated bytes.
At VLEN1024 capacity is16, still satisfying the original8..128 capacity guard.

Measured failure: sampled exit1,0.419404 seconds; confirmed target PC0x10472,
cause13/SIGSEGV11, base=tval=0x3fb27ca000 (offset0). The detail parent reports16
unexpected signals for scenario5; the single reports cases1/expected_sigsegv0/
errors1. This is not the intentional scenario4 first-active-element fault.

Full original oracle: no target trap, returned VL8/vstart0, out[1..8] all0x5b,
out[0]/out[9] guards0x5b; initialize all130 uint64 outputs, all16 mask bytes,
capacity and both helpers as in the source. No retry or page repair is expected.

Why useful: H is ordinary e16 all-off, I's FOF suffix has four active elements.
This is first-address all-off FOF with a 64-byte logical span, crossing two
32-byte lane mask-data words on M6 (four e64 elements per word). It discriminates
owner/word-position progression and FOF classification without inventing a new
case. Hypothesis: a stale/incorrect predicate at the second word could translate
an inactive address; expected behavior is eight consumed skip descriptors,
zero target MMU requests/AXI reads, no exception/FOF-shortening, and normal done.
Count handshakes, not valid cycles, and distinguish earlier destination/mask
preparation loads from the target. BE0 VRF traffic is not an architectural write.
Probe `ldu_mask_owner_id_i`, word-valid/first-element, element_number,
`idx_predicate_valid/active`, skip queue push/pop, MMU request, VLDU mask release,
remaining bytes, same-VID done and returned VL/vstart.

## Current RTL and Bounded Cost

Read-only comparison found live AddrGen/VLDU/sequencer/dispatcher byte-identical
to M6 frozen versions. Relevant current paths already implement the repairs:
`addrgen.sv:604` owner/word-qualified predicate, `:924` inactive skip before
translation, `:1251` fault marker and `:1275` nonfirst FOF metadata;
`vldu.sv:624` partial FIFO accounting and `:641` final-grant drain;
`ara_sequencer.sv:989,1028` correct-VID fault-load completion barrier;
`ara_dispatcher.sv:4374` suppresses architectural FOF trap and updates VL.
The stale AddrGen TODO is not proof that predicate suppression is still absent.
Do not edit RTL from these hypotheses; source-port evidence must first fail.

Both selected archived singles already reproduce independently without preceding
target calls; no guessed warmup or truncated unknown stall is involved. A future
port should reuse real Sv39 S-mode plus independent scalar observation, preserving
the original helper/setup/oracle. Linux clone/wait/signal and PROT_NONE PTE encoding
remain explicitly outside that port's acceptance; do not load the Linux ELF as
bare-metal or claim all96 parent calls passed.

Cost evidence: H's related one-case reference is about275k commit records and
M2 runs294..332 s; I's eight-case reference780454 records and M2 child1251.499 s.
The accepted M6 negative-stride single used836971 reference firmware records and
996.680 s DUT time, with substantially more fault/refill and full-memory checks.
Static expected one-case envelope with comparable observation is roughly
0.3..1.0M firmware instructions, not yet measured for these unbuilt ports.
At the previously used slow273 retired/s proxy plus20%, this is22..74 minutes;
even a future **1.5M instruction preparation admission ceiling** estimates110
minutes, below3h. This is a conditional planning ceiling, not a proved compiler
bound or timeout authorization. Actual compiled-loop/reference cost must be
checked before any future launch; no oracle may be removed to meet it.

## Evidence Binding

Rehashed source/report metadata used here:

| Artifact | SHA-256 |
| --- | --- |
| S/manifest.json | c6d7c465085cf029c57136a7b09e79d3c232e3db2582dcfba3b2f4254b60b26c |
| E/original_report.json | e788df451d0c97a9475fe1808a4685fcf1634cb0f387c9941c8a40a564b48163 |
| E/sampled_report.json | b0fd608dba2971b3ba65cb294b5e8754bd7add1f71b7cf69fc79d595197f39d0 |
| E/symptoms.json | 8d6d083b90db358d2de7b21537ff8c5f79c998da258da840357a4ea73059248d |

No compilation, reference, DUT, live simulation query, new build, archive edit,
shared-document edit or RTL change was performed. Only this selection note is new.
