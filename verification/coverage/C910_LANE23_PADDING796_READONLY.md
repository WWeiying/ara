# C910 Lane 2/3 Padding: Formal 796 Read-Only Review

Status: SOURCE_TYPED_CANDIDATE_NOT_NATIVE_QUALIFIED. No EDA, simulation,
RTL change, or EL addition was performed for this review.

## Exact Candidate Boundary

For each Ara physical lane 0..3, select DIVSQRT gen_num_lanes[2] and [3],
under i_vmfpu.fpu_gen.i_fpnew_bulk. The exact child suffix is:

```
gen_operation_groups[1].i_opgroup_block.gen_merged_slice.i_multifmt_slice.gen_num_lanes[N].active_lane.lane_instance.gen_thmulti_c910_divsqrt.i_fpnew_divsqrt_th_64_c910.i_ct_vfdsu_top.x_ct_vfdsu_double.x_ct_vfdsu_srt.x_ct_vfdsu_srt_radix16_with_sqrt
```

All eight compiled wrappers report FpFmtConfig=8 and WIDTH=16. The child
module is ct_vfdsu_srt_radix16_with_sqrt, Toggle checksum 3969040510,
serialized binary width 20656. Candidate members per child are ONLY:

| Object | Physical bits | Bits | Both directions |
| --- | --- | ---: | ---: |
| initial_divisor_in | [44:0] | 45 | 90 |
| initial_remainder_in | [41:0], [60:59] | 44 | 88 |

Total source candidate: 8 * 89 bits * 2 = 1424 directions. This is not a
claim of a calibrated serialized bit-to-direction mapping or official gain.
All remaining input bits, outputs, arithmetic, mode, clock, reset,
digit-boundary and root-step control remain protected.

## Source Argument

fpnew_opgroup_multifmt_slice derives lane formats using get_lane_formats
and passes LANE_FORMATS to fpnew_divsqrt_th_64_multi. Its compiled WIDTH=16
translation produces only half/bfloat format values, including the default
half value. divsqrt_fmt_q resets to zero; capture preserves the zero double
and single bits. ct_vfdsu_scalar_dp.v:183-205 resets ex1_double/ex1_single
to zero and captures only the corresponding zero format bits, otherwise
holding them. The guarantee is after reset initialization, not pre-reset X.

ct_vfdsu_prepare.v:611-625 constructs half operands with 42 trailing zeros
and bfloat operands with 45 trailing zeros. The denormal path feeds the
same aligned fraction through ct_vfdsu_ff1, whose cases only left-shift
and append zero bits (zero/default cases also return zero), then appends
one zero. It therefore cannot reduce the guaranteed 42 trailing zeros.
The divisor guarantees bits [41:0] zero. The div remainder appends two
zeros and the sqrt remainder appends one or two, guaranteeing [42:0] zero.

ct_vfdsu_srt.v:712-714 appends three zeros to ex1_divisor, giving
initial_divisor_in[44:0]=0. It constructs initial_remainder_in from
{2'b00, ex1_remainder[59:1]}, giving [41:0]=0 and [60:59]=0.
This does not assert that later iterative remainder or quotient bits stay
zero. Reset, SQRT recurrence, and digit-boundary controls are not excluded.

## Frozen Source Pins Checked

All eight current source hashes matched build-source-pins.json:

| Source suffix | SHA256 |
| --- | --- |
| src/fpnew_opgroup_multifmt_slice.sv | 42657b27f28cd781dd76515b15985167140fdf4abe7f52972a6dab4f1958715c |
| src/fpnew_pkg.sv | e742515e3c26e351c3b4a6bf160bcbfb29f7d6fb989bb81b0c34adf1384cf0e1 |
| src/fpnew_divsqrt_th_64_multi.sv | 5436effe873707cc0ecaf60de9b5476f3739df7d8549adaabee2fbc7aab1535d |
| ct_vfdsu_scalar_dp.v | f97cf092cf63c8f11638b344530d27767e569b447ca26460408c08add1d50e2d |
| ct_vfdsu_prepare.v | e7b24e037e5ad78ec0f7201de5f4593c4edfa4384c9646391878887d67d0474f |
| ct_vfdsu_ff1.v | 5df80c7b5f91aec33893fe8fe1a05cdd11cfe2c92518226933cd6fcbbbc58c1b |
| ct_vfdsu_srt.v | 1d090b2332afe2a651eeef99977ccd16bfba164c009ac42166eb2bb4ec3dc837 |
| ct_vfdsu_srt_radix16_with_sqrt.v | 685b6469e6c307cb46eb21c05047388565d0c08caf528922dea64e98ec9655e6 |

Build book: verification/out/repaired-aligned-build-20260930-01/build-source-pins.json
SHA256: 6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b

## Actual Evidence and Ownership

Formal raw: verification/out/akv-canonical-alias-offline-admitted796-parent-20261008-01/combined-toggle-bits.json
Its SHA was checked against the formal admission-manifest output pin.
Typed definitions: repaired-aligned-build-20260930-01/sim/simv.vdb/snps/coverage/db/shape/tgl.verilog.shape.xml

Qualified policy reference:
verification/out/current-population795-pmp816-agent-20261008-01/qualification.json
SHA256: 43b1c922c2561daa5d5e8cb51e30e471bb8d0eaa137d90ad10c63b55cf5257a5
The config SHA was checked against that qualification. Its pinned combined.el
SHA is 650d50d711c981a8dbb9a2c75c57605392dd248b7720869122ce10ba141b9232.
The two proposed fields have no existing Toggle masks or whole-scope ownership
in that policy. Each child already owns 158 arithmetic objects; 10582 of its
raw missing positions are in those owned objects and are not new candidates.

Raw diagnostic per field: divisor has 92 missing serialized positions;
remainder has 98 or 100. An attempted descending-declaration bit projection
did NOT match the raw pattern and was rejected. Thus no physical bit labels
or direction labels are assigned to raw coordinates by this review.

## Verification State

Read-only checks actually completed: formal raw output SHA binding, eight
source SHA comparisons, eight wrapper parameter/child checksum bindings,
binary typed width validation, and selected-field existing-EL ownership scan.
No new unit-test suite was executed or claimed. This record is not a
machine-checked exhaustive source proof or native partial-bit qualification.
Native/calibrated physical membership remains the approval gate before EL use.
