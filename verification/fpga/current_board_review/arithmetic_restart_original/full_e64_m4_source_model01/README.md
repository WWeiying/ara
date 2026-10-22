# Full e64/m4 source model and dictionary

Status: FULL5985_SOURCE_MATH_MODEL_AGREE_NOT_COMPILED_NOT_SPIKE_NOT_DUT.
One authorized Python source-model construction exited0, model elapsed
2.776706758s, under120s. Actual wait is recorded in execution.json.
No C/helper execution, Host compilation, Spike, VCS, RTL edit or large
trace read. Predecessor STATIC_PLAN.md and all existing artifacts unchanged.
No external-agent independent acceptance is claimed.

## Exact model result

| Item | Actual model count |
| --- | ---: |
| Original calls / seeds / operations | 5985 / 3 / 35 |
| Integer / FP calls | 4095 / 1890 |
| CAP / physical group / vtype | 64 / 4 / 0x1a |
| Result words / guard words | 383040 / 11970 |
| Independently compared full output words | 395010 |
| Output footprint per call | 528B / 66 whole u64 words |
| Expected returned-vstart checks | 5985 |
| Full target helper instructions | 77805 (13 per call) |
| Exact unique64B dictionary blocks U | 1986 |
| Dictionary bytes / maximum index | 127104 / 1985 |
| uint16 IDs | 53865 / 107730B |
| Last block actual bytes / padding | 16 / 48 |
| FP ordered destination writes | 241920 / 1935360B |
| Additional integer mathematical corner comparisons | 931 |

Every call is reconstructed from9 IDs and compared to all528 gold bytes.
Only16 actual bytes belong to block8: result63 and the upper guard, both
full64-bit words. The48 dictionary padding bytes are zero, never licensed
as actual output reads. Sentinel/guards are uint64 0x5b, not repeated bytes.
`returned_vstart:0` in calls.json is a SOURCE EXPECTATION, not observed CSR.
No source numerical, guard, history or FP-write coverage is dropped.

## Independent source/mathematical construction

model.py contains a literal source-order loop and C-oracle translation,
plus separate mathematical output generation. The latter independently
expands all tuples without OPERATION_KINDS, uses bitwise-polynomial RNG,
restoring unsigned division with signed quotient/remainder conversion,
bit-vector logical operations, set selection, vectorized compression and
mathematical reduction. All66 words are compared for each of5985 calls.
The FP oracle is the ORIGINAL640 u64 bit table in both paths, with separate
indexing, NOT an independently simulated IEEE754 engine or host float.
This verifies table/source transcription and dictionary losslessness,
not RVV instruction execution or floating-unit correctness.

Header640 words match actual original ELF at file0x1560..0x295f; input8
words match the original code-bound file0x1520. No m2 gold/model module is
imported. All ten source/identity inputs and model.py were hashed before
and after construction. Recovered C is binary-equivalent, not original
text recovery; actual ELF remains c8e9bad5a0247cb63c9b908a316b5b0f775b242984e187d66f1aa7b3137720f6.

Seed RNG exits, independently checked with bit-level shifts:
seed0 d507014a2c3e845d; seed1 fbf3f6d5a5469323; seed2 7f84d41e6c59b1cb.
seed_inputs.json retains all64 original a/b words for each seed. No seed
inherits the previous seed's FP data. Each FP call rebuilds both arrays,
including VL0 and identical repeats. Source and mathematical paths hash
each write as LE(ordinal:u32, ordered destination:u32, value:u64), with
destinations2*i=a[i],2*i+1=b[i]. Both ledgers agree:
ad147ff8086b7c5292f86479723b0ddf17bb954a6973ed1bb0a369f6e73849ba.
calls.json records all input/output hashes, tuples,9IDs and128-write
obligation for EACH FP call. fp_ordered_periods3_u64le.bin encodes three
128-word interleaved per-seed refresh templates, not permission to skip
their1890 executions. First/last ordinals are1/5985; the final call retains
all5984 original predecessors without a partition reset or shortcut.

## ROM and source implementation proposal

Runtime ROM components:127104 dictionary +107730 indices +384 masks
+5120 FP expected table +64 FP inputs =240402B. Raw gold is3160080B and
calls.json is offline evidence, NOT a proposed linked runtime array.
Keep tuple generation as original nested loops. No per-call large struct
or JSON is placed in ROM or stack. Optional three refreshed-period data
templates3072B are diagnostic evidence only; the header uses the input8
table instead. Original globals24744 + runtime reserve16384 + code/other
readonly reserve65536 + stack65536 =172200B. Proposed envelope412602B,
leaving635974B within1MiB before actual link/alignment verification.
This is exact dictionary arithmetic plus stated reserves, not a linker map
or stack proof. Additional source implementation metadata must be counted.

