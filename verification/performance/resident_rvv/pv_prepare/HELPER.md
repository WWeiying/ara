# Candidate RVV Preparation Helper

Owned files: `prepare.S`, `test_prepare.py`, and this document only. The parent
owns the driver, measurement wrapper, build script, and README. Nothing here
freezes the directory, builds/runs a simulator, changes the SDK, or emits the
proposed custom PV instruction. Public symbol: `resident_pv_prepare`.

## Call Contract

Leaf, with a0-a5, ra, and sp unchanged:

| Register | Input |
| --- | --- |
| a0 | FP32 coefficients, two rows with 256-byte row stride |
| a1 | FP16 seeds, two heads with 512-byte memory stride |
| a2 | FP32 scale[2], four bytes per element |
| a3 | T, 1 through 64 |
| a4 | D, exactly 64, 96, or 128 |
| a5 | H, exactly 1 or 2 |

The caller must validate geometry, VLEN=1024, vstart=0, legal current frm=0..4,
V/Zfh/Zvfh availability, and accessible naturally aligned active input spans.
There is no failure status or runtime admission in this cost-measurement helper.
H1 requires only the first row/head/scale to be accessible; second-head memory
is neither read nor used in FP.

Output is v8:v9=seed0, v10:v11=seed1, v12:v13=64 interleaved coefficient pairs.
Each register holds 64 halfwords at VLEN1024. Each seed head reserves 128
halfwords, not D halfwords. Thus head1 starts at v10 even for D64/D96.
The reserved future source operand is v8-v15, but only v8-v13 are imported.
v14:v15 are disposable packing scratch, not additional source payload.

Actual clobbers: t0/t1, ft0/ft1, v8-v21, vl/vtype, and accrued fflags. v0-v3,
ra/sp, all a registers, and frm are untouched. The caller may conservatively
declare the broader agreed clobber set. v16-v19 contain coefficient loads;
v20/v21 contain narrowed halves. Vector state is left at VL128, e16, m2.

## Selected Sequence

1. At VL128/e16/m2, integer-clear v8:v9 and v10:v11. This defines inactive seed
   slots and sets both complete seed groups to EW16 within preparation. It avoids
   hiding maintenance on D64's unused v9 or H1's unused v10:v11 in a later import.
2. Set VL=D/e16/m2 with tail-undisturbed; load active seed0 and, only for H2,
   active seed1 from +512B. Perform scale0 `fcvt.h.s ...,dyn`, then seed0
   `vfmul.vf`; only for H2, scale1 conversion then seed1 multiply. Inactive seed
   elements remain raw zero and never execute FP.
3. Load T FP32 coefficients per active head at e32/m2 into v16:v17 and, for H2,
   v18:v19. Set VL=T/e16/m1. Narrow head0 with `vfncvt.f.f.w v20,v16`, then H2
   head1 with `vfncvt.f.f.w v21,v18`. H1 uses integer-zero v21 instead.
4. Still at VL=T/e16/m1, `vwaddu.vx v12,v20,zero` and
   `vwaddu.vx v14,v21,zero` zero-extend the **raw 16-bit representations** into
   EEW32/EMUL2 groups. Set e32/m2, shift v14 left 16, and OR into v12. Pair t is
   `uint32(head0_half[t]) | (uint32(head1_half[t]) << 16)`, with zero high half
   for H1. No gather, slide, mask register, scalar token loop, or temporary store.
5. Before return, set VL128/e16/m2 and execute `vor.vv v12,v12,v12`. This is a
   real full-group EW16 normalization operation, deliberately inside the helper
   and measured preparation window, including T<32. No post-timer dump is needed
   to perform the intended coefficient conversion/maintenance.

For T=64, source F32 EMUL2 and narrowed F16 LMUL1 both have capacity 64; packed
e32/m2 has capacity 64 pairs and final e16/m2 has capacity 128 halfwords. All
widening/narrowing groups are aligned and nonoverlapping. For shorter T, only T
coefficients per active head enter FP. Unused coefficient pairs are unspecified
raw bits, not additional numerical operands. Their integer normalization may
read/write them but must not contribute FP flags.

## FP And Measurement Boundary

`fcvt.h.s` uses dynamic rounding; `vfmul.vf` and `vfncvt.f.f.w` use current frm.
The helper never clears, reads, or writes FCSR/fflags/frm. Existing flags survive
and active operations accrue flags normally. Scale-convert/multiply order is
head0 then head1, as in `rotation/pv_rotation.S`.

The selected vector coefficient path converts all active head0 coefficients,
then active head1 coefficients, instead of scalar token-wise head0/head1
alternation. It preserves the intended final accrued flag union and per-element
rounding, not intermediate per-token fflags observation order. There is no FCSR
observation inside this helper. Full-call numerical/flags equivalence remains a
parent acceptance requirement; these host checks are not a floating-point oracle.

Time the actual helper including seed initialization and final normalization.
Include any required dependent-use/completion observation in the measurement;
CPU return alone is not a claim that vector work is drained. This is one chosen
candidate's preparation cost, not proof of optimal preparation or full-call
speedup. The parent will use its frozen SoC image and real-model driver to judge
the complete-call benefit ceiling before integration. No new component gate is
proposed here.

## Host Checks

`python3 -B test_prepare.py` checks the source control paths, written registers,
all 384 valid D/H/T combinations, active FP/load boundaries, raw-bit pair packing,
fixed head strides, and placement of EW16 normalization. It does not assemble,
execute RVV, model FP arithmetic, or evaluate performance.

After the parent builds, optional `python3 -B test_prepare.py --disassembly FILE`
also checks GNU objdump `-d -M no-aliases,numeric` output for the public symbol,
leaf register discipline, required opcodes, dynamic scalar conversion rounding,
and the final full-VL EW16 normalization sequence. Only the named helper's
instructions are inspected; other parent-owned driver symbols are untouched.
