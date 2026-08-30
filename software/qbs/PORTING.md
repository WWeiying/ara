# Porting a Runtime to QBS

This guide defines the integration boundary for runtimes other than the
existing llama.cpp adapter. It does not claim that any additional framework is
already integrated.

## 1. Decide whether a tensor is eligible

QBS accelerates a packed quantized linear operation:

```text
A[M,K] x W[N,K]^T -> C[M,N]
```

The runtime should keep its ordinary implementation unless all of the
following are true:

1. the operation is semantically a dense quantized matrix product;
2. the weight encoding maps exactly to a QBS profile, or the runtime has an
   explicitly validated model-load converter;
3. the activation can be produced in the profile's exact Q8 encoding;
4. tensor dimensions, storage, alignment, and device capabilities are valid;
5. the runtime can keep repacked weights alive for every command that uses
   them; and
6. the runtime can propagate an execution fault without retrying an operation
   that may already have changed architectural state.

QBS does not recognize model names, graph node names, framework tensor enums,
or quantization recipe filenames. Those remain adapter concerns.

It also separates two identifiers that must not be conflated:

- a 64-bit **encoding ID** is a stable software contract for exact bytes and
  numerical semantics and is what framework adapters exchange;
- a 4-bit **profile ID** is the compact device ABI used in descriptors and is
  obtained through `qbs_device_bind_encodings`.

This lets a future architecture version assign a different compact profile
number without making every framework treat that number as its format enum.

## 2. Classify the format relationship

Every runtime format must be classified into exactly one category.

### Exact mapping

Use a profile directly only when all of these properties match:

- block byte count and element count;
- payload bit ordering and signed-value reconstruction;
- subgroup boundaries and scale encoding;
- zero-point or min-correction formula;
- auxiliary metadata such as Q8_K `bsums`;
- activation pairing; and
- the QBS numerical contract expected by the application.

Matching names, nominal bit width, or group size alone is insufficient.

### Load-time conversion

Static model weights may be converted once into a canonical QBS profile and
then persistently R4-repacked. The runtime owns this conversion and must decide
whether it is:

- a byte-only permutation that preserves every represented value;
- an exact arithmetic conversion into an equivalent encoding; or
- a requantization that changes represented values and therefore requires
  model-quality validation.

The common QBS library performs R4 layout conversion after a canonical
row-major profile exists. It does not silently reinterpret or requantize a
foreign format.

### Fallback

If neither an exact map nor a validated conversion exists, retain the
runtime's ordinary RVV, scalar, or device kernel. A rejected plan is a normal
pre-issue selection result, not a fatal application error.

## 3. Adapter responsibilities

| Adapter owns | Common QBS runtime owns |
|---|---|
| framework tensor/type mapping | canonical profile metadata |
| graph and operator eligibility | `qbinfo` capability decoding |
| persistent-weight cache lifetime | row-major to R4 repacking |
| activation quantization scheduling | row-major Q8 to M4 packing helper |
| allocator and workspace lifetime | M/N tails and K segmentation |
| thread scheduling and synchronization | descriptor construction |
| tracing and fallback statistics | checked command traversal |
| pre-extension ISA/platform discovery | native `qbinfo/qbexec` wrappers |

This split keeps framework policy outside the architecture library while
preventing profile geometry and command planning from being reimplemented in
every backend.

## 4. Minimal integration sequence

```c
runtime_binding binding = map_runtime_format(tensor.format);
if (binding.mode == FALLBACK)
    return runtime_default_kernel(...);

if (binding.mode == CONVERT_AT_LOAD)
    canonical = runtime_convert_and_validate(tensor, binding.profile);
else
    canonical = tensor.data;

qbs_device_t device;
if (!platform_has_xaraqbs() ||
    qbs_device_query(qbs_native_info, NULL, &device) != QBS_STATUS_OK)
    return runtime_default_kernel(...);

qbs_profile_binding_t resolved;
if (qbs_device_bind_encodings(&device,
                              binding.canonical_weight_encoding_id,
                              binding.canonical_activation_encoding_id,
                              &resolved) != QBS_STATUS_OK)
    return runtime_default_kernel(...);

qbs_repack_weight_r4(...);          // persistent model-load cache
runtime_quantize_activation(...);   // exact Q8_K or Q8_0 blocks

qbs_problem_t problem = {
    .weight_profile = resolved.weight_profile,
    .activation_profile = resolved.activation_profile,
    ...
};
qbs_plan_t plan;
if (qbs_plan_create(&device, &problem, &plan) != QBS_STATUS_OK)
    return runtime_default_kernel(...);

// Cache an immutable plan and reusable workspace for recurring shapes when
// the runtime's ownership and threading model permits it.

status = qbs_execute(&plan,
                     weights, weights_bytes,
                     activations, activations_bytes,
                     output, output_capacity, output_stride,
                     workspace, workspace_bytes,
                     runtime_command_executor, runtime_context);
if (status != QBS_STATUS_OK)
    return runtime_execution_error(status);
```

The fallback decision is made before `qbs_execute`. Once its executor callback
has issued a native command, a fault must be propagated; the adapter must not
silently execute the complete operation a second time.

The capacity fields are not inferred allocation sizes: pass the actual bytes
or elements available to each buffer. Keep packing-helper source and
destination ranges distinct, satisfy the queried base alignments, and keep the
plan, buffers, workspace, and callback context alive until the blocking call
returns. Do not modify a plan after `qbs_plan_create`; recreate it when shape or
device capability changes.

## 5. Framework-specific mapping expectations

| Runtime style | Likely adapter action |
|---|---|
| GGML/GGUF with one of the nine exact encodings | submit its canonical encoding IDs, bind, then persistently R4-repack |
| Runtime importing the same GGUF block ABI | verify ABI fields, then reuse the same encoding IDs; do not map by enum name alone |
| Exact S4/S5/S8 block-32 storage | use the precise framework-neutral encoding alias only when scale and bit-plane order also match |
| Generic groupwise INT4/INT8 with scale/zero point | usually a new profile or validated load-time conversion |
| QDQ or dynamically described quantization graph | fold constants and inspect exact quantization parameters before selecting QBS |
| Delegate-based mobile runtime | keep graph partitioning in the delegate; pass only eligible linear tiles to QBS |
| FP16/BF16 linear layer | ordinary RVV/device fallback; it is not one of the current QBS profiles |

An ONNX Runtime or ExecuTorch adapter can therefore reuse this library, but it
still needs framework-specific graph selection, tensor ownership, and format
mapping. The presence of this API is not evidence that those adapters exist.

## 6. Required validation for a new adapter

Before enabling a format by default, verify:

1. profile metadata and source tensor bytes agree for every block field;
2. direct mapping or conversion matches an independent scalar oracle;
3. M1, M2, M3, and M4 paths produce the expected outputs;
4. N tails, M tails, K segmentation, and output strides are correct;
5. R4 padding is never exposed as logical output rows;
6. MoE repack groups do not cross expert boundaries;
7. insufficient buffers and unsupported capabilities reject before issue;
8. execution faults are propagated without an unsafe retry;
9. fallback executes the runtime's established implementation; and
10. model-level quality is checked whenever conversion changes represented
    values or accumulation order.

`examples/runtime_adapter.c` shows the mapping decision, while
`tests/qbs_runtime_test.c` covers the framework-independent planner and buffer
contract. A real adapter must add its own format and model tests.
