# Comparison NV Producer

Ownership: VMFPU producer only. MASKU, masku_operands and top-level routing are
owned by the parent. Do not infer full-system success from this unit.

Before any producer RTL edit, require the comparison agent's retained cycle
capture to confirm: FP compare accepts with forced-unmasked issue BE, a raw
per-slot NV reaches the old lane fflags output, and the corresponding MASKU
slice has no active predicate/window contribution. Retain the frozen final02
VMFPU (SHA256 3b8c2f8baef95679c9fbaf98077d70705708476f6cf1c7f9c375a37287b28608).

Producer contract:

- Derive dense per-physical-slot NV from issued operand A/B. EQ/NE use sNaN;
  LT/LE/GT/GE use any NaN. Use constant format fields, with only the resulting
  narrow NV vectors selected by actual fp_src_fmt.
- Reuse tag.operand_a[7:0] for comparisons only. All other operations retain
  their complete operand-A tag. No pipeline stage or tag-width change.
- At comparison output, place NV at bit 2 of each element-spaced result.
  Preserve Boolean bit 0, EW8 bit 1, and control/flag_mask tags.
- Suppress both comparison architectural flag data and flag-valid at VMFPU.
  Do not suppress ordinary operation flags or unordered pending publication.
- Parent consumes bit 2 in the same deshuffle coordinates as bit 0, then
  qualifies the accepted current slice with exact [vstart,vl) and predicate.

Focused test plan: independent real VMFPU/FPnew producer interface bench,
per-format EQ/NE/LT/LE/GT/GE, sNaN/qNaN in either operand and every slot,
finite/infinity/signed-zero controls, scalar broadcast including upstream
FP16/32 NaN-box normalization, operand bubbles, output/result-queue pressure,
consecutive operations without reset, and normal VFADD/MIN/REC7/RSQRT7 flags.
Check data and NV payload separately; inspect raw FPnew NV and flag delivery.
Alternate-format classifier banks require separate checks because current
VMFPU request decoding has no legal alternate-format compare selector.

Use frozen dependencies, VCS host only, no full build, Verilator, ZCC or URG.
Re-run the existing ordered and unordered focused regressions after the
producer passes. Existing reduction runners and benches remain untouched.

Run the matched producer suite using `run.py --out NEW_DIRECTORY`, which
defaults to frozen final02. Select the candidate with `--vmfpu PATH`.
`--metadata-checks` additionally checks the six classification banks (including
ALT via a bounded combinational force before instruction execution) and queues
VMFLT, VFADD, VMFEQ, VFREC7 with real output backpressure. The 606 instruction
cases and queued sequence do not force internal signals. Scalar boxing is
modeled at the upstream interface, not tested in a real dispatcher here.

The bench checks raw FPnew per-slot NV against the independent bit-format
oracle, then checks payload Boolean/NV bits, normal results, tag ownership,
flag data even when invalid, flag pulses, backpressure stability and exact
operation counts. Source and test inputs are SHA-pinned read-only snapshots.

See MEASURED_20261010.md for retained baseline and candidate results. Reduction
activity-epoch lifetime is an independently reported open issue; these tests
must not be used to close it or claim whole-image signoff.