fp_period_proposal.h is an UNCOMPILED source proposal. Inside each original
FP call it freshly reads8 immutable input words, dispatches seed0..2,
and emits a0,b0,...a63,b63 as128 ordered8B memcpy stores with memory
barriers. Eight explicit periods use bases0,8,...56. Permutation is
a[j]=p[j], b[j]=p[(3*j)%8], p[j]=input[(j+seed)%8]; for i=8q+j this equals
the original source indices. Both addresses stay within actual64-word
arrays; no pointer type punning/unaligned cast or widened guard store.
It intentionally changes redundant readonly table loads, NOT destination
writes. The original next-seed RNG and all other source ordering remain
outside/unchanged. No table precomputation may substitute for helper output.

Future lowering must prove128 actual SD in order on every FP call,8 fresh
table loads, no spills outside stack, no auto-RVV, no eliminated equal
store, and matching original13-instruction helper windows. The header has
not been preprocessed, compiled or executed. It makes no actual instruction
count claim. If source-level barriers cause extra address/spill instructions,
those must be charged, not hidden under a hand-written witness estimate.

## Cost proposal, not measured firmware

Actual ORIGINAL ELF FP refresh loop10488..104bc has22 instructions/element,
thus64*1890*22=2661120 for that phase alone. The proposed periodic source
removes repeated modulo/index arithmetic while retaining241920 destination
writes. A conceptual8LD +<=5dispatch +128SD +RET leaf would use<=142
instructions, but that is NOT a GCC measurement or upper bound for this
header, its caller or the full program.

check_proposal.py additionally verified the actual proposal's text-level
store order,8 period bases and all384 destinations/values across three
seed branches against both formulas and generated templates. Actual exit0;
proposal_static_check.json records the binding. This did NOT execute or
compile the header. Header SHA:
cfe2af2df0bd9a2bb9b4fbf526cd5061f568fa42f98e3819f0e1423e7fa06da8.

For a future compiled success path, separately count:
F =5985*(13 helper +66 output init +66 actual output LD +66 dictionary LD
+66 comparison branches +9 ID loads +O) +1890*P +2205*M +S.
Here O includes dictionary address calculation, all loop/outer-state and
counting overhead; P is the entire actually lowered FP refresh; M is a
full original mask-group initialization; S covers startup/RNG/capacity/exit.
This is a work decomposition, not a promise that C lowers to those minimum
components. In particular comparison/init compiler control can add work.
With the uncompiled P=142 witness, core arithmetic would be1980090 before
5985*O+2205*M+S. A3M target leaves1019910 for those extras; actual lowering
must establish the total. No new firmware estimate is called measured.

Historical accepted e64/m1 M7 proxy was4528858 instructions/7544.534203s
(~600/s), a different CAP16/image/backend. At that proxy3M means~5000s,
but no<=3h M9 guarantee follows. Existing m8 timeouts reinforce this limit.
No compile/reference/DUT admission is included here. Exact dictionary fit
is now established at model level; actual code/stack/net cost remains the
next separately authorized gate. Keep all5985 calls if it fails that gate.

## Evidence and scope limits

- generated01/result.json SHA984e9bfa457dd1178b4fe60e7b0c3e4aef7114190b4ec4439a8f554785635a43.
- model.py SHA04b39ab4fbf49c11a48532498636fb9ea0d454013610d472fbf8cc238f3e884c.
- input_pins.json SHA06cda105ceb6dfd7c3563c3d07a6602f7e2a525fcd63dd4c7975a5b8b12e4898.
- gold_u64le.bin SHAc3c9938a41a189115180b08e8e61c34220da268ee49102d3d17fcbc81be3cc31.
- dictionary64.bin SHA86c1fbe7dac7157c3943f4a538f12868f220103173c39d123bb50ba97bfa41e6.
- indices_u16le.bin SHA2c066b751c4ec632cce78622bc567277257fe6ac9fb539bc1be65b4b9b9d01ea.

Other generated hashes/lengths are in result.json. The previous static
report contains original source/helper identity and physical boundaries
v8..11/v16..19/v24..27. They remain disjoint; don't invent overlap testing.
Archive resume03 recorded this exact program board PASS. Current M9 full
regression is still uncompleted/unaccepted. This is not a newly identified
remaining RTL bug, an independent-agent review or DUT architectural PASS.
