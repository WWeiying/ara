# Bounded cross-group V reuse: experiment, not production

## Motivation and measured scope

The production Prefill executor groups up to eight query/head rows. Within a
group it decodes each visible V token once and applies that value to every
participating row. It resets the panel context for the next group and decodes
the same earlier V tokens again. This is software decode work, not additional
QBS arithmetic. No RTL change is proposed at this stage.

The schedule audit uses the accepted real Qwen3 capture, checks its identity,
and reads all mask rows rather than inferring visibility from allocated KV
capacity. Both Q4_0-K and Q8_0-K captures use Q8_0 V, D=128, GQA=2, eight KV
heads, twenty queries, and prefix lengths 1 through 20. Physical KV capacity is
256, but it is not the number of visible tokens.

| Scope | QBS commands, unchanged | PV row updates, unchanged | Original V decodes | Cached V decodes |
|---|---:|---:|---:|---:|
| Existing queries 16..19, one KV head | 4 | 148 | 20 | 20 |
| Proposed queries 0..7, one KV head | 8 | 72 | 12 | 8 |
| Entire captured operator | 160 | 3360 | 480 | 160 |

These counts are schedule-derived, not RTL performance results. The old
four-query benchmark has only one group and cannot demonstrate this benefit.
It remains useful as an overhead control. No speedup or DRAM traffic reduction
is claimed from these counts.

## Candidate and numerical contract

`value_cache_candidate.h` is an isolated host-test prototype. Cache the first
32 decoded V tokens, reset the valid mask at each KV head and each invocation,
and decode later tokens through the original callback. Cache state must not
survive a call or cross heads. Input tensors remain immutable during a call.
Mark an entry valid only after successful decoding. A failed decode must be
retried rather than using partially written data.

Do not change QK grouping, causal visibility, online Softmax order, PV update
order, or output scatter. On a hit, copy exactly the decoded float bits into
the existing value buffer. This preserves signed zeros as well as ordinary
values. The candidate does not reorder floating-point accumulation.

The public native decode callback is arbitrary. It is NOT automatically safe
to omit repeated calls: a callback could update state or raise exceptions.
Future integration must use an explicit, reviewed pure-decoder capability or
a specialized entry tied to the known Q8_0 decoder, with a conservative path
for other bindings. Do not change the meaning of generic bindings silently.

For the existing `q8_0_value.h` decoder, admission rejects nonfinite F16
scales. Signed INT8 to F32 conversion is exact. A finite F16 scale has at
most 11 significant bits; multiplying by an INT8 magnitude requires at most
18 significant bits, within F32 precision. The nonzero product magnitude is
also within the normal F32 range. This explains why the admitted arithmetic
need not raise new FP flags; it is not a substitute for RISC-V execution
tests. The decoder changes vector configuration, which its C callers already
treat as caller-clobbered. Tests must still verify sticky FFLAGS and VCSR.

## Resource and performance limits

The fixed-size prototype reserves 32 KiB of float payload (32 x 256 x 4),
plus metadata, even for D=128. Only 16 KiB is populated at D=128. A later
dimension-packed workspace could allocate exactly that smaller amount; the
current prototype must not be described as allocating only 16 KiB.

Each first decode adds a cache store; each hit adds a cache load and output
store. The latter replaces decompression, not all memory work. Scalar memcpy
can make the candidate slower even with fewer decode calls. Long prefixes
reuse only their first 32 tokens; do not extrapolate the short-prefix savings
to long-context attention. Full-call cycle measurements must include these
copies, cache reset/fill, admission, and workspace handling under equivalent
conditions. Compare the single-group control as well as multi-group cases.

## Completed checks

- Three Python schedule tests, including independently enumerated visits for
  nonmonotone prefixes longer than 32: PASS.
- Source-pinned capture re-audit:
  `verification/out/prefill-value-reuse-audit-20261029-02.json`.
- Host cache test under Clang AddressSanitizer and UndefinedBehaviorSanitizer:
  3,912 lookups, D=32..256, three KV-head identities, nonmonotone prefixes,
  tokens beyond cache capacity, bitwise output and padding checks, failed-fill
  retry, invalid dimensions, and reset isolation: PASS.
- Host executable:
  `verification/out/prefill-value-cache-host-20261029-01/test`.

The host test uses a deterministic mock decoder to test storage and control.
It does not establish Q8_0 decoder equivalence, complete attention output
equivalence, RTL correctness, or performance. Production code is unchanged.

### Whole-executor host differential

`value_cache_sources.py` now derives a candidate executor from canonical
`execute.h`, with exact single-anchor checks on transformations. It retains
the same admission, QK scheduling, online update and output-scatter code.
The additional caller-provided pure-decoder identity is an explicit
attestation, not automatic proof of callback purity. This API remains confined
to the experiment; the generic production bindings have not changed.

`value_cache_host.py` runs both the original executor fixture and its candidate
against the per-query reference. The fixture uses two KV heads, five queries,
GQA=3, D=96, nonmonotone prefixes 1/33/65/32/20, and a seven-row final group.
Every output byte and untouched padding agree. Actual mock-decoder calls fall
from 260 to 196, consistent with a 32-token cache. It also checks invalid last
queries, workspace overlap and size rejection before callbacks, failure on
the first command, and failure after one completed group without incorrect
fallback or output writes. Missing decoder eligibility rejects before reading
the request. Host exception flags match with an initially set sticky flag.

Latest accepted evidence:
`verification/out/prefill-value-cache-executor-20261029-04/result.json`.
ASan and UBSan were enabled. This verifies complete host fixture output using
the QBS reference model and a simple exact quantizer/decoder, not real GGML
quantization or RISC-V execution. The next gate remains real-input native
execution and cycle measurement.

Preserved attempts: `-01` exposed an overbroad test-source substitution and
failed compilation; `-02` passed without exception checks; `-03` demonstrated
that the reference model clears host flags for each command. For `-04`, the
test's command adapter restores preexisting flags after the reference call,
emulating sticky command flags. Neither the reference model nor production
code was edited to obtain this result. No failed attempt is labeled PASS.

## Promotion gates

1. Derive a candidate executor from canonical production sources; retain the
   original executor as the paired reference. Explicitly enforce decoder
   eligibility. Test all outputs, failure propagation, admission before side
   effects, KV-head resets, and prefix/group tails.
2. Use real Q4_0-K and Q8_0-K captures with Q8_0 V. Include at least two groups
   and the one-group control. Check bitwise paired outputs, reference
   tolerance, flags, exact QBS command counts, and actual decode invocations.
3. Run bounded ABBA VCS comparisons on the reviewed current RTL image, with
   independent directories and pinned inputs. Include all execution costs;
   do not use callback counts or QEMU timing as speedup evidence.
4. Integrate into the shared llama.cpp helper only after reproducible benefit
   and model-level equivalence. Retain generic/fallback behavior. If copying
   costs dominate, reject the candidate rather than promote a counter-only win.

No synthesis, PPA change, or new hardware storage is required by this proposal.
