# Unboxed E32/MF2 Full17920: Static Source Proposal

Status: **STATIC_SOURCE_CANDIDATE_ONLY; EXECUTION_NOT_AUTHORIZED**.
One narrow successor to the accepted e16/mf4 packed approach is proposed.
No generator, model construction, Host test, compile, reference, DUT, live query,
or raw-trace read was performed. No sealed predecessor or RTL is modified.
This is the named remaining broader-FP parent, not a rerun of e8/e16 timeout
cases and not part of arithmetic22. Review entry: this file, `COST.md`,
`shape.json`, and `INPUT_BINDINGS.json`.

## Exact Original Identity

Archive root C: `/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01`.
Parent: `rvv_fp_compare_unboxed_unmasked_e32_mf2`.

| Input | Binding |
| --- | --- |
| Original ELF, C/rvv_additions46/binaries/<parent> | `1bc4201a51302e1c9f2f0f8f517cc053de49ba38ee2aa21574bf5f15fd68ca38` |
| Original hash-exact fp_compare_oracle.c | `03cc50313dee7cda6476658bbe025409617242c06cd06cdaff8d83d2812e9bad` |
| Original manifest, C/rvv_fp_comparisons_unboxed_v24_unmasked_01/manifest.json | `13a460255abd3e2349c8a6108c3ed5f2a9174dc30648d347d7e7fb3900c0a489` |
| Original <parent>.S under that manifest | `dae429dd0bb703733e89bb7756624089d1545b383d5ab18438360669dec02769` |
| Original e32/fixtures.h | `ec7f1d6b54e6f386aa006511792bfe02aba308e035501b223f7adc39e0a936eb` |
| Original e32/operations.h | `cd0e50739a57ccd54ead1092113528d6535ec62468e8fe4863dbb64fbf2fee64` |

The current canonical C at `/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/fp_compare_oracle.c`
and the retained full C in `fp_compare_unboxed_prefix265_prepare01/software/original/parent.c`
match that original manifest hash. `fp_comparison_original/provenance01/parents.json`
identifies this parent as HASH_EXACT_PRESENT with SEW32, UNBOXED1, UNMASKED1,
RESTART0, DK0. The original failure is retained in recovery08_11 terminal_scene
report and recovery08_12 previous_report; these repeat the same historical
parent output, not two new roots. The archived final line is cases17920/errors832;
the first DETAIL is op4/seed0/VL15/mode0/sticky0, expected_flags0/actual_flags16.
This is not a claim that current M9 still fails or that an e16 PASS closes it.

Static code binding: the original ELF has one exact executable match for each
source-ordered helper, contiguous from capacity `0x10532` through `0x107ea`.
There are 696 bytes / 185 instructions: capacity3, four vv17, six vf19.
Comparison with the previously bound e16 helper bytes changes only vsetvli
vtype14->23, VLE16->VLE32, and vf LHU->LWU. The source assembly has exactly those
normalized textual differences. This is an actual original-helper byte check,
not a new compilation or a claim of byte-identically rebuilding the full e32
Linux program. Any later SoC/reference binary must bind its own relocated PCs.

## Source-Derived Geometry And Ordering

- VLENB128; e32/mf2 effective64B, CAP16, vtype23 (`0x17`), physical register group1.
  Sources are v8 and v16, destination mask v24, separate mask v0. No alias-m8
  semantics or integer-matrix op set is imported.
- Exact nested order: seed32 -> op10 -> lengths7 -> mode4 -> sticky2 -> trial1.
  Lengths are 0,1,2,3,8,15,16; all starts are0. Total17920, including2560 VL0,
  7168 vv and10752 vf. Each op occurs1792 times, each vf raw seed336 times.
  No partition reset, shortened prefix, selected easy tuple, or call deduplication.
- There is no RNG in this parent. Preserve its deterministic index formulas:
  `ai=(i+seed+7*(seed/16))%16`; vv `bi=(3*i+5*seed+seed/16)%16`,
  vf `bi=seed%16`. Both a and b are refreshed on every call, including vf/VL0.
