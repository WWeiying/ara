# Strided-Cache RTL Performance Inquiry

This is the timing successor to the accepted GGML graph and full-model
functional gates. QEMU results are prerequisites, never a source of latency.
It uses the existing VLEN1024, four-lane, 16MiB simulation image; no RTL build
or hardware change is needed.

## Matched Workload

Both paths process the original six Query heads sharing KV head 0, D=128,
with 128 visible tokens in a physical two-head, capacity-256 cache. The builder
permutates every original captured K/V row into token-major storage without
changing payload bytes. The other physical KV head remains present; only the
selected group's 768 output values belong to this inquiry.

- Ordinary: production RVV Q4_0/Q8_0 dot products, head-major online Attention.
- Candidate: shared quantized runtime, QBS DIRECT groups, bounded K gathering,
  and cross-head V reuse.
- Both use the identical RVV Q8_0 V decoder, original Query quantizer and
  production scale/mad primitives, with identical compiler FP policy.
- ABBA order compares two executions of each mode within one ELF.

The candidate timer includes GGML metadata mapping, strict runtime admission,
Query quantization, K-panel copies, QBS execution, online Softmax and PV.
Four K panels copy 17408 bytes for Q8_0 K or 9216 bytes for Q4_0 K per
candidate trial. These copied bytes are not a measured AXI/DDR traffic count.

This standalone timer does not include GGML graph dispatch, allocation,
backend host-buffer extent discovery, or cold device-capability discovery.
Its speedup is for QBS plus changed scheduling, not a pure hardware ablation
or a whole-model speedup. Both the data-layout change and the decoder match
are explicit in the build/result metadata.

## Checks and Ownership

`build_strided_attention.py` preserves the accepted ordinary objects, verifies
the full captured row mapping, checks ELF bounds and the simulator contract,
and rejects scalar V decoding, reference arithmetic or an archived main in the
final disassembly. It only builds; it never starts a simulator.

`run_strided_attention.py` requires checked terminal PASS from the new model
gate, independently replays its log and checks the shared implementation. It
then verifies the pinned ELF/image, runs one bounded VCS inquiry, and checks:

1. Every output against the independent original capture tolerance.
2. Recorded paired differences, repeated output bits, guards, FCSR and VCSR.
3. Exact candidate panel/copy counts and absence of candidate work in baseline.
4. Sixteen actual QBS hardware records against the RTL counter schema.
5. Independent vector/backend/AXI protocol evidence bound to this ELF/image.
6. Pre/post source, helper, artifact and executable identities.

The worker directly owns its simulator under a systemd user service. Each
format has a separate build, output and log directory. It writes terminal
`result.json` and `status.json`, including failure/timeout, without changing
the original experiments. A measured slowdown is retained, not turned into a
functional failure or silently omitted. Each invocation is bounded at three
hours; no repeated polling or automatic rerun is used.

The model prerequisite's full QEMU source inventory was checked by its own
completed worker. The VCS worker pins the accepted model evidence and matching
shared implementation, not all unrelated QEMU build sources again. Its own
VCS software, imported local checkers, protocol tools and image remain pinned.
