# GGML Operator Composition And Real-Graph Functional Check

## Entry Contract

`software/akv/experimental/quantized_kv/ggml_entry.h` composes the previously
tested pieces into one GGML-facing function:

```text
actual FLASH_ATTN_EXT tensor
  -> metadata/type/shape/thread/precision mapping
  -> real host-backend allocation and view bounds
  -> shared C runtime admission
  -> caller-provided QBS executor + production GGML callbacks
```

It does not register an operator hook, enable a runtime flag or probe custom
instructions. The caller explicitly supplies capabilities, normal-memory policy,
callbacks and aligned workspace, and must preserve tensor/input lifetimes and
the required platform serialization. Disabled, reference or non-single-worker
calls are rejected before backend memory inspection. Per-call tensor mapping
and data admission are not duplicated in a second arithmetic implementation.

The report distinguishes `mapping_reason`, `memory_verified`, and
`runtime_called`. The last flag means only that the shared C function was called;
it is **not** a hardware execution counter. Native command attempts, completed
groups, V decodes and executor status remain in its nested native report.

The integer return status must not be treated as a Boolean handled/not-handled
result:

- `OK`: result complete.
- `FALLBACK`: rejected before arithmetic callbacks/output modification; the
  caller may execute ordinary GGML.
- `EXECUTION_FAILED`: some work/output may already exist; report the failure,
  do not silently retry ordinary GGML.

The caller supplies disjoint valid report/workspace objects, as with the common
runtime API. This helper is not an untrusted-pointer or concurrency validator.

## Actual GGML Graph, Not A Handwritten Reference Schedule

`test_ggml_graph.cpp` constructs a real GGML `FLASH_ATTN_EXT` graph and allocates
its tensors through the actual CPU backend. It loads the unchanged original
Qwen Query, quantized K/V, mask and captured model output, then calls
`ggml_graph_compute_with_ctx` to compute the ordinary result. It subsequently
calls the new composed entry on those same actual tensor objects.

The entry uses the production GGML Q8_0 CPU `from_float` and `to_float` traits,
not a synthetic integer-scale quantizer. PV callbacks are thin calls into the
original `vec.h`, compiled with the recorded host CPU target flags. The common
C runtime is the same implementation used by native benchmark preparations.
The injected executor is explicitly the independent host `qbs_ref`, not native
instructions or QEMU. It preserves the caller's host rounding/sticky state while
merging command exceptions; the command oracle itself clears its temporary FP
flags internally.

The sealed GGML libraries, build manifest, original source dependencies and
public header ABI are checked before and after testing. Current public headers
must be byte-identical to the headers pinned by that library build. No external
source, library, existing experiment or active VCS input is modified.

## Accepted Host Results

Both original K=Q8_0/V=Q8_0 and K=Q4_0/V=Q8_0 captures pass with **all 12 Query
heads, both KV heads, D128, visible KV128 and capacity256**. Each produces 1,536
outputs, repeats the shared path twice, executes 16 reference commands per call,
quantizes 12 Query rows and decodes 256 V rows. Repetitions are bit-identical,
workspace guards remain intact, and all original Q/K/V/mask bytes are unchanged.

| K format; V always Q8_0 | Ordinary GGML vs captured gold: max absolute error | Shared entry vs gold/ordinary graph |
|---|---:|---:|
| Q8_0 | 0 | 1.40070915e-6 |
| Q4_0 | 0 | 9.65595245e-6 |

Every individual output passes the already established absolute 0.004 plus
relative 0.002 criterion; no tolerance is widened. Host CPU graph arithmetic is
not the RVV instruction-order baseline, so these host differences must not be
confused with the separately accepted bit-identical paired RVV/QBS RTL results.

Additional checks cover:

- A hole in the mask: entry rejects before quantization, decode or reference
  command issue, leaving every output byte unchanged. Ordinary GGML subsequently
  computes the supported fallback graph successfully.
- An injected executor failure on command three: one tile already has partial
  work; the entry propagates `EXECUTION_FAILED`, attempts exactly three commands
  and does not compute/retry the untouched second KV group.
- Disabled entry: no memory validation or native runtime call is performed.

GCC and Clang ASan/UBSan pass the same tests. The existing shared GGML libraries
are not rebuilt with sanitizers; the new adapter/runtime/reference/test and thin
PV wrapper are instrumented in the sanitized run. Two inherited missing-prototype
warnings from the unchanged thin PV source are diagnostic only, not arithmetic
or linker failures; the wrapper is not edited while native consumers are sealed.

```sh
cd verification/akv/quantized_kv
python3 -B -m unittest test_ggml_graph -v
```

## Remaining Gates

This proves host operator composition, real captured data and fallback/error
semantics. It is not a whole-model invocation, a live installed GGML dispatch,
a native instruction test or a performance measurement. The two ongoing VCS
public-entry experiments independently measure the original six-head group
including mapping/admission. They do not include these newly added backend
allocation-query calls. Actual backend deployment must account for that wrapper
overhead too, retain ordinary RVV/F16 AKV paths and pass model execution before
being promoted for model use.

A separate default-OFF private backend hook now passes actual native-QBS Linux
QEMU graph dispatch, rather than this host test's direct helper call. Both real
formats pass all12 heads/two KV heads and ordinary fallbacks; a further actual
GGML projection/Attention/projection graph passes persistent-AQ interleaving.
See `ggml_live/README.md` and `ggml_interleave/README.md`. These are functional
integration results, not whole-model or RTL performance evidence. The archived
external source snapshot preserves the existing private checkout changes and
does not automatically commit or push that checkout.
