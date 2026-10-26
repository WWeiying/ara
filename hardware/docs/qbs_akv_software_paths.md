# QBS / AKV Software Paths and Switches

Source audit: 2026-10-26. This documents current selection, not a new performance
acceptance or deployment recommendation. The source audit did not edit external
sources. A separate fresh paired field-copy VCS measurement is now complete;
see [the measured scope and results](../../verification/akv/quantized_kv/field_copy_pair/RESULTS.md).
Earlier H/S/B results do not measure that change.

## Source Names

Repository paths below are relative to `ara_dsa_signoff_integration`.
`GGML` means the read-only external `/home/wangwy/llama/llama.cpp/ggml` tree;
`Q` = `GGML/src/ggml-cpu/arch/riscv/qbs.cpp`, `A` = adjacent `akv.cpp`,
`K` = adjacent `quant-kv.cpp`, and `N` = `software/akv/src/akv_v2_native_riscv.c`.
Line references describe the inspected source, not immutable linked binaries.

## Switch Table

Defaults distinguish hardware parameters, compilation, and runtime environment.
Use literal `1`/`0` for environment controls: Q/A accept additional truth spellings,
but M4 preparation and the shared native AKV opt-ins require exactly `1`.

| Path / switch | Actual default and selection | Fallback / boundary | Source and accepted evidence |
| --- | --- | --- | --- |
| QBS `SplitIssue`, `HalfScaleIssue` | RTL parameters both `1`; production compute instance uses those defaults. No GGML environment switch. | Format/operation gating remains inside accumulator; comparison parameter settings require a different image. | `hardware/src/vlsu/qbs/qbs_fp_accumulator.sv:10`, `qbs_compute_engine.sv:607`; [split](qbs_fp_split_issue.md), [half-scale](qbs_half_scale_issue.md). |
| QBS activation lookahead | RTL `ActivationLookahead=1`; command enable requires DIRECT, with the short-M scheduling guards retained. | Not activation-context reuse; no runtime environment knob. | `hardware/src/vlsu/qbs/qbs_engine.sv:19,1029,1546`; [overlap](qbs_activation_overlap.md). |
| QBS backend | CMake `GGML_RISCV_QBS=OFF`; compiled backend also needs runtime `GGML_RISCV_QBS=1` for native selection. | Unsupported type/shape/capability stays on ordinary GGML; `GGML_RISCV_QBS_EMULATE` is a separate reference executor, not native proof. Optional `GGML_RISCV_QBS_FORMATS` restricts formats. | `GGML/CMakeLists.txt:180`, Q:234-248,300,528; [native graph/context](../../verification/qbs/results/ggml-tile-context-20261023.json). |
| SDK M4/M8 activation byte packing | Explicit RVV automatically compiled under `__riscv_vector`; no runtime opt-in. `QBS_PACK_FORCE_SCALAR` **being defined**, even as zero, disables explicit RVV. `QBS_PACK_AVL_LIMIT` defaults to zero, a test-only ceiling. | Portable scalar fallback; byte-unaligned aux supported; caller validates sizes/non-overlap and zero-pads only inactive rows. No FP conversion or Zfh dependency. | `software/qbs/include/qbs/qbs_pack_rvv_internal.h:4-33`, `software/qbs/src/qbs_runtime.c:425-524`; [native API](../../verification/qbs/results/runtime-activation-pack-native-20261023.json), [runtime twins](../../verification/qbs/results/runtime-pack-projection-twins-v2-20261023.json). |
| Fused M4 Q8_0 / Q8_K preparation | `GGML_RISCV_QBS_M4_PREPARE` defaults OFF, cached on first use. Opt-in branch requires QBS and **no `__riscv_zvfh`**. | Helper numerical-domain guards retain production generic fallback. With Zvfh, Q8_0 uses its existing Zvfh implementation and Q8_K the existing generic implementation; this opt-in branch is not selected. | `GGML/src/ggml-cpu/repack.cpp:347-407`, adjacent `arch/riscv/q8_0-m4.h`, `q8_K-m4.h`; [Q80 production](../../verification/qbs/results/ggml-m4-canonical-soc-20261023.json), [Q8K live graphs](../../verification/qbs/results/q8k-live-graphs-20261023.json). |
| Activation context / resident cross-op AQ | `GGML_RISCV_QBS_ACTIVATION_CONTEXT` absent means ON **after backend admission**. `GGML_RISCV_QBS_CROSS_OP_CONTEXT` absent also means ON, requiring context enabled and non-emulation. | SDK checks every command's layout, capacity, M/K, and lifecycle; split-K/gather/accumulate and singleton-N plans are ineligible. Cross-op skip-quantization additionally requires one worker, Q8_K, matching graph epoch/source/consumer identity. Otherwise use ordinary preparation/plan, not assumed residency. | Q:242,864,1062,1259; `software/qbs/src/qbs_runtime.c:699-751`; [full projection](../../verification/qbs/results/context-projection-soc-20261023.json), [actual interleave](../../verification/akv/results/quantized-kv-ggml-interleave-20261024.json). |
| Wide M / segmented weights | `GGML_RISCV_QBS_WIDE_M` defaults OFF. `GGML_RISCV_QBS_SEGMENT_K_BLOCKS` defaults zero, cached; nonzero selects segmented packing policy, not QBACC. | Wide choice remains subject to device/layout limits and can lose context eligibility. Invalid segment syntax/range aborts, not silent fallback. | Q:247,1211,1386-1406; [six-run graph matrix](../../verification/qbs/results/ggml-tile-context-20261023.json). |
| QBACC / long-K continuation | `hardware/Makefile:27,133-140`: `qbs_vrf_continuation` defaults `0`; capability can be enabled in a test image. No corresponding automatic GGML continuation selector is established. | Keep long-K optimization OFF: accepted real Q6_K panel case was slower. Hardware capability, standalone SDK exercise, and runtime deployment are different claims. | [design and negative result](qbs_vrf_continuation_design.md), [SoC proof](../../verification/qbs/results/qbacc-soc-20261023.json). |
| F16 AKV backend / kernel / portable | CMake `GGML_RISCV_AKV=OFF`; runtime `GGML_RISCV_AKV` OFF. `GGML_RISCV_AKV_KERNEL` defaults `auto` (v2 with required caps, otherwise v1); accepts `v1`/`v2`. `GGML_RISCV_AKV_PORTABLE` OFF, applies to v2 Decode. | Full type/layout/mask/capability admission precedes execution. `GGML_RISCV_AKV_EMULATE` selects reference execution. Invalid kernel policy or unsupported request returns ordinary GGML. | A:79-89,131,221,495,682; [shared Decode](../../verification/akv/results/canonical-decode-runtime-20261024.json), [Prefill](../../verification/akv/results/canonical-prefill-runtime-20261024.json), not native full-GGML/model acceptance. |
| AKV REFILL overlap | Compile macro `AKV_REFILL_OVERLAP=0`; not an environment switch. | Keep serial scheduling: whole-Attention paired measurement regressed despite focused overlap success. | N:10-15,611; [negative whole-call result](../../verification/akv/results/refill-attention-abba-20261023.json). |
| One-query D128/GQA6 PANEL4 | `AKV_QK_PANEL4` OFF; exact `1`, real native PANEL4 capability, F16/D128/six-row plan required before FULL. Missing weak `getenv` means OFF. | Falls back to existing singles kernel. This is **not** a global disable of PANEL4: existing D256 and Prefill Q2/GQA2 paths independently use capability-selected PANEL4. | N:104-124,538,613,821,854; [numeric](../../verification/akv/results/qk-panel4-rtl-20261024.json), [whole call](../../verification/akv/results/qk-panel4-attention-20261024.json). |
| Paired Decode QK/PV | `AKV_PAIR_HEADS` OFF; exact `1`, VLEN1024, real caps, 2..8 heads, D64/96/128; excludes D128/six heads to retain its specialized path. | Generic leaves otherwise; odd final head uses generic. Selection once before FULL, no cross-call pair state. | `software/akv/experimental/paired_heads/native_selection.h:11`, `dispatch.h`; [KV128](../../verification/akv/results/paired-heads-threeway-20261024.json), [KV256](../../verification/akv/results/paired-heads-kv256-threeway-20261024.json). |
| Paired Prefill F32 PV | `AKV_PREFILL_PAIR_PV` OFF; exact `1`, VLEN1024 and row/tail/dimension caps; same head/dimension bounds and six-head D128 exclusion. | Generic F32 PV, including odd remainder. This is not Decode's padded F16 accumulator representation. | `software/akv/experimental/paired_heads/f32_pv/runtime.h:11-52`, N:690; [primitive](../../verification/akv/results/paired-f32-pv-rtl-20261024.json), [whole shared Prefill slice](../../verification/akv/results/canonical-prefill-runtime-20261024.json). |
| Quantized KV native QBS DIRECT | CMake `GGML_RISCV_AKV_QUANT_KV=OFF`, nested under AKV and requiring QBS. Runtime needs `GGML_RISCV_AKV_QUANT_KV=1`, `GGML_RISCV_AKV_QUANT_KV_NORMAL_MEMORY=1`, and native QBS enabled. | One worker, Decode, K Q4_0/Q8_0, V Q8_0, finite guarded domain, VLEN1024/vstart0/RNE, prefix mask and checked non-overlapping strides. Rejection before execution returns ordinary GGML; execution failure after admission aborts. Not an AKV quantized-payload engine. | A:691-700; K:50-103; `software/akv/experimental/quantized_kv/selection_strided.h:15`; [graphs](../../verification/akv/results/quantized-kv-ggml-strided-20261024.json), [short actual model](../../verification/akv/results/quantized-kv-model-strided-20261024.json), [Q4 H/S/B](../../verification/akv/results/canonical-q4-hsb-acceptance-20261025.json), [Q8 H/S/B](../../verification/akv/results/quantkv-hsb-q8-acceptance-20261025.json). |
| Fixed-size field-copy implementation | `AKV_QUANT_FIELD_COPY` uses `__builtin_memcpy` for GNU/Clang, ordinary `memcpy` otherwise. No new environment/CMake performance switch. | Object-representation copy, no pointer-punning/alignment strengthening; bulk gather/copy remains separate. Fresh Q4_0 K / Q8_0 V full-call pairing measured 16.35% fewer cycles for the native path, including compiled layout effects. This is not full-model deployment acceptance. | `software/akv/experimental/quantized_kv/field_copy.h:4-13`; consumers `selection.h`, `selection_strided.h`, `ggml_decode.h`, `online.h`, `q8_0_value.h`; [paired evidence](../../verification/akv/quantized_kv/field_copy_pair/RESULTS.md). |

