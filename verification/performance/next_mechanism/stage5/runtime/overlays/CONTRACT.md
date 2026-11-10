# Stage5 GGML Resident Overlay V1

Held experimental integration, not native/model/board acceptance. Do not modify
the six sealed parent runtime files or the user's dirty llama repository.

`prepare.py` archives llama `da56aa750559c180d631b466de983ff2bb5d54d9`,
checks the two base hashes, applies the reviewed adaptation of auto-pair commit
`06d046324e1dde07d3d6f8625843b2b8858a1a06`, and requires the intermediate
AKV hash `40e41f2ac210c8c1eeb0ad3149734e47a12044fa17fe4d30797b75a23320544f`.
No dirty input is copied. The quantKV CMake block, feature/emulation behavior and
auto/explicit native policy remain from this baseline. Then the new opt-in is
materialized in a separate build input and recorded with pre/post hashes.

## Build And Route

`GGML_RISCV_AKV_RESIDENT=OFF` is the default CMake option. OFF adds no SDK leaf,
platform code or resident symbol and preserves the adapted baseline object.
ON requires the frozen experimental SDK, links qk.S and pv.S once (pv.S includes
its own prepare), and fixes the initial no-refill-overlap schedule. Stage4
features-v2 is not enabled. Scalar guard/platform and AKV dispatch compile with
vectorization disabled; the CSR reader is the existing sealed scalar assembly.

The runtime request is `GGML_RISCV_AKV_RESIDENT=1`. This is a request ONLY, never
authority. A linked provider is still mandatory for both OFF-request native and
ON-request resident calls in an ON build. No provider means ordinary GGML before
INFO or any custom opcode. Actual CSR access only follows validation of the
trusted provider's safe-state contract. Non-RNE or VLEN mismatch declines before
INFO; nonzero VSTART is terminal, not an ordinary vector fallback. No CSR is
written. No provider is registered here; validated-model registration is held
until its model and launcher are accepted. Production capability index4 stays0.

Resident scope: single worker, Decode, F32 Q / F16 K,V, D64/96/128 and the
existing v2 shape/layout guards. The global quantKV environment switch does NOT
exclude F16. Actual quantized K, Prefill and unsupported v2 use the unchanged
legacy body only with the separately registered `ggml_akv_legacy_current_v1()`
contract. Its default is NULL. BASE explicitly authorizes legacy INFO/native;
PREFILL and QUANT_KV additionally authorize those implementations (QUANT_KV
includes their QBS/quantized-value paths). No legacy support is inferred from
resident QK/PV profile bits. Contract provider pointer/SHA must match and
`whole_process_ram=1` must attest the sealed process stack/heap, including SDK
descriptor/query/dequant/workspace allocations made inside the old body.
The scalar companion acquires the same provider's exclusive lease with actual
query_tokens, worker count, logical KV groups and complete tensor spans, then
rechecks CSR before entering that body. It does not fabricate resident selection.
Original mutex ownership is not recursively reacquired. Declined legacy grant
means ordinary GGML. OFF build retains all original branches. ON emulation keeps
the original feature/reference path but skips the preceding native-only quantKV
entry, so it cannot bypass provider denial to issue QBS/custom instructions.
Ordinary QBS outside this attention adapter retains its separate admission.

All groups have immutable plans, global Q/output offsets, local SDK query bases,
features and owned spans checked before query conversion or FULL. Destination
cannot alias inputs. The private vector allocation covers queries/workspaces;
the lease spans the entire call through every SDK RELEASE. A last-group miss
selects original native for the whole call, not a mixed resident retry. Both
routes retain the exact auto/explicit pairing policy. Once route fixation starts,
any SDK failure terminates; there is no fallback/replay. Query conversion can
accrue flags; resident hardware flags must not be conflated with preparation or
incoming sticky flags. Features and nonzero masks retain original native code,
not the Stage4 resident feature path.

## Counter Contract For Model Runner

After each synchronized call, `ggml_akv_resident_snapshot_v1(&c)` returns cumulative
uint64 fields (subtract successive snapshots; snapshot is not a timing probe):

| Field | Meaning |
| --- | --- |
| denied | no provider or unsupported actual CSR state, before INFO |
| unsupported | frontend type/shape/layout/threading/scope/alias decline |
| lease_denied | trusted provider declined ownership/memory |
| resident_calls / native_calls | whole-call fixed route, before first conversion |
| resident_groups / native_groups | SDK group returned OK on that route |
| completed | all groups returned OK |
| failed | SDK error after fixation; process must terminate, no retry |
| legacy_calls / legacy_completed / legacy_fallback | separately granted old body entry/result, NOT resident groups |

For a successful native call: delta completed=1, native_calls=1,
native_groups=actualKVgroups/chunks, resident fields=0. For a requested supported
resident call: completed=1, resident_calls=1, resident_groups=actual groups,
native fields=0. Always completed=resident_calls+native_calls for a successful
phase with failed=0 (legacy counters are separate). Prefill/unsupported/quantized-KV
phases must be labeled legacy or fallback, not resident success. F16 positive cases
must have resident groups >0; all-fallback never passes the positive gate.

Optional `GGML_RISCV_AKV_TRACE=1` emits one completed-call record:
`GGML_RISCV_AKV_RESIDENT_V1 route=resident|native requested=0|1 groups=G dimension=D tokens=T`.
Original AKV aggregate executed/groups counters are updated for these calls.
These counters are NOT hardware work/retirement. Runner must additionally bind
the final ELF/provider/model/launcher and compare actual QK/PV/context opcode
counts against shape-derived counts, reject unexpected native/emulated routes,
and independently check all logits/CSR. No timing or board claim follows.

## Tests

`python3 -B test_overlay.py --output <fresh signoff stage5_ggml_overlay_host_...>`
archives SDK f500 and da56. Host control fixture uses real GGML entry + archived
SDK plan/features/admission and counting stubs for execution/conversion. This
proves denial, control, lease, group preflight, fallback and counters only;
it is explicitly not numerical/native instruction evidence. GNU objects and
CMake configure and seven objects compiled with actual generated flags validate
the SDK/core/leaves/platform/GGML integration closure without launching model/EDA
workers. This is not a complete linked GGML library or a runnable provider.
