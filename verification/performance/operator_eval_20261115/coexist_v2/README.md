# Group7 Compact ISA And Coexistence

Firmware preparation only. No VCS, Spike, hardware build, SDK or production
edits. At most three delivered ELFs, reusable unchanged on the parent's same
source all-on, shared_fma_off, loan_off and queue_zero images. Parent proves
actual switch elaboration and strict independent protocol/image identity.

## Interface

```sh
env -u LD_LIBRARY_PATH python3 -B verification/performance/operator_eval_20261115/coexist/prepare.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_coexist_prepare_20261115_minimal_01
python3 -B verification/performance/operator_eval_20261115/coexist/test_coexist.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_coexist_prepare_20261115_host_tests_01
```

Deliver `run-plan.json`, `source-pins.json`, `build.json`, host test receipt and
raw build/objdump logs. No automatic simulator launch or retry is provided.

## Fixed Small Set

1. Integer: archived reviewed TEST_CASE1 vectors, 16 elements each, for vmul,
   vmulh/hu/hsu, vmacc/vmadd/vnmsac/vnmsub at SEW8/16/32/64; vwmul/u/su and
   vwmacc/u/su at source SEW8/16/32. Two representative mask/tail/restart
   successors. Exactly 52 individual vector operations, no random expansion.
2. Ordinary FMA: three reviewed vfmacc cases, FP16/32/64, plus nine directed
   FMA sign/rounding and mask/tail/restart cases. Covers cancellation, finite
   rounding, min-normal/subnormal, overflow, infinities, zero, qNaN/sNaN and
   sticky fflags. Exactly 12 operations; gold is pinned Spike SoftFloat.
3. Handoff: 14 short stages from archived qbs_akv_handoff inputs/issues. QBS,
   ordinary RVV multiply, AKV FULL/load, Resident QK, ordinary FMA, Resident PV,
   ordinary FMA, RELEASE and QBS return; additionally direct QBS->AKV and
   AKV->QBS handoffs followed by ordinary RVV. Resident D64/H2/T3 requires 384
   QK and 384 PV FMAs, with independent gold, not a full Attention benchmark.

Current parent ISA is ELEN64 and FPUSupportHalfSingleDouble. Preparation rejects
an admission source that does not establish that support. Source SEW64 widening
to128 exceeds ELEN64 and is explicitly NOT prepared, never silently skipped.
vwmaccus.vx, saturating/fixed-point vsmul, broad rounding/LMUL matrices, concurrent
exceptions and OS context switching are outside this compact regression.

All inputs are extracted using git archive of the parent's fixed
dbe2b78817ef45b912444afcb85ad6e01a2be135 revision. Validated FPGA delivery remains
1e48e205df5cec34183222c36d22eb4858466810; this is not SDK or board acceptance.
Only apps/common, reviewed ISA files, handoff source, SoftFloat wrapper and
experimental qk.S/pv.S/pv_prepare.S enter the archive. The dirty native
akv_v2_attention_rvv.S is neither archived nor compiled. No live SDK is read.
The archived handoff main is not executed; its SKIP path must disappear from
the ELF. The only text derivation surrounds four original scratch arrays with
guards, with exact original/replacement strings recorded in each build.

## Acceptance

Target compares every output byte, all inactive bytes, outer guards, immutable
data, fcsr/frm, VCSR=5 (nonzero vxrm/sticky vxsat), vstart and actual VL/vtype.
All comparisons and UART are outside ROI. Integer/FMA stages set initial flags
outside ROI; handoff stages preserve sticky flags across the complete sequence.
No traps, SKIP, unsupported type, disabled capability, missing case or extra
case can pass. Ordinary arithmetic/test entries and ordered custom opcodes must
retire from the exact ELF; vector allocations and activity02 accepted native
and private FMA semantic work must match. QBS/AKV actual command/payload counts
are checked. A single output hash never replaces the target's byte comparison.

rdcycle covers each small kernel's loads, execution, stores and final drain,
including result snapshots in handoff stages. Initialization, gold checks and
printing are excluded. Cycle data supports a small same-ELF regression pair,
not operator or end-to-end speedup claims. Sequential handoffs do not prove all
concurrent arbitration, reset/fault interactions or platform admission. The
parent must not reinterpret these synthetic arithmetic/ABI patterns as real
model data, FPGA NORMAL_MEMORY eligibility, or default Resident enablement.
