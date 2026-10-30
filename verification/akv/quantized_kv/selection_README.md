# Quantized KV Runtime Admission

`software/akv/experimental/quantized_kv/selection.h` is a pure, experimental
Decode selection contract. It is not yet installed in GGML and does not enable
a fast path. It issues no custom/vector instructions, does not allocate memory,
and leaves the destination data and returned plan unchanged on rejection.
Existing F16 AKV admission, ordinary RVV and GGML fallbacks are untouched.

## Why Separate Admission Is Necessary

The existing AKV hardware consumes F16 KV data. The quantized-KV candidate
instead uses existing QBS for QK and ordinary RVV for online Softmax and PV.
Consequently, F16 cache admission cannot authorize this path. In particular,
QBS row-major N32 reads consecutive K rows: a padded/interleaved token stride
cannot be silently treated as a tight row, even though each row is individually
valid. V can remain strided because the production decoder is called per row.

The selector takes explicit byte extents/strides, dimensions, exact encoding
identities, a previously discovered QBS device contract, and execution policy.
There is no model-name dispatch and no assumption that all formats called Q4
have the same payload representation.

| Property | Initial candidate admission |
|---|---|
| Operation | One Decode query token, one sequence, uniform GQA groups |
| K encoding | Exact QBS Q4_0 or Q8_0 weight encoding ID |
| V encoding | Exact Q8_0 encoding ID |
| Query/output | Contiguous F32 elements, independently specified head strides |
| Head dimension | 32 through 256, divisible by 32 |
| Heads | At most 256 total Query heads, 1--8 Query heads per KV head |
| Cache | At most 65,536 tokens; bounded head-by-capacity product |
| Mask | Exact +0 visible prefix followed by F16 negative infinity; nonempty |
| K layout | Tight token rows, disjoint heads, even base/strides |
| V layout | Proven-disjoint head-major or token-major rows, including padding |
| Features | No sinks, no additive head bias, no Softcap |
| Execution | Explicit opt-in, normal memory, VLEN=1024, vstart=0, FRM=RNE |

An admitted metadata shape is not evidence that native performance or model
accuracy has been validated for that shape. Actual full-path RTL performance
testing currently uses the captured D128/GQA6/KV128 cases.

## Checks Before Any Side Effect

1. Reject disabled/unknown policy and unsupported execution state before reading
   tensor contents. Require the exact device numerical/descriptor contract,
   profile compatibility, layouts, M/N/K/result bounds and alignment. The
   needed M/N follows the real groups4/2/1 and N32/tail schedule.
2. Prove every declared address extent fits without integer/address wraparound.
   Prove row disjointness for the supported head-major/token-major layouts.
   Reject output overlap with Query, K, V or mask backing storage.
3. Verify the entire mask representation before selecting a visible prefix.
   A hole, negative zero, finite additive value, NaN, or empty prefix falls back.
   No hidden K/V row is scanned merely because capacity is larger than length.
4. Inspect Query and visible K/V scales through their raw IEEE bits. Signaling
   NaNs are rejected without performing floating-point comparisons or adding
   an invalid exception during admission.
5. Check each original Q8_0 Query block's maximum magnitude. Zero is supported.
   A conservative nonzero range from 2^-120 through 127*65504 avoids reciprocal
   overflow and nonfinite stored F16 scales in the production quantizer.
   Positive score scales above 2^64 fall back as an additional conservative
   bound on scaled QK intermediates. These are candidate-domain guards, not
   modifications to the original quantizer.
6. Commit the returned plan only after every check passes. Once a downstream
   command or output update has happened, an execution failure must propagate;
   the caller must not silently restart the ordinary path over partial output.

The caller owns memory validity, read/write permissions, normal-memory identity,
serialization and prevention of concurrent input mutation. C metadata checks
cannot discover these properties from a pointer alone. Quantized Query scratch,
descriptor and score workspace still need caller-owned aligned storage.

## Test Evidence

`python3 -B verification/akv/quantized_kv/test_selection.py` checks:

- 8,192 positive metadata combinations across dimensions, GQA ratios, KV heads,
  visible-prefix/tile tails, both K encodings and both V layout orders.
- Three additional positive numerical-boundary/hidden-row checks.
- 65 explicit rejection scenarios, including capability/ABI mismatch, pointer
  overflow, insufficient extents, aliased rows/output, unsupported features,
  mask holes, numerical range, signaling NaNs and alignment.
- 32,768 small row-layout combinations: every admitted layout is checked
  independently by enumerating pairs of byte intervals for overlap.
- Ordinary GCC and host Clang AddressSanitizer/UndefinedBehaviorSanitizer runs,
  plus C++17 header compilation for eventual GGML adapter use.

`test_selection_capture.py` validates metadata and unmodified file hashes for
both frozen Qwen2.5 captures, then executes admission on their actual Query,
K, V and mask bytes. It uses a reference device capability table, not a native
hardware query; output memory must remain unchanged.

System GCC's sanitizer linker stub points to a missing runtime on this host.
The sanitized test therefore explicitly uses `/usr/bin/clang` and its installed
compiler-rt, not ZCC. No compiler installation or global environment is changed.

## Remaining Integration Gate

The selector's scans have a real cost. The currently queued whole-Attention
inquiries test the computation schedule, not this newly added selection code.
Any subsequent GGML integration must include admission cost in its full-path
measurement, validate all workers consistently before dispatch, preserve
F16 AKV and ordinary fallback routing, and retain default-off selection until
numerical and performance evidence supports promotion. Host admission counts
are not VCS test counts or RTL coverage percentages.
