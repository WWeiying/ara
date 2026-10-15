# NF8 Positive-Stride Outlier: Static Selection

2026-10-11. No RTL changes, compilation, Spike/VCS/Linux execution, or NF7
progress queries. `selection01.json` contains pinned evidence and all 192
original tuple geometries; `prepare_selection.py` only reads/extracts them.

## What Is Actually Known

Original `rvv_fault_replay_segment_nf8_strided_e32_mf2` is a real aggregate
failure: Recovery12 reports **192 cases / 192 signals / 169 errors**. Its
Recovery13 `previous_report.json` is the same observation, not another run.
`rvv_failure_retest01/results.json` subsequently records the **same ELF** with
192/192/**128**, exit1, 20.2369 s, run ID `69dbca9c7803589118d7625f30051734`.
Archived VLEN512 and VLEN1024 references both report 192/144/0.

**The exact inner tuple, phase, field, and got/want responsible for the extra
41 errors cannot be recovered from these aggregate logs.** Trace was disabled.
The error counter includes trap metadata, returned vstart, saved prefix, final
register data, and memory guards; 169 is not proof of 169 numerical mismatches.
Do not label any selected tuple below as the measured original failing tuple.
`ISSUES.md:458` likewise explicitly leaves those extra41 unlocated. The later
128 retest does not erase the original169 or prove identical root cause.

## Provenance

Campaign root: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.

| Artifact | SHA256 |
| --- | --- |
| additions54 ELF, reference54 ELF, identity57 rebuilt ELF, all identical | `c90e2ac2ab90fba392ca887842ce07c78244405ef41428f7e8f760373e658282` |
| reference54 archived target assembly | `63c68bc8c2c935884520082cd423c51e9f14fb7caac7a42816026b9597acb8db` |
| current `fault_replay_oracle.c`, matching identity57 source manifest | `631da853fe5939e2a812145d23155767d4e803f3d9aa22133187d6455905588a` |
| current `fault_replay.py`, matching identity57 source manifest | `47765b894cde708521c8a32ce02539e9bd140ebc1be464824252817a05755ff9` |

The original reference54 source hashes differ, but archived
`rvv_fault_identity_regression57/source_mf2_False_0_nf8_stridedTrue_reverseFalse/`
binds the current C/generator hashes to an ELF verified byte-identical to the
release. The identity ledger was checked and assembly regeneration in memory
matches the original S exactly. This is stronger than an unbound source guess;
no new rebuild was performed. All full evidence paths/hashes are in JSON.

Original ELF disassembly: load PC `0x109c4`, opcode `e9c56c07`
(`vlsseg8e32.v v24,(a0),t3,v0.t`); store PC `0x10a4e`, opcode `e9c56c27`.
Any future Sv39 fixture is a source-derived port with relocated target PCs,
not execution of this Linux ELF and not Linux signal-ABI closure.

## Exact Setup and Oracle

`fault_replay_oracle.c:199` enumerates, outermost first:
`unmapped 0/1, store 0/1, boundary 1/3/5, mode 0..3, gap 1/3, split 0/1`.
VL8, e32/mf2, tu/mu; masks ff/aa/24/00. For mapping base M:
`stride=4*(8+gap)` (36 or44); `base=M+4096-boundary*stride-16*split`;
`A(i,f)=base+i*stride+4*f`. All addresses are element-aligned and nonoverlapping.
Data fields occupy **v24..v31**, one register per fractional field, not four
packed registers. At VLEN1024 cap=16 words/field (VLEN512 cap=8).

Original memory is `37*((A-M)/4)+11`; input is `101+13*i+29*f`; old load vd is
0x5b. Expected fault element is first active i>=boundary, or8 for no fault.
Handler checks exact target PC, MAPERR/ACCERR, saved VL8/vtype23/vstart, and
si_addr equal to a protected field address of that element. Completed active
prefix and inactive prefix are checked before repair; then completed active
memory is poisoned XOR0x5b and **same PC/vstart** is resumed.

Final oracle (`:257` onward): returned vstart0, exact fault count, all cap*8
field words, all 8192 bytes of memory including stride gaps, and output guards
at indices0 and cap*8+1. Load final data is original active data, with old
inactive/tails; store source registers stay unchanged and completed-prefix
memory retains poison. Faulting-element partial fields are not required to be
atomic or to have a specific intermediate order. In particular, do not demand
all accessible fields of the faulting segment have committed at trap time.
Original manifest excludes **physical fractional tails beyond cap**; additional
whole-register guards may be explicit strengthened checks, not claimed original
coverage, and must not weaken the original cap-tail oracle.

## Current Sequencing Audit

Current AddrGen/VLDU/VSTU/segment sequencer/main sequencer hashes equal frozen
candidate02; hashes are pinned in JSON. Dispatcher differs only by the two
scalar-insert internal-vstart assignments inspected here. This is a source
comparison, not validation of the new workspace/candidate03 by an older image.

- `segment_sequencer.sv:78,105,127,213,233,239`: mf2 field register offset=f;
  nf=7; accepted f7 clears field count and advances element. Each micro-op has
  vstart=i, vl=i+1, base offset4*f, original stride retained. The original VL8
  instruction can issue 64 field micro-ops. No NF8-specific count/register
  truncation was found in this inspected path.
- `addrgen.sv:366,615,620,926`: address is `base+4*f+i*stride`; predicate
  requires matching owner and first-element window. An off field emits a skip,
  no translation/AXI, and final skip completes. Alignment is checked only for
  active masked addresses. One-word micro-op fault computes vstart `(i+1)-1=i`
  at `:1283`, not field index or i*8+f.
- `vldu.sv:438,444,489,618,641`: one field's bytes target its own vd/element;
  skip advances position without data. Exception marker is ordered behind prior
  descriptors; partial results enter the normal queue and completion waits for
  empty queue plus final VRF grants. `ara_sequencer.sv:987,1028` retains fault
  response until load completion; `segment_sequencer.sv:262,286` stops further
  fields and waits for backend idle before architectural response.
- Store counterpart `vstu.sv:454,579` suppresses W for skip and drains pending
  B before fault completion. Main sequencer `:1029` waits for store completion
  in the normal build (unless explicit `ARA_STORE_B_AB_BASELINE` is defined).

These rules address known mask/fault-completion mechanisms; they are not
measured NF8 closure. No concrete current NF8-specific defect is established.

## Minimal Discriminator, Not Launched

First run only **trial19** after a separate host/Spike reference is accepted.
Its hypothesis: a split-page NF8 fault/retry can misplace or lose a completed
field at f7-to-next-element transition, independently of the all-off fault bug.
Controls below are fixed original tuples, not arbitrary variants:

| Original 0-based trial | (unmapped,store,boundary,mode,gap,split) | Purpose |
| --- | --- | --- |
| 19 | (0,0,3,0,3,1) | Primary load; stride44, M+3948, expected vstart3 |
| 17 | (0,0,3,0,1,1) | Stride36/M+3972; same fault element and split |
| 67 | (0,1,3,0,3,1) | Store source/prefix poison and W/B side effects |
| 31 | (0,0,3,3,3,1) | All-off control: no trap, no target MMU/AR |

For trial19, faulting element3 has f0..3 at M+4080..4092 and f4..7 protected
at M+4096..4108. Oracle allows any of those four protected tvals; current
micro-op order predicts f4 first. Saved v31[2] must be **37603**, before and
after retry. Trial67's corresponding input is330 and post-handler poisoned
memory must remain273, detecting incorrect restart from element0.

Use the existing real-Sv39 fixture infrastructure with exact trap PC/cause13
or15/vstart3, PTE repair + sfence and unchanged-PC retry; preserve all original
register/prefix/memory/CSR checks. Record firsterror as tuple/phase/field/element/
address/got/want and per-phase cumulative counts. A small source-derived pass
does not localize or close the original extra41; full192 remains the eventual
coverage boundary, and Linux context/replay remains a separate system layer.

If a mismatch occurs, capture one bounded window around element2 f7 through
element3 f4 fault: segment state/count/vstart and accepted request tuple,
AddrGen owner/predicate/address/MMU response and descriptor push/pop, VLDU
issue/commit IDs, result address/BE/request/grant/final-grant, fault completion,
and architectural trap. Wrong accepted addresses distinguish sequencing from
correct addresses with wrong VRF data; correct data before trap but wrong saved
state distinguishes the context/fixture layer. No speculative RTL change or
blind rerun is justified by the aggregate169 alone.
