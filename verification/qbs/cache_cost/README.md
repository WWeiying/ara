# Prepared activation cache cost

Question: after parallel group-sum quantization, is exact-byte cache reuse still
cheaper than quantizing the same real four-row activation three times?

`native.cpp` uses captured Qwen projection activations (4 x 1536 FP32) and the
accepted independent 7008-byte Q8_K M4 golden buffer. Four ABBA trials compare
three actual parallel quantizations against one quantization plus two cache
hits. Both paths produce three separately checked outputs, preserve FCSR/VCSR,
check guards and input immutability. The cache path includes fill and final
release in the measured region. The same producer is used in both paths.

This is preparation-only, not full GGML dispatch or matrix execution. Its
three consecutive calls do not reproduce cache disruption by intervening
matrix work. Use it to establish the cost breakdown, not model speedup or
authority to remove input-byte validity checks.

Expected cache counts per reuse trial: one producer, one miss, one store,
two hits, 49152 requested comparison bytes and 45600 copied payload bytes.
Requested comparison bytes are not physical memory traffic.

The builder recompiles all selected objects with GNU tools and pins captured
inputs, transitive source dependencies and tools. No archived object reuse.
The runner uses the separately reviewed retirement SoC admission, checks build
and image identities, validates every output byte on target, verifies the
reported signature against the independent golden, and runs the unchanged
CVXIF/backend/AXI checker. Fresh output directories are mandatory.

This experiment does not modify production runtime behavior or RTL. Both
algorithms are already present in the runtime; no new cache optimization is
claimed before measurement.
