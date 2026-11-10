# Stage5: GGML Integration, Model Regression And Unified Delivery

Status: ACTIVE. No Stage5 model result or delivery is accepted yet.
Starting Ara revision: `c49289ff8f433b8780954e207d6b0149f7bc2c32`, tag
`stage4-supporting-reuse-20261110`.

## Objective And Boundaries

Integrate the retained resident Attention mechanism into actual llama.cpp/GGML
selection, validate representative model/quantization/context combinations,
and deliver pinned RTL, SDK, runtime, build inputs and reproducible evidence.
Ordinary RVV, QBS, existing AKV and unsupported-case fallbacks must remain
correct. No synthesis, PPA, new bitstream, bus/SRAM growth or new development
worktree is part of this stage.

Stage4's M4 helper is not promoted: its complete-call gain is1.020137x.
The feature-bearing resident entry is an explicit default-OFF capability, not
a default performance path; its representative gain is1.040052x and the small
functional shapes are slower. Stage3's plain-score result is distinct evidence.
Do not add or multiply these ratios, or infer model speedup from QEMU time.

## Acceptance Gates

| Gate | Required proof | Initial state |
|---|---|---|
| S1: source and execution contract | Fixed baseline/patch inventory; active consumers protected; actual QEMU/SDK/RTL capability and numerical contracts inspected | In progress |
| S2: native runtime integration | GGML capability/type/shape/rounding/ownership selection; whole-call admission and failure semantics; ordinary fallback; explicit opt-in where required | Pending |
| S3: instruction and graph validation | Actual custom instructions executed by an independently checked model; original and new GGML routes, flags, counters and numerical outputs checked; unsupported controls exercise fallback | Pending |
| S4: representative model regression | Same-input baseline/candidate model runs spanning selected models, weight formats and contexts; complete outputs/logits and actual dispatch counts; bounded individual jobs | Pending |
| S5: unified delivery | Source/patch/tool/model/build hashes, runtime switches, result table, reproduction commands, reviewed commits/tag and Stage4-to-Stage5 acceptance audit | Pending |

The finite regression matrix and numerical comparison policy must be frozen
after inspecting available captures/models and the real runtime contracts,
before execution. A synthetic graph or SDK stub alone cannot close S4.
Model runs cannot replace instruction-model checks at S3. Unsupported model
paths should retain correct fallback, not be silently cast or reinterpreted.

## Initial Findings And Preservation

The current llama.cpp HEAD is `03959acc0`; its seven tracked dirty files are
not automatically accepted delivery inputs. The previous validated runtime
tag points to `da56aa750559c180d631b466de983ff2bb5d54d9`. Reconcile these and
registered board/software changes explicitly; do not overwrite, revert or
silently commit unrelated local edits. Use archived inputs and reviewed,
hash-bound overlays for tests when the live workspaces differ.

The existing GGML native path calls ordinary v2/native-auto SDK entries,
not the resident entry. The generated resident supported fields remain0 in
the accepted software contract. An environment switch alone cannot assert
hardware eligibility or normal-memory/ownership conditions. S1 must define
the explicit experimental platform contract versus advertised production
capability before an integrated new instruction can execute.

VCS/Spike remain the RTL/architectural tools; native QEMU may validate real
runtime/model execution if its instruction model is inspected and checked.
No Verilator, URG or RTL Linux boot campaign is introduced. Long jobs use
independent outputs and direct service ownership, with one launch confirmation
and event/terminal inspection rather than repeated polling.

## Native Execution Dependency And Implementation Split

Source audit confirms that the inspected QEMU10.2.0 image implements QBS but
not AKV INFO, lifecycle, replay or resident QK/PV. Earlier AKV software emulation
is useful reference evidence, not native resident execution. Therefore S3
requires a successor QEMU instruction model, preserving the frozen QBS model.
Do not modify a previously accepted emulator source/build in place.

The implementation split is:

1. Per-hart AKV context, descriptor/range validation, FULL/REFILL/RELEASE and
   row/column/panel replay, with explicit memory-fault invalidation.
2. QEMU decode/translation and guest-memory/VRF callbacks; QEMU SoftFloat for
   dimension-ordered FP32 QK and token-ordered FP16 PV, including flags and
   legal register/control constraints. Do not substitute host arithmetic.
3. Directed state/fault/numerical checks, then the unchanged accepted Stage4
   performance and functional ELFs, before real GGML/model execution. Startup
   compatibility is an isolated test-machine adapter, not an ELF/oracle rewrite.
4. A versioned trusted-platform provider, absent/default-deny in generic builds.
   A validated test deployment is bound to sealed emulator/launch inputs;
   it does not claim new hardware discovery or board eligibility. Index4 remains
   zero. Model/native support and operator environment flags alone cannot grant
   production normal-memory or exclusive-context eligibility.
5. Minimal GGML plain-Decode selection under that contract; keep features,
   quantized KV, Prefill and unsupported shapes on their original paths.

## Proposed Finite Model Matrix

The model owner is pinning actual files, tokenizers and natural-text token
prefixes. These are intended test points, not accepted or frozen inputs yet.
Each pair changes resident selection only; QBS optimizations stay fixed.

| Model/weight family | KV | Prompt and Decode contexts | Purpose |
|---|---|---|---|
| SmolLM2-135M Q4_K_M | F16/F16 | 63 then64,65 | D64, GQA3, odd heads and tile boundary |
| Qwen3-1.7B Q4_K_M | F16/F16 | 136 then137,138, capacity256 | D128, GQA2, multi-tile tail |
| Qwen2.5-1.5B Q4_0 | Q8_0/Q8_0 | Short fixed prefix, two Decode steps | Different weight family; quantized-KV fallback |
| Same Qwen2.5 model | Q4_0/Q8_0 | Identical prefix/steps | Second quantized-KV fallback |
| Gemma3-1B Q4_K_M | F16/F16 | Existing short-prefix pattern | D256 resident rejection and original fallback |

Require eligible native resident instruction hits, zero resident execution on
ineligible paths, complete logits/tokens/CSR checks, and exact source/model/
launch provenance. Different primitive command counts across execution routes
are expected; useful logical work and each route's own protocol must match.
Only QEMU functional claims are allowed from these runs. Full integration cost
measurement must include query conversion and other GGML preparation; the
accepted SDK-only RTL ratios are not model performance.