## Actual Backend Connections

- **QBS:** GGML repack dispatch -> `qbs.cpp` activation planning / context preparation
  / `execute_plan` -> shared `software/qbs/src/qbs_runtime.c` and
  `qbs_native_riscv.c`. Packing already-interleaved M4 output is not synonymous
  with running the SDK row-major-to-interleaved byte packer. Fused quantization
  and byte packing are separate optimizations with separate callers.
- **F16 Attention:** `GGML/src/ggml-cpu/ops.cpp:9075` -> A's Decode/Prefill support
  checks -> worker zero -> `context_mutex()` across FULL/REFILL/compute/RELEASE
  -> shared native C/S (or explicitly selected reference). Other GGML workers
  wait at the post-node barrier. Decode v2 supports admitted D64/96/128 shapes;
  v1 remains D128/GQA6. Prefill additionally requires the GGML tiled-query
  threshold (`GGML_FA_TILE_Q`) and its layout/causal-mask contract. A smaller
  direct SDK slice does not prove that full GGML Prefill route ran.
- **Quantized Attention:** A's quantKV branch is **before** F16 runtime admission;
  `GGML_RISCV_AKV=0` alone does not disable it. K uses production GGML query
  `from_float`, shared RVV V decoding and scale/mad, bounded strided K panels,
  then Q's guarded DIRECT bridge. AKV mutex is acquired before QBS mutex. The
  bridge does not wait for or destroy reserved persistent AQ; it admits only
  synchronous, row-major, non-segmented Q4_0/Q8_0 x Q8_0 DIRECT commands
  (Q:809-839,1159-1181). QBS emulation cannot supply this native device. AKV's
  emulation flag is not a quantKV reference-mode switch.

