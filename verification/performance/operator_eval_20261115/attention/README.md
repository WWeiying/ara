# Current-RTL Attention Preparation

No simulator, SoC compile, URG, Verilator, production edits, or commits are made
by these tools. The external parent owns the current all-on SoC, max-four
scheduler, independent protocol check, terminal SUCCESS, and pre/post image pins.

## Ready Artifacts

Under `/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/`:

- `operator_attention_prepare_20261115_calibration_01`: T137, D128, GQA2,
  three complete calls, order RVV/native/Resident. Original real Qwen3 capture.
- `operator_attention_prepare_20261115_d64_t64_01`: derived D64/GQA2/T64.
- `operator_attention_prepare_20261115_d96_gqa3_t65_01`: derived D96, two KV
  groups of three heads, tail1, local pair H2/H1, global offsets checked.

Each successful build has `build.json` state `BUILT_NOT_EXECUTED`, `attention.elf`,
`inputs/fixture.json`, `source-pins.json`, and the parent's `run-plan.json` format.
Firmware compilation and checker host tests do not establish RTL correctness.

## Interface

```sh
env -u LD_LIBRARY_PATH python3 -B verification/performance/operator_eval_20261115/attention/prepare.py \
  --case qwen3_d128_gqa2_t137 \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_attention_prepare_20261115_example
```

`--order balanced` emits six calls `[0,1,2,2,1,0]`. The default calibration emits
three calls `[0,1,2]`. Select any Decode shape in `cases.json` with `--case`.
Always use a fresh owned output; failures and originals are never overwritten.
Compiler environment injection is rejected. Only the fixed GNU bare-metal
toolchain is used. Every object, header dependency, tool, archive, and linked
library is inventoried. No historical object or ELF is reused.

```sh
python3 -B verification/performance/operator_eval_20261115/attention/check.py \
  --build BUILD --log RUN/run.vcs.log --vector RUN/vector.csv \
  --commit RUN/commit.csv --output RUN/attention-result.json
```

The checker returns nonzero on failure and writes `{state: PASS|FAIL, metrics: ...}`.
It intentionally leaves `protocol_checked`, `image_checked`, and
`performance_acceptance` false. The parent combines this with independent checks.

For the parent activity02 image, use the successor `check_activity.py` with the
same arguments. `activity_interface.py --build BUILD --output FRESH_OWNED_OUTPUT`
seals an updated central manifest and source inventory without modifying the
original build or its pinned helpers. It requires exactly four `OPERATOR_UNIT`
records per call, checks every lane's accepted private-FPU semantic QK/PV work,
and keeps normal-FMA requests separate from private Resident requests.

## Version And Arithmetic

SDK/common: `git archive dbe2b78817ef45b912444afcb85ad6e01a2be135`, not Git ref
`main`. Exactly eleven compact overlays are copied from the receipt-checked
`resident_direct_model_20261114_03/inputs/sdk`, matching `direct_model/build.py`.
The live dirty `akv_v2_attention_rvv.S` is never read or copied. Archive assembly
SHA is `0e90dccf193c43bcda367fa18813bedb1077e9790795635f9efa993871a20061`.

All modes convert the same F32 queries to F16, use ascending-dimension widening
F32 QK, tile64 SDK online softmax, token-ordered FP16 PV, F32 normalization, and
a final drain inside complete-call timing. The memory-RVV baseline shares the
unchanged archived SDK softmax/store functions through a single translation
unit; it packs K inside the ROI and reuses K/V loads for head pairs. Native is
the actual native-auto SDK entry. Resident is the actual compact SDK executor,
with all groups preflighted before FULL, no link wrappers and no partial retry.
Single-owner bare-metal platform admission is explicit, not a NORMAL_MEMORY
board deployment claim. Parent image requirements: four lanes, VLEN1024,
16 MiB L2, enabled AKV v2/Resident QK/PV, gate reset strict0.

Independent checked flags-v2 SoftFloat reference reconstructs every full output,
natural and incoming sticky flags, command-local QK/PV flags, and query narrowing.
The original T137 result must reproduce accepted golden SHA
`0be0c9b07fdbd8773ec85ef2b738bbcc65f657f322d65e77610609c968ee9316`.
Initial DZ=8 must survive; original natural flags=3, final FCSR=11.
F64 positive-sum bounds prove reduction-tree independence before F32 rounding.
Host expf is the existing pinned scalar-libm contract, not a new exact-exp claim.

The checker demands complete raw outputs, full input/golden and query hashes,
outer/inactive guards, FCSR/VCSR/VSTART, group offsets, actual retired SDK and
leaf entries bound to ELF instructions, exact custom opcode sequence, AKV
command/payload totals, Resident geometry/flags/architectural byte-write masks,
and unique terminal records. For T137 calibration there are 241 AKV commands:
237 native, four Resident lifetime commands, and zero memory-RVV commands.
Resident has three QK and three PV instructions, each totaling 35,072 scalar
FMA elements over the full call. These are work counts, not utilization ratios.

Two `csrr zero,cycle` markers per call enable/disable the existing TB monitor,
outside the rdcycle stamps with no added fence. Commit evidence checks all six
markers. The base checker retains `[PERF]` console records. The parent collector
uses `monitor_metrics.py` to parse the actual `[LLM_PERF]` records in separate
`llm_perf_report_*.log` files and the `OPERATOR_UNIT` console records. These are
not `LLM_METRIC` records. Activity02 monitor cycles and complete-call rdcycle
intervals are deliberately distinct.

## Open Scope

The memory-RVV arm is `diagnostic_tiled_rvv`, pending strongest-baseline review;
it cannot support a primary RVV speedup claim. The inspected `full_call` baseline
uses AKV Panel4 QK and rotating-register V-row PV, so copying that baseline and
calling it pure memory RVV would be incorrect. Native-vs-Resident calibration
does not establish balanced repeated-call performance. Integrating the stronger
established Panel4/rotating-register baseline is an explicit next gap, not an
edit to make while T137 runs. No speedup is required or inferred by a checker
PASS.

The D64/D96/GQA/tail and context matrix is executable via `prepare.py`. Derived
queries rotate captured dimensions within rows; KV group g uses captured
visible token `(t+64*g)%137`, physical row128, unchanged scale. Prefix cases
recompute full softmax; they do not reuse the T137 golden. T256/T512/T1024 repeat
visible captured rows and are correctness/structural-only, not real long-context
model performance. Fresh captures remain required for primary context curves.

Prefill and quantKV remain unclosed. The authoritative existing F16 shared-reader
replay is `verification/akv/shared_reader_integration/run_real_runtime.py --kind prefill`
(the draft `run_real_prefill.py` pointer in the frozen cases file is not a file).
It checks historical build/image schemas and launches VCS, so do not invoke it
from this preparation interface. The checked quantized Prefill builder
`verification/akv/quantized_kv/prefill/build_production_native.py` consumes a
16-object archived recipe, a separately audited Q4_0/Q8_0 real capture, live
production quantized sources, and a different output-ownership root. Rebinding
these to the current archive/central runner requires separate preparation and
numeric/flag review; this work does not silently route them through F16 Decode.
The compact executor does not admit Prefill/non-F16; fallback is not Resident.

## Host Tests

```sh
python3 -B verification/performance/operator_eval_20261115/attention/test_attention.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_attention_prepare_20261115_hosttests_example
```

Synthetic passing records and mutations test the checker, never RTL acceptance.
Do not edit pinned helpers or these firmware outputs once the parent consumes
their source inventory. Later fixes require successor helpers and fresh outputs.
