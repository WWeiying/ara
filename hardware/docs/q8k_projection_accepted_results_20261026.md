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

The single-output quantizer layout candidate remains uninstalled. Its modest
complete-projection benefit is measured, but it must undergo its own shared
helper integration and actual-build regression rather than being silently
folded into this context-policy change.
