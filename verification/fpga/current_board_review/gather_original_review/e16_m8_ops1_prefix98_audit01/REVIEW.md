# Independent e16/m8/op1 Prefix98 Preparation Audit

Date: 2026-10-11. Reviewed sibling directory
`e16_m8_ops1_prefix98_prepare01` without changing its files. Only this independent
report was added. No compilation, Host/Spike re-execution, DUT launch, or RTL edit.
Existing evidence was rehashed and parsed read-only; no checker main or preparation
main was invoked. This is separate from Tesla's ongoing preparation final audit.

## Decision

**No preparation/source/reference blocker to bounded DUT admission.** Admit only
the pinned natural first98-call program, subject to the parent's separate image,
resource, timeout and terminal-checker gates. This review does not approve a new
launch plan or certify DUT behavior.

The historical archive records the stalled `vrgather.vx` instruction but no trial
tuple. Trial98 below is a source-order prediction verified in Spike, not a proven
historical failing tuple. This is neither full2688-child nor parent-matrix/Linux
closure; whole original Linux ELF rebuild equivalence remains unproven.

## Source And Binary Identity

The shared original C is
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_gather02/rvv_small_gather_restart_e16_m1_ops0/original.c`.
Its directory name is not the selected operation: the pinned partition's
`operations.S`, `operations.h`, and SEW16/restart/op-mask2 build definitions select
the actual e16/m8/op1 child.

Original child:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_permute_partitions01/release/binaries/rvv_permute_restart_e16_m8_ops1`.
Archived scene/report:
`/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_recovery08_175/terminal_scene/`.
The copied ELF, release ELF and scene ELF identities agree. The pinned triage
record has `last_trial=null`, last PC `0x105ee`, opcode `308e4c57`, head PC
`0x105f2`, and confidence `opcode_family_candidate_no_trial`.

| Identity | SHA256 |
| --- | --- |
| Original shared C | `b6e5fa032dfdc58ec621d0377f93cf824f27ad460d6bd102e173e244a65ec5ca` |
| Archived Linux child ELF | `25c6f4e22b01d0d1457c18e289cca6fe7cd3e85113175a3c9e5c82e3d56c3d2a` |
| SoC ELF, `soc01/gather_prefix_e16_m8_ops1.elf` | `161f41852ebbe6d7d9a0574691c39435dec3229b1017b20462e6211fb82fe74d` |
| Spike ELF, `spike01/gather_prefix_e16_m8_ops1.elf` | `1c31dadb8218af116137ddcc463c8af3fa76c84528c6a356aa50fe0fa7c92f56` |
| Baseline pins JSON | `c2e963b61f8ae135725a20ef61867550cd55728def9a8f5275ffb52d4a68cc96` |
| Source/ELF proof JSON | `76b19b33499bceef0251adf3ebc7b08a482dfb52d33b7336e854b432e075abcf` |
| Expected Host model JSON | `88373f4ec057cc31680e5cc309e303220993d5086f4e36337f61e2c1cb0610c9` |
| Host gate JSON | `752cf2b2f2cc053379d761ccf292d1c01c546b5e052afc9d3d6e307a6f5e7aa5` |
| Spike reference JSON | `58aed0171fe300be629e6d61b4d4cb61729a0b20b6add35a7d22c049fdbdfd15` |
| Raw Spike commits | `3774dc8654b7e169ac370f063497a4b2aa291ee92aa26baf92b802d4b2420dd5` |
| Preparation completion JSON | `a1195e24c11f1a0d5457fd47d5a3ee371dd0a49049fa972d00c37c4ce3e5504f` |

All23 baseline pins and all9 prepared-provenance file hashes matched. Both ELF
hashes, reference linkage, all8 host log hashes, and raw commit hash matched.
The 13-instruction archived helper window was independently redisassembled and
matched against both port helpers, not merely accepted from the proof JSON.
SoC/Spike case-C object files are byte-identical (SHA256
`35b7dbebb84bf825f6c5b01a24163b4f20ba49fd3fb595613cfcbd0163982dee`);
their assembly objects are also byte-identical (SHA256
`fd1cb88a6b1ea37afa09c4201f2b85dd1d30cbb6d1d050028d66c1d5851efde4`).
Runtime/link differences explain distinct SoC and Spike ELFs; Spike did not run
the SoC ELF itself.

## Natural Prefix And Oracle

Reconstructed the actual source diffs and matched both recorded diff files.
Adapter changes replace Linux output/exit/startup plumbing and omit TIOCOUTQ;
they do not change the math or scalar oracle. Prefix changes add an exit only
after the 98th completed helper, full output loop, guard checks and case increment,
plus an exact98 count check and explicitly prefix-named terminal marker.

