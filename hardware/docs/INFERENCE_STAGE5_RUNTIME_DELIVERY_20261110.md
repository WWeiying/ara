# Stage5: GGML Integration, Model Regression And Unified Delivery

Status: ACTIVE. Same-image native instruction/SDK gates pass. SmolLM2 has a
separate accepted scoped audit; Gemma D256 fallback and Qwen3 F16 pass.
Qwen2.5 Q4/Q8 KV has an accepted separate command-accounting audit. The final
Q8/Q8 model pair and unified delivery audit are not yet accepted.
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
| S1: source and execution contract | Fixed baseline/patch inventory; active consumers protected; actual QEMU/SDK/RTL capability and numerical contracts inspected | Source/build contracts checked; deployment remains experimental |
| S2: native runtime integration | GGML capability/type/shape/rounding/ownership selection; whole-call admission and failure semantics; ordinary fallback; explicit opt-in where required | Implemented and compile/link checked; full-model acceptance pending |
| S3: instruction and graph validation | Actual custom instructions executed by an independently checked model; original and new GGML routes, flags, counters and numerical outputs checked; unsupported controls exercise fallback | Same-image instruction/SDK gates pass; real GGML graph check remains with S4 |
| S4: representative model regression | Same-input baseline/candidate model runs spanning selected models, weight formats and contexts; complete outputs/logits and actual dispatch counts; bounded individual jobs | Four of five pairs accepted; Q8/Q8 remains in progress |
| S5: unified delivery | Source/patch/tool/model/build hashes, runtime switches, result table, reproduction commands, reviewed commits/tag and Stage4-to-Stage5 acceptance audit | Pending |

The finite regression matrix and numerical comparison policy must be frozen
after inspecting available captures/models and the real runtime contracts,
before execution. A synthetic graph or SDK stub alone cannot close S4.
Model runs cannot replace instruction-model checks at S3. Unsupported model
paths should retain correct fallback, not be silently cast or reinterpreted.

Current native gate evidence is
`stage5_qemu_four_gates_20261110_03/result.json`, SHA256
`d1fe3d705d1caa1923536eff66a6e4fa51030d180e2db01c1724ccc1a4f211d0`.
It binds the directed enabled/disabled/ROM tests and unchanged QBS/Stage4
performance/functional ELFs to BUILD07. No full-model result follows from
these gates. The model provider additionally retains real Linux CSR guards
and permits the exact fixed model's shared read-only mapping, matching llama's
actual mmap loader; it does not grant arbitrary shared/device memory access.

## Initial Findings And Preservation

The current llama.cpp HEAD is `03959acc0`; its seven tracked dirty files are
not automatically accepted delivery inputs. The previous validated runtime
tag points to `da56aa750559c180d631b466de983ff2bb5d54d9`. Reconcile these and
registered board/software changes explicitly; do not overwrite, revert or
silently commit unrelated local edits. Use archived inputs and reviewed,
hash-bound overlays for tests when the live workspaces differ.

The source comparison establishes that current HEAD is not a superset of the
validated delivery: its two-file delta removes the quantized-KV CMake block
and several mask/feature handling paths. Do not use a plain HEAD archive as
the complete integration baseline. Preserve the da56 runtime and register a
minimal reviewed adaptation of auto-pair commit `06d046324` instead. Its last
patch context differs from da56, so direct patch application or unchecked
copying of the dirty runtime is not an accepted reconstruction procedure.
Accepted da56 CMake SHA256:
`2168ddbf805dc048b86d868468b4793f8998d635bd55cfa9d247bef4e375275f`;
accepted da56 AKV source SHA256:
`a2382b3a19a9c035428181c22a131ca18aaa466c153d9dc8006d7b43a75f97fb`.

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

Actual files, tokenizers and natural-text token prefixes are frozen in the
final model preparations and their explicit launch-asset bindings. Frozen
inputs are not themselves evidence of successful model execution.
Each pair changes resident selection only; QBS optimizations stay fixed.

| Model/weight family | KV | Prompt and Decode contexts | Purpose |
|---|---|---|---|
| SmolLM2-135M Q4_K_M | F16/F16 | 63 then64,65 | D64, GQA3, odd heads and tile boundary |
| Qwen3-1.7B Q4_K_M | F16/F16 | 136 then137,138, capacity256 | D128, GQA2, multi-tile tail |
| Qwen2.5-1.5B Q4_0 | Q8_0/Q8_0 | 40 then41,42, capacity256 | Different weight family; original quantized-KV route |
| Same Qwen2.5 model | Q4_0/Q8_0 | Identical prefix/steps | Second original quantized-KV route |
| Gemma3-1B Q4_K_M | F16/F16 | 4 then5,6, capacity256 | D256 resident rejection and original fallback |

Require eligible native resident instruction hits, zero resident execution on
ineligible paths, complete logits/tokens/CSR checks, and exact source/model/
launch provenance. Different primitive command counts across execution routes
are expected; useful logical work and each route's own protocol must match.
Only QEMU functional claims are allowed from these runs. Full integration cost
measurement must include query conversion and other GGML preparation; the
accepted SDK-only RTL ratios are not model performance.
