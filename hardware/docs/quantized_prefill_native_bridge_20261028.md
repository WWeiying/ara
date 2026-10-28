# Prefill grouped-command bridge

The real Qwen3 host replay established scheduling equivalence, but its QK
callback called individual GGML dot products. The next intermediate gate
connects the same scheduler to `akv_quant_native_qk`, preserving the existing
QBS descriptor construction, status handling, and synchronous executor ABI.
This bridge remains under `verification/`; it is not production admission.

## Alignment boundary

Q8_0 uses 34 bytes per block. For D=32 or D=96, consecutive rows alternate
between four-byte and two-byte aligned addresses. Uniform Decode grouping
usually starts M4/M2 groups on even rows. Different causal prefixes can split
those groups and produce an odd starting row. Forwarding that pointer directly
would violate the command activation alignment requirement.

`native_prefix.h` therefore copies only an unaligned command's activation rows
into a bounded aligned scratch buffer. Aligned groups pass through unchanged.
The maximum scratch allocation is 4 * 8 * 34 = 1,088 bytes, with no heap
allocation and no additional quantization. The executor must consume the
activation synchronously before returning. D=128 uses 136-byte rows and does
not require this copy. This is a software workspace, not new hardware storage.

## Verified behavior

Run:

```sh
python3 verification/akv/quantized_kv/prefill/test_native_prefix.py
```

GCC and Clang UBSan both passed 24 combinations: D=32/96/128, Q4_0/Q8_0 keys,
and four eight-row prefix patterns spanning lengths 1 through 65. The tests
reuse the existing QBS descriptor reference executor and fixture, check
bit-exact agreement with row-major online computation, preserve padding,
verify V decode counts, reject requests past a row's prefix without command
issue, and stop immediately on executor failure. Candidate paths exercised
40 alignment copies. No hardware timing or native instruction execution is
claimed by this test.

## Remaining integration boundaries

The bridge assumes already validated, disjoint buffers with bounded lifetimes
and contiguous K rows. A production Prefill call must validate every query and
mask row before starting output, retain terminal errors after execution begins,
and support the existing strided-K panel path. That path currently keys its
panel cache on exact token count; different causal prefixes can otherwise
regather the same tile repeatedly. Its reuse policy must be considered in the
complete-call benchmark, not hidden behind a prepacked input assumption.

The next gate is real captured data through native grouped QBS commands,
followed by paired VCS timing that includes preparation and output work.
