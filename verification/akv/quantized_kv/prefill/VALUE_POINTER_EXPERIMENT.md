# Direct V-row consumption candidate

This is a successor experiment, not a change to the running copy-based VCS
pair or the production runtime. `value_pointer_sources.py` derives its
executor and scheduler from the canonical sources with checked substitutions.

## Changed behavior

The scheduler obtains a `const float *` for each token, instead of requiring
every decoded row to be copied into online scratch. The first cacheable visit
decodes directly into the cache; subsequent visits return that row. Tokens
32 and above continue using the original scratch buffer. Every participating
query row consumes the selected pointer before the next token callback.

The returned pointer never escapes the synchronous token loop. Reset remains
per KV head and per invocation, and invalid entries become valid only after
a successful decode. A callback failure or null returned pointer terminates
execution without treating partially written output as a fallback. The
generic production callback interface is unchanged. Decoder eligibility is
the same explicit pure-decoder contract as in the copy prototype.

This removes both cache-fill copies and hit copies from V transport. It does
not remove output scatter or K-panel copying, nor does it reduce QBS command
counts or reorder Softmax/PV arithmetic. The fixed workspace still reserves
32 KiB of decoded V payload plus metadata. No RTL change or speedup claim is
made at this stage.

## Verification

Command:

```sh
python3 verification/akv/quantized_kv/prefill/value_pointer_host.py \
  --output verification/out/prefill-value-pointer-executor-20261029-01
```

PASS with ASan/UBSan. The unchanged acceptance fixture checks the original
and pointer candidate against per-query reference outputs for two KV heads,
five queries, GQA=3, D=96 and nonmonotone prefixes 1/33/65/32/20. It exercises
both cached rows and scratch reuse beyond token 31, a seven-row tail group,
all output and padding bytes, sticky host flags, rejection before callbacks,
and partial-output failure behavior. Decode counts remain 260 versus 196.

Evidence and full source pins:
`verification/out/prefill-value-pointer-executor-20261029-01/result.json`.
The host decoder/quantizer are fixture implementations. Actual RVV decoding,
real-capture output equivalence, and complete-call RTL cycle benefit remain
unverified for this successor.

The Q4/Q8 copy-based VCS workers are independent sealed controls. Do not change
their source files, output records, or candidate identity. A future native
pointer comparison must be a new build/run against the original executor;
beating the copy candidate alone is insufficient for promotion.
