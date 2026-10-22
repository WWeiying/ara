# E32/MF2 Full17920: Static Cost And Capacity

Status: **FEASIBLE_CANDIDATE_WITH_NARROW_UNPROVEN_MARGIN**. No current linked
binary, generated full model, Host numerical result, or reference measurement
exists for this successor. Counts below derive algebraically from original
source geometry; instruction estimates reuse only explicitly identified e16
evidence. No runtime budget is enlarged or execution authorized here.

## Full Memory Obligations

| Item | Per call | Full17920 |
| --- | ---: | ---: |
| A fresh active input |64B /8 SD /8 ROM LD|1,146,880B /143,360 SD /143,360 LD|
| B fresh active input |64B /8 SD /8 ROM LD|1,146,880B /143,360 SD /143,360 LD|
| Mask initialization |128B /16 SD|2,293,760B /286,720 SD|
| Output initialization |130B /16 SD + SH|2,329,600B /286,720 SD +17,920 SH|
| All fresh stores |386B /49 stores|6,917,120B /878,080 stores|
| Actual result + combined guards read |4B /LWU|71,680B /17,920 LWU|
| Logical vector A/B loads |64B each|2,293,760B combined|
| Logical old-vd/mask VLM |2B each|71,680B combined|
| Logical VSM result |2B|35,840B|

Each a/b backing remains4096B, of which4032B is untouched above the64B hot
prefix. Combined upper BSS is8064B; it must remain zero, not be initialized
per call or reused. Core original BSS is8192+128+130=8450B before alignment,
runtime buffers and metadata. Relative to e16, a/b BSS grows4096B, requiring
512 additional8-byte BSS stores in the existing startup loop. At its actual
four-instruction loop body, this adds2048 instructions, assuming the same
rounded boundary/layout (exact final map remains to be checked).

Per call49 stores =16 input +16 mask +17 output, versus e16's41. Expected
input LD count is16, versus8. Hence the narrowly identified hot-body difference
is **16 extra instructions/call =286720**. The helper's LHU->LWU remains one
instruction; VLE32/vtype23 changes do not add instruction count. More vector
data bytes may still increase hardware cycles, which this arithmetic does not
bound. Full mask128 is not reduced to logical2B; full output130 is not reduced
to its checked4B. There is no nonzero-vstart loop in this source.

## ROM And Stack Feasibility

- 48 source periods *64B =3072B, versus1536B for e16. Proof is based on distinct
  original bit patterns and the16 rotations/permutations/constants, not a new
  dedup run. Call records are2240*8=17920B; combined packed ROM20992B.
- Original six fixture tables are6*16*16*8=12288B and original FP32 inputs64B.
  Conservatively retain all12352B even if later section GC removes them.
- A planning envelope of packed ROM20992 +original fixtures12352 +core BSS8450
  +runtime8192 +stack65536 +text65536 =181058B, before alignment/other metadata.
  Thus1MiB is plausible. This is not an actual ELF map or stack proof.
- Preserve64KiB reserved stack. E16 actual caller/main/num normal depth was288B;
  the e32 eight-pair unroll has no required large stack array, but compiler
  live ranges, saved registers and spills must be counted from actual linked
  code. Do not copy the e16 frame/PC constants into a future observer.

## Instruction Evidence And Estimates

Accepted e16/mf4 full reference measured2653044 firmware instructions through
HTIF, with complete17920/EOF, not a truncated prefix. Its actual compiled
successful upper was2669042 (Spike),2682862 (SoC). Those are evidence for the
old shape only. The original error-count/popcount/first20 DETAIL path remains
implemented but is not part of an all-correct cost estimate.

| Planning arithmetic, not a proven e32 upper | Count |
| --- | ---: |
| E16 measured reference firmware |2,653,044|
| Extra input LD/SD:16*17920 |286,720|
| Additional input-backing BSS loop |2,048|
| **Measurement-based analogy** |**2,941,812**|
| Margin against3M |58,188 (1.940%)|
| E16 compiled Spike upper +same identified delta |2,957,810|
| Residual margin in that upper analogy |42,190 (1.406%)|
| E16 compiled SoC upper +same identified delta |2,971,630|

These are NOT current GCC outcomes or rigorous bounds: more address-generation
instructions, relocation changes, lost record hoisting, spills or longer
branches can consume the margin. A rise of only four instructions/call adds
71680 and defeats the measurement-based analogy. No blind flags trial or cost
PASS is justified. Error cases may cost more, and must reject rather than be
declared accepted on a finite prefix.

An incomplete lower bound, useful only to show that3M is not ruled out by
mandatory work, is878080 fresh stores +286720 input ROM LD +17920 output LWU
+2240 hoisted immutable record LD +326147 original helpers/capacity =1511107.
This omits address math, comparisons, branches, all loop/caller ABI work, stack,
startup and output. If record hoisting does not occur,17920 record loads add
15680 relative to this expression; actual CFG must charge them. All17920 calls
and source/flag/oracle obligations remain mandatory regardless of hoisting.

## Three-Hour Assessment, Not Admission

The accepted e16 M9 simulator walltime was6687.051487s. Scaling it only by
2941812/2653044 gives7414.90s (2.06h), leaving3385.10s to a3h cap. This is a
rough feasibility indicator, NOT a measured e32 rate or a latency bound:
source bytes double, vector EEW/LMUL changes and scheduling/backend latency
can differ. No e8/e16 timeout rerun is involved or authorized. The only next
step proposed is parent-reviewed software implementation and actual artifact
cost validation; reference and DUT need their own later gates.

Evidence: accepted e16 `reference_entry02/TERMINAL_REPORT.md`, independent
`fp_compare_unboxed_full17920_source_review01/REFERENCE_TERMINAL01_REVIEW.md`,
`compile01/REPORT.md`, and independent M9 `TERMINAL_REVIEW01.md`, all pinned in
`INPUT_BINDINGS.json`. No large reference/CSV was read to prepare this estimate.