- Original typed32 arrays a[1024], b[1024] are **4096B each**. Only the first
  16 words /64B of each are rewritten per call. Each untouched4032B upper region
  remains original BSS zero, not scratch/table storage. This differs from the
  e16 parent's2048B backing and32B active input per bank.
- Mask initialization remains128B per call, despite the helper's logical VLM
  footprint being only2B. Output initialization remains all130 bytes of0x5b;
  logical result is2B at output+1, and guards are byte0 and byte3. The original
  post-result oracle does not check bytes4..129; do not add or remove that scope.

## FP32 Fixtures, Malformed Boxing, And Original Oracle

The original16 FP32 inputs, in index order, are:
`00000000,80000000,3f800000,bf800000,3f000000,40000000,40400000,33800000,`
`00000001,007fffff,00800000,7f7fffff,7f800000,ff800000,7fc12345,7f812345`.
They include both signed zeros, normal/subnormal boundaries, infinities,
index14 qNaN and index15 sNaN. Use the original six comparison/flags tables
directly. A future independent integer classifier must use exponent0x7f800000,
fraction0x007fffff and quiet bit0x00400000, not FP16 masks or host float math.
The original e32/e16 `expected[6][16][16]` literal texts are byte-identical
(SHA `88e0f3478da6a690d9329d24bfd50aefe1402fcc9ad4ee982084cd6ad4e68b09`);
their input literals are NOT interchangeable. This static fact is not a new
full-model or numerical acceptance. Regenerate from the e32 source when allowed.

Every vf helper retains `lwu t2,0(a1); fmv.d.x ft0,t2`. The loaded raw32 is
zero-extended to64, including negative-zero/negative/NaN payloads. The upper32
zero bits are invalid FP32 NaN boxing, so the consuming operation treats it as
qNaN. The source explicitly substitutes rhs index14 only for expected vf
semantics; it does not change b[] or ft0. Seeds0/16 legitimately carry raw0;
all other30 carry nonzero values. Do not sign-extend LWU, box the upper bits,
replace FMV.D.X with FMV.W.X, or hardcode all scalar payloads to zero.

For EQ/NE-vf, an active lhs sNaN raises NV; qNaN alone does not. For ordered
vf LT/LE/GT/GE, any nonempty active range raises NV because rhs is qNaN. An
invalidly boxed raw rhs sNaN is consumed as qNaN, not independently as sNaN.
VL0 adds no flags. Sticky0/1 remains ORed into flags; do not waive flags or
hardcode NV for all vf cases. At the original first failure (seed0/VL15), lhs
index15 sNaN is outside the active range, so EQ-vf expects NV0, unlike VL16.

DK0 old destination is always the **16 mask bits0x5b5b**, not a typed32 aold.
For each bit: VL0 requires old; i<VL requires original wanted; nonempty tail
allows the original set {old,1,wanted}. UNMASKED1 means mode does not predicate
the target, but all mode-specific setup and helper memory requests remain.

Precompute Z16/O16 must-zero/must-one masks and baseflags per(seed,op,VL).
For actual16 result bits, `bad=(actual&Z)|((~actual&0xffff)&O)`. This preserves
all allowed independent tail choices, not a chosen single tail pattern.
Each bad bit contributes one error. Nonzero returned low32(vstart) adds one;
wrong high32(flags) adds one; either/both wrong guards adds one combined error.
Maximum19 errors/call,340480 total fits unsigned32. Preserve original `prior`,
`errors!=prior && details++<20`, all DETAIL fields/order and per-call error delta,
final summary and exit. A scalar clear-lowest-set-bit loop is only on the error
path; it must not merge two wrong bits into one error or stop subsequent calls.
No new restore-readback claim: exact saved/restored fflags instructions remain,
but the original has no extra readback after the final restore.

## Single Proposed Scalar Implementation

