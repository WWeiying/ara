# Native Quantized Attention in GGML and Model Generation

## Execution Path

The opt-in private adapter handles a single Decode query with Q4_0 or Q8_0 K
and Q8_0 V. Both the ordinary and candidate paths use the production GGML
Query quantizer. The candidate groups Query heads that share one KV head:

1. Quantize each Query head once.
2. For a strided K cache, gather at most 32 visible K rows into a bounded panel.
   Preserve every quantized byte. A contiguous cache skips this copy.
3. Reuse that panel for the group's M4/M2/M1 QBS DIRECT commands.
4. Decode each V row once and reuse it across the group's Query heads.
5. Keep each head's original token-order online Softmax and PV arithmetic,
   using the production scale/mad primitives and the RVV Q8_0 V decoder.

The adapter remains under the existing AKV whole-call lock and QBS DIRECT
serialization. It does not create, release or replace a projection's persistent
activation context. Failed admission uses the ordinary path; a command failure
after work starts is an execution failure, not a transparent retry.

This is a software scheduling extension using existing QBS/RVV hardware. The
scratch space is 13120 bytes, including the maximum 8704-byte K panel. It does
not add an RTL SRAM or require a new descriptor field or instruction.

## Functional Graph Gate

Accepted run:
`verification/out/akv-quantkv-ggml-strided-20261024-01-control`.

The test uses real captured Q/K/V values, two K formats, contiguous and
token-major physical layouts, 128- and 5-token visible prefixes, and repeated
native calls. It verifies physical backing bytes and strided tensor metadata;
it does not insert a contiguous-copy graph node before dispatch. All 16 native
calls and six fallback cases passed. The native calls issued 160 commands,
gathered 40 panels, copied 110656 K payload bytes and decoded 2128 V rows.
These are workload counts, not measured memory-bus traffic or RTL speedups.

Numerical checks cover all 1536 outputs per call, repeated bit equality,
paired FCSR/VCSR, the original capture tolerance where applicable, and exact
fallback equality. The original capture materialized K/V with `ggml_dup`;
the new fixture independently permutes the same bytes into live-cache-style
views before testing dispatch.

## Full-Model Gate

The successor worker is `run_model_strided.py`. It requires the checked graph
result, independently rechecks its raw log and source identities, and builds
the public llama.cpp model API with the same native adapter.

The fixed workload is Qwen2.5-1.5B-Instruct Q4_K_M, all 28 layers, four prompt
tokens and three greedy generated tokens. Each K format gets independent
ordinary/candidate contexts; V is Q8_0 in both. Projections use native QBS in
both modes, so this is an Attention integration comparison, not an ordinary
RVV-versus-whole-QBS-model performance test. Each trajectory consumes its own
previous generated token. Logits are compared only while the histories match.

The requested context is 128, but the runtime rounds it to 256. The checker
requires the actual context logs, not just the requested value in test markers.
Multi-token Prefill intentionally falls back. Both subsequent Decode steps
must execute native quantized Attention in every layer: 112 calls, 448 QBS
commands, 224 gathered panels and 128128 copied K payload bytes across the
two candidate generations. Native work and adjacent layout records are checked
in addition to tokens, logits and native projection coverage. Identical text
under fallback is not accepted as native coverage.

The background service is
`akv-quantkv-model-strided-20261024-01.service`; results are written to
`verification/out/akv-quantkv-model-strided-20261024-01-control`.
Only terminal `PASS` in both result/status files, with the pinned raw evidence
accepted, closes this functional gate. QEMU supplies no RTL latency, speedup
or power evidence. A separate paired VCS inquiry must include admission and
K gathering costs before deployment performance is claimed.

The prior model run remains FAIL: its text matched because quantized Attention
fell back. Its archived results are not overwritten or promoted by this gate.

The successor run completed with terminal PASS and accepted all 112 native
Decode calls and 448 commands. All four contexts generated token IDs
`34208, 916, 279` (` jumps over the`). The six paired logit comparisons had
maximum absolute difference, RMSE and KL equal to zero. This is a three-token
functional result for this prompt, not evidence of long-context quality or an
end-to-end speedup. The compact receipt is
`verification/akv/results/quantized-kv-model-strided-20261024.json`.