## Rebuild and Fallback Instructions

1. Resolve **both source directories explicitly** in a fresh external build:
   `GGML_RISCV_QBS_RUNTIME_DIR=<signoff>/software/qbs` and
   `GGML_RISCV_AKV_RUNTIME_DIR=<signoff>/software/akv`. They are source roots, not
   paths to an installed library. Only QBS has the compatibility inference from
   `GGML_RISCV_QBS_INCLUDE_DIR/../../software/qbs`; AKV has no analogous inference.
   quantKV is resolved as `${GGML_RISCV_AKV_RUNTIME_DIR}/experimental/quantized_kv`.
   See `GGML/src/ggml-cpu/CMakeLists.txt:444-515`.
2. Enable only the desired build options. QBS requires RVV and CPU repack; AKV
   requires RVV, Zfh and Zvfh; quantKV additionally requires both backends and its
   own build option. CMake compiles the shared SDK sources directly. This AKV
   ISA requirement also explains why the no-Zvfh M4 preparation opt-in is not
   automatically active in the combined binary. Preserve the existing per-source
   FP flags (`CMakeLists.txt:486-489,517-526`); do not replace them with fast-math.
3. Recompile affected C/C++ objects and relink the final program, recording resolved
   include/source paths and object/library/ELF identities. In particular, old
   static libraries and frozen primitive/runtime objects **do not acquire the
   `083d` field-copy source change** merely by changing a source checkout or env.
   The field-copy experiment rebuilt its affected benchmark objects and linked
   two fresh ELFs; it did not rebuild an external llama.cpp model executable.
