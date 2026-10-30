# Actual GGML Backend Memory Bounds

`software/akv/experimental/quantized_kv/ggml_memory.h` supplies the memory-range
part of the future GGML adapter. It does not install a backend or issue an
accelerator instruction. The existing public-entry VCS tests remain unchanged;
their caller verifies bare-metal extents through the ELF/image contract rather
than invoking these GGML backend APIs. Real runtime integration must account
for this additional wrapper work as well.

## Why Allocation Size Is Not Tensor Size

GGML can place Query, K, V, mask and output in one backend allocation. Returning
the remaining allocation bytes for every tensor makes their ranges appear to
overlap even when their actual tensor data is disjoint. Conversely, accepting a
shape-derived range without checking the allocation could admit an out-of-bounds
view. Both questions need separate checks.

For a supported contiguous inner block, the helper computes:

```text
row_bytes = ne[0] / block_elements * block_bytes
tensor_span = row_bytes + sum((ne[i] - 1) * nb[i], i=1..3)
```

Every dimension and arithmetic step is checked before narrowing or addition.
The storage units are F32=4/1, F16=2/1, Q4_0=18/32 and Q8_0=34/32 bytes/elements;
unknown types, invalid block multiples and incorrect inner strides are rejected.
The resulting span is a conservative bounding interval, including stride gaps,
not a promise that arbitrary row layouts are executable. The common selector
still proves the actual allowed row/head layout and rejects harmful aliases.

The helper obtains the real backend's host accessibility, allocation base and
size, then checks that the complete tensor interval fits without pointer wrap.
It uses the tensor's actual data pointer, so a nonzero view offset is included.
An unassigned view buffer can resolve through an existing view owner, with a
bounded traversal to reject cycles. No range is enlarged to force admission.
On failure, output sizes/context remain unchanged.

Host accessibility does **not** establish cacheability, coherency or arbitrary
platform memory attributes. The caller's `normal_memory` assertion is preserved,
never inferred or forced true. A caller that cannot establish the supported
normal-memory contract must leave it false and use the ordinary path.

## Real Allocator Tests

`test_ggml_memory.cpp` uses actual `ggml_init`, tensor/view constructors,
`ggml_flash_attn_ext`, the CPU buffer type, and backend allocation APIs. It does
not substitute fake GGML tensor definitions or mock the allocation methods.

The test links the sealed real host GGML libraries from the original capture
build. Library/artifact hashes and capture receipts are checked. The public
headers used by compilation must match both the capture's original pinned
headers and the current runtime headers byte for byte, preventing an assumed
cross-version ABI match. All identities are checked again after execution.

There are 96 positive cases: D32/128/256, GQA groups1/3/6/8, one/two KV heads,
capacity33/128, and Q4_0/Q8_0 K. Each uses a genuine nonzero-offset Q8_0 V view
with a gap between heads, and a single real shared allocation. The resulting
sizes equal GGML's own tensor byte counts, and mapping plus shared admission
succeeds without false aliases. Output data remains untouched.

Each case also checks seven invalid extent descriptions (672 rejections total):
allocation-end overrun, pointer before allocation, stride overflow, zero extent,
unsupported type, incomplete quantized block and cyclic view ownership. It checks
failure-without-context-modification and verifies that `normal_memory=0` remains
zero and is rejected by the common selector. GCC and Clang ASan/UBSan execute the
same cases; counts are not doubled when reporting distinct test scenarios.

```sh
cd verification/akv/quantized_kv
python3 -B -m unittest test_ggml_memory -v
```

These are real GGML **allocation, metadata and admission** tests. They do not
execute the Attention graph, custom instructions or an LLM, and are not RTL
coverage or a new model/performance acceptance claim. The actual backend
dispatch, collective multithreaded admission and complete model checks remain
separate gates.
