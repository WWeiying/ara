# QBS Runtime Library

`software/qbs` is the runtime-neutral software contract for the `Xaraqbs`
extension. It deliberately contains no GGML tensor types, GGUF model names, or
llama.cpp operator identifiers. llama.cpp is the first adapter, not part of
the QBS ABI.

## Contract boundary

QBS computes packed quantized matrix products with the mathematical shape

```text
A[M,K] x W[N,K]^T -> C[M,N]
```

The descriptor identifies an exact weight profile, activation profile, packed
layout, and one hardware tile. A profile denotes an exact byte layout and
numerical formula. A runtime may use a profile in either of two ways:

1. map an exactly compatible native format directly to the profile; or
2. convert/repack its format into the canonical QBS profile at model-load time.

Matching only bit width or group size is not sufficient. For example, another
runtime's blockwise INT4 format is not `Q4_K` unless its scale, correction,
subgroup, and packed-bit semantics are identical.

Framework adapters do not need to embed the compact hardware profile numbers.
They name an exact canonical byte/numerical contract with a stable 64-bit
`QBS_*_ENCODING_*` ID and call `qbs_device_bind_encodings`. The common runtime
then resolves that software encoding pair to the profile IDs implemented by
the queried device. Encoding IDs never enter a descriptor or instruction, so
this indirection has no command-stream or hardware-cycle cost.

The simple block contracts also expose framework-neutral aliases whose names
state the relevant layout, for example
`S4_B32_F16_SPLIT_NIBBLE_OFFSET8` and
`S8_B32_F16_TWOS_COMPLEMENT`. These aliases mean exact byte compatibility, not
"any symmetric INT4/INT8." The K-quant and nonlinear-codebook encodings retain
their GGML-specific contract names because relabeling them as generic would be
unsafe; GGUF is a common container for these blocks, not their numerical ABI.

This gives QBS two distinct kinds of portability:

- **operator and shape portability:** the public operation is a quantized
  `A[M,K] x W[N,K]^T` tile, independent of model and graph names;
- **format portability through an explicit contract:** exact formats map
  directly, while other formats require a runtime-owned, validated load-time
  conversion. Similar bit width alone never enables a direct path.

The current profiles are canonical GGML-compatible encodings, not a claim that
all INT4 or INT8 encodings share their byte ABI. Adding another ecosystem does
not require changing planning or issue code, but it may require a new exact
profile or a persistent model-load conversion.

The current v1 profiles cover four useful semantic families:

- affine K-block formats: `Q2_K`, `Q4_K`, and `Q5_K`;
- symmetric K-block formats: `Q3_K` and `Q6_K`;
- simple 32-element block formats: `Q4_0`, `Q5_0`, and `Q8_0`;
- nonlinear codebook format: `IQ4_NL`.

They pair with `Q8_K` or `Q8_0` activations. Unsupported formats remain on the
runtime's ordinary RVV or scalar path.

This is an intentional v1 core rather than an exhaustive quantization list.
It covers the complete `Q2_K` through `Q6_K` weight family, three simple
32-element block formats, and one nonlinear codebook format while reusing one
descriptor and execution path. It does not natively cover `Q4_1`/`Q5_1`, the
remaining IQ and TQ families, MXFP4/NVFP4, or runtime-specific GPTQ/AWQ block
layouts. Those formats require measured demand plus either a new exact profile
or a validated conversion target. The descriptor has a four-bit weight-profile
field, so profile IDs are a versioned architectural resource, not a substitute
for a runtime format registry.

## Public layers

| Layer | Public operation | Runtime responsibility |
|---|---|---|
| ABI | generated `qbs_abi.h` | use stable encoding IDs; pass resolved profile/layout IDs only to the common planner |
| Discovery | `qbs_device_query` | call only after ISA/platform discovery proves `Xaraqbs` exists |
| Encoding binding | `qbs_device_bind_encodings` | assert an exact source/converted encoding ID pair |
| Metadata | `qbs_*_profile_info` | inspect the resolved canonical profile |
| Packing | `qbs_repack_weight_r4`, `qbs_pack_activation_m4` | cache persistent weights and prepare activation groups |
| Planning | `qbs_plan_create`, `qbs_plan_next` | supply logical M/N/K and source storage layouts |
| Execution | `qbs_execute`, `qbs_execute_with_options` | provide buffers/workspace; optionally bind one explicit activation-context token |
| Native ISA | `qbs_native_info`, `qbs_native_execute_command` | establish extension presence and handle runtime policy |