4. For ordinary fallback, explicitly disable the appropriate runtime backend and
   its emulation switch; also disable `GGML_RISCV_AKV_QUANT_KV` independently.
   Setting pair/PANEL4 opt-ins to zero retains generic AKV, not ordinary RVV.
   Disabling activation context retains QBS DIRECT, not ordinary GGML. Restart
   the process when changing cached M4/segment policy. Never retry ordinary
   computation after a partially admitted native failure as if it were a selector
   rejection. Native execution requires a compatible custom-instruction target.
5. Observe actual selection using QBS call/lifetime/M4 preparation traces and
   `GGML_RISCV_AKV_TRACE` (including `GGML_RISCV_QUANT_KV_LAYOUT`); env presence or
   successful linking alone is not evidence of native execution. Freestanding
   benchmarks may supply their own weak `getenv` mode provider; that is not the
   default of a Linux GGML process.

## Remaining Scope and Drift

The **paired field-copy RTL experiment** completed with two freshly rebuilt
binaries and complete-call checks. H/S/B cycle sums changed from
3171119/1755032/1137762 to 3009554/1726145/951711, respectively (two calls per
mode). This measures the compiled software change, including natural layout
effects, on the same hardware. It is neither hardware-only nor model speedup.
The new source keeps the selector and numerical contract; it does not create a
new supported shape or justify promoting opt-in backends to defaults.

Activation-context traffic savings are not a blanket latency gain: the real
full-output projection was 256975 DIRECT versus 257184 context cycles. Wide-M
selection can reduce resident eligibility under the 4672-byte capacity; it is not
a context-aware global traffic optimizer. REFILL overlap and long-K QBACC retain
their negative-result/OFF policy. Accepted paired-head four-head capture subsets
and shared Prefill slices are not full native F16 GGML/model proof. That separate
future scope, and the unimplemented QBS/AKV Spike extension, are not silently
added as prerequisites to this bounded software-path organization task.
