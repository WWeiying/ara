# Accepted complete-projection measurements and runtime integration

Both exact-comparison runs completed their original full shapes and ABBA
sequences. Unlike the earlier truncated/timeout runs, their application,
independent QEMU comparison, input pins and strict UVM checker all passed.

| Experiment | Original cycles (two trials) | Optimized cycles (two trials) | Speedup | Cycle reduction |
| --- | ---: | ---: | ---: | ---: |
| Single-output Q8_K preparation layout | 245395 | 242971 | 1.009976x | 0.9878% |
| Q/V/K activation-context reuse | 374776 | 334780 | 1.119470x | 10.6720% |

The first candidate reduces preparation cycles by 12.1434%, but preparation
is only about 8% of this full projection. The second reduces preparation
cycles by 66.5603% by preparing the shared activation once instead of three
times. Neither change significantly speeds up QBS arithmetic itself. These
two effects must not be multiplied or claimed as full-model speedups.

## Geometry and comparison

All data come from captured layer-0 Qwen2.5-1.5B Q4_K_M Decode tensors. Q is
M1/N1536/K1536 with Q4_K weights. The reuse test executes Q/V/K in the captured
runtime projection order, with N1536/256/256 and Q4_K/Q6_K/Q4_K weights. Their
F32 activation buffers are exactly equal. Output profiles and dimensions are
unchanged; all 64 native commands per trial remain. Intervening graph matrix
operations are excluded from this isolated reuse timing, but were present in
the separate model-level functional test.

Both sides use the same ELF within each experiment. Complete preparation,
descriptor construction, native execution and output stores are timed.
Captured-output tolerance checks, exact paired output/CSR checks, input
integrity and canaries run outside the timed regions. Full weight images are
compared bytewise against independent read-only copies at group boundaries.

## Strict acceptance evidence

| Evidence | Single-output projection | Mixed-profile Q/V/K |
| --- | ---: | ---: |
| CVXIF requests / responses | 16684 / 16684 | 25234 / 25234 |
| Backend allocations / completions | 12247 / 12247 | 17777 / 17777 |
| AXI AR / completed reads | 17216 / 17216 | 23592 / 23592 |
| AXI AW / matched B | 216 / 216 | 304 / 304 |
| UVM issues | 0 | 0 |
| Pending / aborted transactions | 0 / 0 | 0 / 0 |

Evidence directories are `verification/out/q8k-projection-exact-20261026-01`
and `verification/out/q8k-qkv-exact-20261026-01`, respectively. Each contains
`result.json`, `manifest.json`, QEMU results, raw VCS/vector traces and
`soc/uvm_result.json`. The raw VCS log SHA256 values are:

- Projection: `c2b15756921a8f400dbc2554ae6d3116be70b93fa650f0258db9169c3c926d6c`.
- Q/V/K: `f936beca35013f9d19927a2eb96367a3c4bfcafc381d4823daddf86f67e6bf87`.

Historical incomplete runs remain incomplete; these new results do not
rewrite their status.

## Production integration

The higher-benefit float-gap context policy has now been applied to the actual
local llama.cpp `arch/riscv/qbs.cpp`. Before editing, its complete previous
contents were archived in
`verification/out/q8k-float-gap-integration-20261026-01/qbs.before.cpp`.
`compile_installed_float_gap.py` requires that the entire new file equal the
reviewed patch applied to that snapshot, then compiles that actual source
with its production compile record. It does not generate a private policy
variant. The scoped distributable patch remains in `software/qbs/integrations`.
Other dirty llama.cpp changes were retained and are not staged or committed.

The production-TU graph run is
`verification/out/q8k-float-gap-installed-graphs-20261026-01`. It links the
new production object with compatible frozen remaining runtime objects and
uses the real cross-op-context OFF/ON configuration, not the private test
switch. It checks safe F32/F16 gaps, in-place writes, hidden custom side
writes, input epochs, numerical outputs, CSR and context counts. It completed
with PASS for all 16 graph executions: quantizations 16/12, skips 0/4, equal
output/CSR pairs and balanced context lifetimes. Six host policy/alias/patch
tests also passed after installation. This closes the production-TU graph
gate; a fresh model run with the production object remains separate work.
A full clean rebuild of every library is not claimed.

The single-output quantizer layout optimization is now installed. Its shared
implementation is now `software/qbs/ggml/q8_K-decode-sums.h`. The helper keeps
the measured algorithm exactly, changing only private function/include-guard
names. `test_shared_decode_helper.py` verifies this textual equivalence.
`compile_shared_decode.py` rebuilds the entire quantizer translation unit with
production flags and requires all 177 `quantize_row_q8_K` instruction opcodes
to match the measured candidate object; this check passed in
`verification/out/q8k-decode-shared-compile-20261026-01`.

The helper only sums complete 16-byte quantized groups. It leaves signed-max
selection, scale computation, floating-point conversion, output layout and
scalar fallback unchanged. Its empty assembly constraint keeps the narrow
source distinct from the wide reduction result; it emits no instruction and
does not change architectural state. The caller requires standard RVV with
VLEN at least 128 and VL containing complete groups, as in the existing Q8_K
block quantizer. The separate VLEN128/256/512/1024 functional tests remain
the numerical evidence, not the opcode comparison alone.

The actual runtime source and helper were installed after verifying that they
were not inputs to the running context-policy model gate. That model uses its
sealed pre-existing quantizer objects. A snapshot of the old source is in
`verification/out/q8k-decode-integration-20261026-01/quants.before.c`.
`compile_installed_decode.py` checks the entire source delta and header bytes,
then compiles the actual source with production flags. All 177 quantizer
opcodes again matched the measured candidate, in
`verification/out/q8k-decode-installed-compile-20261026-01`.

`verification/out/q8k-decode-installed-full-20261026-01` completed PASS with
11520 checks using that actual production object. It tests VLEN128/256/512/1024,
12 input patterns, K=0/256/512/1536/1792/8960, five legal FRM settings and all
eight VCSR settings. Full block bytes, input preservation, canaries, subgroup
sums and FCSR/VCSR are checked against the separate old function. No private
candidate implementation is used for the optimized callee.

The context-policy installed-model gate also completed PASS in
`verification/out/q8k-float-gap-installed-model-20261026-01`: six comparisons,
911616 bitwise-equal logits, equal tokens and CSR, with equal native matrix
work. This gate toggles the real cross-op option OFF/ON with M4 preparation
fixed ON; unlike the earlier private test, it measures correctness of the
installed policy rather than isolating just the float-gap rule.

The two actual production objects still need a combined model regression.
Their separate acceptance results are not a substitute for this final
combination check, nor a full clean build of all runtime libraries.

The combined gate is now arranged in
`verification/out/q8k-combined-installed-model-20261026-01`. It explicitly
links both installed objects. Its baseline calls the old single-row quantizer
extracted from the pre-integration snapshot and disables cross-op reuse; the
optimized side calls the actual installed quantizer and enables reuse. M4
preparation, QBS/AKV settings and all arithmetic workload remain fixed.
This is a combined functional test, not an isolated incremental policy
ablation or model timing measurement.

The link-time wrapper records original/installed quantizer calls independently.
`combined_decode_gate.py` requires those counts to reconcile with all recorded
single-row preparations for each mode, rejecting missing, duplicated or
wrong-path dispatch records. It also preserves the six full-vocabulary,
token/CSR and native-work checks from the accepted model harness. Tests of
the dispatch checker and old-function extraction passed before launch. The
worker's final result must be inspected before reporting combined acceptance.