The planner owns M1--M4 grouping, N tiles and tails, K segmentation, descriptor
construction, and split-K accumulation. It supports row-major and R4 weights,
row-major activations, and the grouped M4 representation used by multi-token
GEMM. It performs all shape, profile, layout, workspace, and capability checks
before issuing the first command.

A successful `qbs_plan_t` is immutable and can be cached for repeated calls
with the same shape and device contract. `plan.workspace_bytes` is a validated
scratch-capacity upper bound for that plan. Runtimes should reuse scratch
storage where their allocator model permits it; partial-only split-K plans need
only a small accumulator tile, while activation gather space is reserved only
when at least one command can actually require a copy. Planning and scratch
management never add hardware commands.

Once `qbs_execute` calls the command executor, a memory or architectural fault
is an execution fault and must be propagated. A runtime must not silently
retry the same operation on a fallback path after a possibly visible command.

## Explicit activation-context reuse

`qbs_execute()` is the compatibility path and always emits `DIRECT` commands.
`qbs_execute_with_options()` can eliminate repeated Q8_K activation reads
between output tiles when `qbs_plan_supports_activation_context()` is true.
The current device contract is deliberately narrow: one context, `M=1`,
row-major Q8_K, at most 16 K blocks (`K<=4096`), no split-K or gather, and at
least two output tiles. An eligible execution emits `FILL`, zero or more
`REUSE` commands, and a final `RELEASE` command.

The adapter owns the token:

```c
const qbs_execution_options_t options = {
    .use_activation_context = 1,
    .activation_context = {
        .context_id = 0,
        .generation = generation,
    },
};
```

Generation is not inferred from addresses. The adapter must assign a new
generation to a new logical activation and serialize the complete
`FILL...RELEASE` sequence against other users of the same hardware context.
Hardware validates ID, generation, activation profile/layout, M, and K-block
count. A mismatch is an execution-visible context fault, never a silent
DIRECT fallback. Failed or aborted FILL commands do not publish a context.

Capability or plan rejection occurs before issue and may select DIRECT or the
runtime's ordinary RVV implementation. Once the first QBS command has issued,
the adapter must propagate faults rather than retrying partially visible work.

## Runtime adapter pattern

An adapter for GGML, ONNX Runtime, ExecuTorch, or another engine should remain
small and follow the same sequence:

```text
runtime tensor metadata
  -> exact canonical encoding ID or load-time conversion target
  -> qbs_device_query and qbs_device_bind_encodings
  -> qbs_plan_create with the resolved device profile pair
  -> persistent R4 weight cache
  -> runtime activation quantization / M4 packing
  -> qbs_execute
  -> ordinary runtime fallback for any pre-issue rejection
```

Runtime-specific tracing, allocator integration, thread scheduling, tensor
lifetime, and fallback selection stay in the adapter. Profile geometry,
capability parsing, packing, tile planning, and instruction execution stay in
this library so adapters cannot drift from one another.

`examples/runtime_adapter.c` demonstrates the boundary with fictitious runtime
metadata. One format is an exact mapping, a same-bit-width foreign INT4 format
is explicitly marked for load-time conversion, and an unsupported floating
format remains on fallback. It contains no GGML declarations.

See `PORTING.md` for the exact-mapping checklist, conversion and fallback
rules, adapter ownership boundary, and the validation required before enabling
a new runtime or format.

For CMake integration, add this directory and link the namespaced target:

```cmake
add_subdirectory(path/to/software/qbs qbs-runtime)
target_link_libraries(runtime_backend PRIVATE qbs::runtime)
```

An installed library exports the same target through
`find_package(qbs_runtime CONFIG REQUIRED)`, so an adapter does not need to
compile QBS sources into its own backend target.

Before calling `qbs_execute`, an adapter supplies actual weight, activation,
and output capacities. The common layer validates all three before issuing its
first command. Once issue begins, an architectural or memory fault is returned
as an execution error and must not be hidden by retrying the operation.
Weight and activation bases must meet the queried alignment contract, output
and workspace must be naturally aligned for `float`, and packing-helper source
and destination ranges must not overlap.

## Building and testing

```sh
make -C software/qbs check
```

The host test checks all nine weight profiles, both activation profiles,
capability-contract decoding and profile-pair filtering, R4 padding,
Q8_K/Q8_0 M4 packing, exhaustive representative M/N/K planner combinations,
mixed M4 plus row-tail storage, bounded gather workspace sizing, split-K command
accumulation, explicit buffer capacities and alignment, and reduced devices
with narrower M/N/K capabilities and row-major-only layouts. It also checks
activation-context eligibility, FILL/REUSE/RELEASE sequencing, token bounds,
single-tile rejection, and that the legacy execution API remains DIRECT.
