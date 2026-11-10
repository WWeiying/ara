# Experimental Resident Attention Helpers

This is an explicit stage-3 candidate, not a default runtime path or a board
delivery. The capability remains zero. A validated experimental platform must
be identified outside these helpers; an ordinary AKV capability is insufficient.

## Complete Group Executor

`executor.h` declares `akv_experimental_attention_execute_v2_native`. Compile
`akv_v2_native_riscv.c` with `AKV_EXPERIMENTAL_RESIDENT_ATTENTION=1` and link
`qk.S` and `pv.S`. The macro defaults to zero and the new symbol is absent in
that build. Do not separately compile `pv_prepare.S`: `pv.S` includes it.
Existing public SDK entries retain their original selection even in the
experimental build.

The entry executes one immutable Decode group plan through the existing v2
core. It replaces only QK and PV arithmetic leaves. Context FULL/REFILL,
software scaling, masking, online softmax, cross-tile rescaling, RELEASE and
normalization keep their original order. It does not fuse Prefill queries or
replace the runtime's group planner.

| Admission | Requirement |
|---|---|
| Platform | Explicit availability, eligible memory, FS/VS enabled, four lanes and VLEN1024 |
| Ownership | Exclusive ownership across every group and tile through RELEASE |
| Data | F16 Q/K/V, D64/D96/D128, one query token and supported v2 row-view plan |
| Arithmetic | RNE and vstart zero; no CSR is changed to obtain admission |
| Schedule | Plain scores after normal feature handling; no effective refill overlap |
| Memory | Caller validates all group spans, workspace capacity and nonaliasing before execution |

The executor snapshots options and device information, checks actual
VLEN/FRM/VSTART only after trap-safe admission, and preflights full/tail tile
maps before mutating the workspace or issuing FULL. Each tile uses local query
pairs starting at 0, 2, 4 or 6. An odd final head uses H1, and a final context
tile can contain fewer than 64 tokens. Longer contexts use REFILL and existing
software tiling, not larger hardware storage.

The `automatic` argument selects the existing explicit/environment policy (0)
or native-auto policy (1). Failed resident admission retains that exact policy;
it does not force a slower generic kernel or make an invalid plan executable.
`platform_admitted` and `whole_call_owned` are required even for this native
fallback. Prefill, segmented D256, non-F16 data and unsupported active score
features do not select the resident leaves. Once execution starts, errors are
terminal: there is no partial replay or automatic fallback retry.

No GGML path discovers or enables this entry automatically. Formal runtime
integration and board deployment are separate stages.

## QK Leaf

`qk.S` issues one resident QK command, then stores only the active FP32 scores.
The helper uses the same 256-byte head stride as the existing Attention
workspace and supports one or two heads. The command reads Q and K from the
already-loaded context; it does not reload a query pointer from memory.

| Argument | Meaning |
|---|---|
| `scores` | Writable FP32 output, with 64 elements reserved per head |
| `tokens` | Active tokens in the current tile, 1 through 64 |
| `heads` | One or two consecutive query rows |
| `dimensions` | Head dimension 64, 96 or 128 |
| `query_base` | First resident Q row, with `query_base + heads <= loaded_queries` |

The caller must own a valid resident context with matching D and sufficient T,
check the hardware capability/configuration, and satisfy the FP-state, rounding
mode and vstart requirements before issuing the command. `qk.h` checks argument
geometry only; it does not establish ownership, check pointer capacity or
advertise device support. Do not route unsupported calls here.

Each output is a positive-zero FP32 accumulator followed by dimension-ordered
FP32 FMAs on exactly widened F16 inputs. The helper does not apply attention
scaling, masks, softmax or output normalization. Those remain in the caller.
Vector registers v0 through v3 and caller-saved integer temporaries are
clobbered. The command preserves architectural VL/VTYPE; the subsequent normal
RVV stores configure VL/VTYPE as needed, as existing software helpers do.

`verification/performance/resident_rvv/qk_shared/test_sdk_helper.py` checks host
geometry and the real GNU-assembled opcode/store fields. It is not a substitute
for executing this helper on the candidate RTL.

## PV Leaf

`pv.h` declares `akv_experimental_resident_pv(probability, accumulator,
old_scale, tokens, dimensions, heads)`. The respective head strides are 256 B,
512 B and 4 B. It accesses only T probabilities, D accumulators and one scale
per active head; H1 never accesses the next head. The inputs must match an
already-loaded resident V context.

The leaf rounds scales and probabilities to F16, rescales existing F16
accumulators, then issues token-ordered F16 FMAs. It stores active results back
to the padded workspace. Preparation and FMAs can accrue flags but do not clear
the caller's prior flags or change its rounding mode. This is a scalar-ABI
assembly function with caller-saved scalar/vector clobbers, not a vector-ABI
function. It does not issue FULL/REFILL/RELEASE, normalize outputs or establish
a whole-call memory fence. See `pv.h` for the complete clobber and memory contract.

## Evidence And Reproduction

- `test_executor.py`: host route/stub tests, GNU object checks and default-OFF
  equivalence; not native arithmetic execution.
- `verification/performance/resident_rvv/qk_shared/full_call/`: same-image,
  equal-work VCS Attention comparison against panel4 QK and rotating-register PV.
- `verification/performance/resident_rvv/qk_shared/full_call_sdk/WORKFLOW.md`:
  actual SDK functional firmware and independent protocol/work checks. Its OFF
  call is a fallback check, not the optimized performance baseline above. Use
  the corrected `flags_v2` sources identified there, not historical helpers.
- `verification/performance/resident_rvv/qk_shared/RESULTS.md`: scoped receipts,
  measured cycles, source identities and remaining acceptance work.

The paired prototype measures one real Qwen3 D128/H2/T137 call at 1.20842x.
That result does not establish model-wide speedup, all-shape benefit or native
SDK acceptance by itself. Use the applicable receipt, not host-test counts, to
decide which execution scope has passed.

Actual native SDK execution separately passes in
`stage3_attention_sdk_vcs_20261110_01/result.json`: requested-OFF/ON original
D128/H2/T137 and a distinct derived D96/H6/KV2/T65 case, 1,088 bit-exact FP32
values, FCSR 3/11/3, actual SDK entries, work, independent protocol and post-run
identities. This closes stage-3 candidate validation without changing the
default route, capability or board delivery.
