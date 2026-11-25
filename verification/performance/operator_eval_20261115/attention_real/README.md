# Real Captured Attention Successor

Preparation only. Never launches VCS, Spike, hardware compilation, or edits SDK.
Parent owns the activity02 all-on SoC and its maximum four simulator slots.
No result here is FPGA, runtime-default enablement, or RTL performance acceptance.

## Interface

Run from `/home/wangwy/openproject/ara_dsa`:

```sh
python3 -B verification/performance/operator_eval_20261115/attention_real/prepare.py \
  --capture /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/e2e_qwen3_f16_attention_capture_20261106_01 \
  --heads 0,1 \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_attention_real_prepare_20261115_t137_01
```

Fresh captures use the same interface with `--capture` ending in
`operator_real_contexts_20261115_01/qwen3_512`, `qwen3_1024`, or `llama32_128`.
Actual visible Decode contexts are 513, 1025, and 129, not prompt lengths.
The build emits `run-plan.json`, `source-pins.json`, `build.json`, and exact
operand/independent/model gold fixtures. Parent consumes the plan, never this
helper as a simulator launcher. Use `--order balanced` for symmetric five-arm
order; default calibration order is 0,1,4,2,3.

## Arms

0. Ordinary-memory RVV, panel4 QK and alternating v8/v10 PV. K transpose is
   timed. Arithmetic schedule derived explicitly from established full_call.
1. SDK native auto, including panel4 paired-head selection.
2. Forced compact resident mechanism with explicit test-platform assertions.
3. Experimental entry with requested=0, validated_available=0: default native
   fallback, preserving SDK native selection, not default resident enablement.
4. Established full_call panel4 QK + exact rotating-register PV source. This
   uses AKV replay loads; it is NOT ordinary-memory RVV. The only linker wrap
   replaces the PV leaf on this arm. No SDK dispatch is wrapped.

Every arm executes the same full visible KV prefix, shared unchanged SDK
online tile64 softmax and output normalization. Capture physical capacity and
full mask are retained byte-for-byte, with exact active D packed into physical
row128 for D64. No repeated KV, dimension rotation, or shortened softmax.
Qwen heads0/1 share captured KV0 (model GQA2); Llama heads0/1 share captured KV0
but are explicitly a two-head slice of a model with GQA4, not a GQA2 model.

## Numerical Contract

Known model scale is F32(round(1/sqrt(D))); exported rounded parameter JSON is
only a consistency check. D128 = 0x3db504f3, D64 = 0x3e000000. The same fixture
macro drives firmware and oracle. Every operand, mapping, model hash, head,
context, scale, and mask is recorded in fixture provenance.

Independent Spike SoftFloat library supplies ordered F32 QK, F16 PV and casts,
the SDK vector-exp polynomial, and a positive F64 reduction-tree bound. No
simulator runs. Scalar expf is independently modeled from installed newlib's
FMA-contracted ef_exp schedule, not host glibc; builds bind FP schedule and
constant tables to a pinned historical target ELF. Unsupported scalar exp
domains stop preparation. Original T137 must reproduce accepted output SHA.

Every output must also satisfy existing model tolerance
`abs(actual-model) <= 0.003 + 0.02*abs(model)`. Failing data never gets looser
tolerance or becomes performance eligible. Target compares every raw output
against independent gold and every model value outside ROI, reports a complete
output hash, and prints only the first64 raw values. Host rejects partial or
extra records, flags/CSR/guard errors, wrong paths, wrong custom opcodes, bad
DMA accounting, or mismatched command-local lane/FMA/VRF work. activity02
private-FPU checks are mandatory. Parent additionally checks protocol/image.

## Ownership

Only this directory and `operator_attention_real_prepare_20261115_*` outputs
are owned. `ancestor/` preserves sealed helper bytes with fixed hashes in
DERIVATION.json. No live imports from sealed attention/, no rewritten ancestor
pins, and no inherited historical live RTL/doc/model-input scripts. Model and
captured immutable operand identities are retained. SDK is git-archived with
the reviewed whitelist; dirty native assembly is excluded. Once a parent
consumes a build, these sources become sealed; changes require successor files.
