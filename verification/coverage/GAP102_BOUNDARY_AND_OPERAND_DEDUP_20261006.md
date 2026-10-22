# GAP102 Legal Widening Accumulator Boundary

Prepared only: no VCS/DVE run, RTL edit, exclusion, or coverage admission.

## Exact Compiled Target

Base: `cache-port1-offline-admitted-717-20261006-01`, admission seal
`82cd5f277d934c7b2435bfff3e2af1d4dd64cdea6435baba67b72749be183b62`.
Dispatcher is read from the historical snapshot, SHA256
`9af95c3eee6c63ecd9e60bf6d7c6474bdaaf1c5f96cef1bd653a6d51c6a2dd43`,
equal to the fixed build-source manifest pin, not current dispatcher RTL.

At `ara_tb.dut.i_ara_soc.i_system.i_ara.i_dispatcher`, branch raw127 remains
zero in717. Its compiled selector is spec25/vector1002, definition checksum
1558979345 and spec checksum3771491581. These are compiled diagnostic
coordinates, not newly qualified DVE exclusion identities.

The large spec's `point.line=1656` is only its root. Native vector ID1002 is
also not an expression index. Source association instead uses the compiled
branch expressions and their path bits, counted from the vector's right end:

* Expression5829, index1254, parent1245: legal widening overlap AND use_vd_op.
  The selected path demands bit1254=1.
* Expression5843, index1259, parent1254: `vl <= overlap_start_element`.
  The selected path demands bit1259=0, with complementary bit1260=1.
* Calibration: known raw345/spec25/vector784 demands expression4541's
  bit985=1. Raw offset345, native vector784 and expression index985 are
  different quantities; none is substituted for another.

Stimulus: e16,m4, VL129, tu/mu, vstart0, unmasked
`vwmaccu.vx v8,a0,v12`, a0=7, ELF opcode `0xf2c56457`.
The source group v12-v15 legally overlaps the high half of wide destination
v8-v15. The high source starts at wide element128. VL129 crosses that boundary;
the existing `vwiden_overlap_edges.c` MAC recipe uses short VL79. This source
comparison explains the stimulus choice, not a historical software-pin claim.

Falsifiable prediction: if this request takes the frozen overlap-MAC path,
line5843 takes its false arm. Source snapshot/normalization may divert the
request first; Spike PASS alone does not guarantee raw127 will increment.
Require an actual single-test raw VDB witness before any coverage claim.

## Preflight Evidence

App: `apps/riscv-tests/isa/rv64uv/vgap102_widen_acc_cross_v2.c`.
Builder/tests: `build_gap102_preflight_v2.py`, `test_build_gap102_preflight_v2.py`.
Output: `gap102-widen-acc-cross-preflight-717-20261006-02`.
Manifest SHA256: `703f8609edcccbb5a487bb047fcc8f333a05a13d649de0a1df1b4848cd31cb0b`.

10 tests PASS; actual host and Spike PASS723 checks; all75 pins rechecked.
The separate Python oracle reads both multiplicands and the wide accumulator
from the pre-instruction byte image, including the source-overwritten high
half. It validates all4096 VRF bytes, tail/other registers, all1536 source-array
bytes, two exact VL/vtype/vstart/vcsr snapshots, no trap and64 recovery/guard
bytes. The initialized alias accumulator at element128 is0x10251000; its
result is0x10260180. No in-place reference update can corrupt later operands.

Attempt01 remains FAILED: the compiler introduced an undeclared vector
initializer for the recovery buffer. V2 uses volatile scalar buffer stores;
the strict unexpected-vector-write rejection remains active and tested.
Future old-image VCS estimate: about1-3 minutes, hard budget600 seconds,
commit/vector/VDB only, no FSDB. Estimate only; no runner launched.

## Operand Parameter Dedup

Independent raw716 audit: `operand-parameter-six707-dedup-716-20261006-02.json`,
SHA256 `387283d6b8972ba59c74851fe8599f682d25914617fc0319cc83401bc8852b0f`.
Tool/tests: `audit_operand_parameter_dedup_716_v2.py` and its test;4 tests PASS.
This binds frozen queue/stage/package bytes, design/sourceinfo/metric-info and
toggle signatures, including all merged compiled variants. Null bitmap
checksums are not treated as proof: actual branch definitions are bound.

For each of st_mask_a/slide_addrgen_a/mask_m on all4 lanes, SupportIntExt2/4/8,
SupportReduct, SupportNtrVal and FPUSupport are0. The parameter-false TRUE
bodies already belong to the exact six707 operand target set: raw9-30 under
root244 (22),32 points under root336, and raw84/86/88/92/94/96 under root502
(6). Total60 per instance,720 duplicates, zero new parameter-guard candidates.
This audits prior target-set membership; it does not apply six707 to716/717.

Remaining protected zero raw coordinates per instance:
32,37,38,39,40,42,47,53,56,60,65,68,72,80,83,85,87,90,91,93,95.
Total252. They do not demand a false parameter to be TRUE; conv-case entry,
false-arm and other reachability claims need separate producer/source proofs.
No producerNone assumption, line/condition exclusion or default exclusion is
introduced. Retain these points and do not duplicate the720-point policy.