The RNG seed `0xe736815b449aec21`, 64-bit xorshift order (13,7,17), 512 input/index
initializations, nested loop order, predicate construction, old-vd initialization,
and scalar oracle are retained. There is no skipped vector predecessor or direct
jump to trial98. The preceding97 helpers and their scalar checks execute. Disabled
op0 iterations contain no helper call/RNG advancement; they are not additional
vector predecessors. The prefix remains in seed0/scalar0.

Every call loads fullcap512 input, indices and old-vd, then the mask, sets the
selected VL, writes vstart, executes the original masked gather, reads vstart,
restores fullcap VL, and stores all512 outputs. All13 helper encodings match the
archive. Target is `vrgather.vx v24,v8,t3,v0.t`, encoding `308e4c57`: archived PC
`0x105ee`, SoC PC `0x80000708`, Spike PC `0x80000754`. Policy remains e16/m8/tu/mu.

Trial98 tuple is `[seed,op,scalar_index,length_index,mode,trial] = [0,1,0,6,0,1]`:
VL512, vstart256, scalar0, mode0/all predicate bits enabled. Expected output0..255
is91; output256..511 is input0=61881 (`0xf1b9`); both external guards are91 and
returned vstart is0. Trial97 is the same full-VL/mask/scalar case with start1.

The original C checks each of512 elements without relaxing prestart, masked-off,
or tail values, and checks both guards plus returned vstart. CSR scope is the
original vstart check, supplemented by reference vset/VL observations; this is not
a claim of new fflags/vxsat coverage.

## Host And Raw Spike Evidence

The existing Host gate records one positive exit0 and seven injected negatives
exit1: active, prestart, masked-off, tail, guard0, guard1, CSR. Their raw logs and
hashes agree, each reports98 calls, and all injected errors produce FAIL rather
than a success marker. No Host executable was rerun in this audit.

Nonblocking limitation: the prestart and tail negatives both corrupt element0 in
the first VL0/start1 call, producing identical logs. They test rejection at the
intersection of those regions, not independent nonempty-body boundary scenarios.
This does not reduce the real program's full-capacity oracle or the raw checks.

Re-executed only the pure read-only `audit_trace` parser on retained commits and
compared every returned field with `reference/reference.json`: exact agreement.
Additionally used an independent raw vector/CSR parser, rather than relying solely
on the existing scalar-load checker, to verify all98 register setups and results.

| Actual reference observation | Count/result |
| --- | --- |
| Calls and target retirements | 98 |
| Retirements for each of13 original helper instructions | 98 each, 1274 total |
| Per-call initialized source/index/index16/predicate/output values checked by existing parser | 2178 |
| Independent target input, index, predicate low512 bits and full old-vd register checks | 98 |
| Independent full512-element result-register checks and full512-element vector-store checks | 98 each |
| Actual fullcap/target/fullcap vset return and VL-CSR checks | 98 each, 294 total |
| Returned vstart zero | 98 |
| Scalar output checks | 50,176 |
| Scalar guard checks | 196 |
| Total scalar output/guard loads | 50,372 |
| Active VL distribution | 0/1/2/3/256/511:16 each; 512:2 |
| Firmware retirements through successful HTIF store | 2,002,820 |
| Last gather retirement | 1,991,033 |
| Reference process / firmware exit | recorded returncode0 / observed HTIF value1 |
| Recorded Spike execution time / raw commit bytes | 3.327266 seconds / 129,703,748 bytes |

The independent parser checks actual target-entry vstart and mask/register data,
updates vector state from raw retirements, and checks both result vectors and
stored values against the source-derived independent model. Prefix and tail
preservation are not inferred from PASS text alone. Unused upper mask bits are
not required to preserve values after the architectural mask load.

Reference ISA is `rv64gcv_zvl1024b`, using the pinned restart-capable Spike SHA256
`c03c5a84f2313b2e0bb28be7aba496836b8d7b29e472c918457bca21f8abc7d2`.
The 5,000,000-instruction/120-second/768MiB log limits were not exhausted. The
2.003M retirement count is an instruction-cost input for DUT budgeting, not a
measured DUT duration.

Reconstructed console has exactly the expected case begin, prefix PASS98/errors0,
case PASS and BOARD_REPLAY_PASS markers. The parser rejects FAIL/TRAP/MISMATCH/
DETAIL and rejects incomplete call, helper, oracle, CSR or HTIF-exit evidence.
Future DUT acceptance must enforce those same scopes rather than treating a
runner exit or generic board marker as sufficient.

**Final status: preparation/reference audit accepted, no blocking finding.
DUT not run by this audit; historical stopped tuple unknown; full child and Linux
acceptance explicitly remain open.**