Reuse the e16 packed design structurally, in this NEW directory only. Do not
edit/import-and-mutate sealed files. Make SEW-dependent parsing/packing explicit
rather than copying a second hardcoded FP16 implementation:

1. Consume this e32 manifest/source/assembly/header identity and assert CAP16,
   scalar word width4, physical group1, vtype23 and exact original defines.
2. Build immutable input periods from actual FP32 fixture indices. Pack pairs
   as `uint64_t(x0) | (uint64_t(x1)<<32)`, eight words per bank. All16 distinct
   bit patterns imply16 lhs rotations,16 stride3 rhs permutations and16 vf
   constant periods:48 distinct64B periods,3072B total. Do not reuse e16 data.
3. Preserve the mature64-bit record layout: Z16/O16/baseflags8/VL8/Arow8/Brow8;
   32*10*7=2240 records,17920B. A record may be hoisted within only its eight
   mode/sticky variants because it is immutable. No source, result, flag,
   owner, or call acceptance may be cached across helpers.
4. Per call perform16 mask SD; eight unrolled pairs of input LD->SD for A/B
   at offsets0,8,...,56;16 output SD plus exact SH at128. This is49 fresh stores
   and an expected16 input-period LD. Verify actual lowering later; neither
   repeated values nor VL0/mode3 permits eliminating a required fresh write.
5. Call the original helper with original arguments/order, then one aligned
   output LWU covering byte0/bytes1..2/byte3. Original packed error arithmetic
   and reporting remain unchanged except the printed SEW and function name.

Use aligned8 declarations and mature scalar memcpy/asm primitives, not casts
of uint32 arrays to uint64 pointers or of output+1 to a wide pointer. Unsigned
casts occur before32-bit packing shifts; no shift by64, sign extension, OOB
tail load/store or strict-aliasing violation. Grouping two original word writes
into one scalar SD changes scalar implementation, not helper identity: both
private disjoint arrays are fully initialized before any helper, with no
concurrent reader in the original source. Keep A/B group order and full fresh
coverage explicit. Loading/storing one A/B word pair at a time avoids keeping
all sixteen ROM values live, but does not guarantee compiler spill behavior.

This stage supplies no runnable generator or candidate-C artifacts. The profile
in `shape.json` is static configuration; future source implementation and
generation require the next parent authorization after Tesla review.

## Future Evidence Contracts, Not Tests Run Now

The full oracle is17920 calls/flags/vstarts,286720 result bits,35840 guards,
326144 dynamic original helper instructions plus capacity3. All input/store
widths, full backing zeros, mask/output init, per-call argument/lifecycle and
exact helper PCs must be derived from new linked binaries. Five helper memory
owners per call remain89600;15360 nonempty targets plus2560 VL0 qualifications
remain distinct. Generic unrelated token matching must not be weakened.

The frozen M9 committed-FPR chain from the accepted e16 review is reusable as
a wire contract, not as e32 execution evidence. This static pass rehashed its
14 source pins, snapshot and image.json, all unchanged. For each future e32
FMV.D.X, require actual relocated helper PC/opcode `f2038053`, valid retire,
trap0, rd0 and full64 rd_wdata equal zero-extended original b[0]. Independently
check the preceding **LWU/t2** address/data and current seed. Opcode selects
the FPR bank; GPR x0 must remain zero and must not absorb this writeback.
This is committed FPR writeback, not physical FPR readback or a direct sampled
accelerator scalar operand. A numeric qNaN PASS alone cannot distinguish raw0
from other invalid boxes. Future negatives must include nonzero->zero,
sign-extension/boxing, wrong seed/current PC, and missing same-value setup.

After source review, the next parent-approved stage should establish original-C
full numerical/allowed-tail/error-count equivalence and bounded short negatives,
then actual fixed GCC helper/ABI/map/CFG evidence. If its complete cost exceeds
3M, HOLD without a second flags/candidate trial. No reference or <=3h DUT
admission follows from this static plan, and no original Linux closure is claimed.
