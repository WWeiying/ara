# Register-PV context-length check

The 20-token Q4_0 K pair has a verified 12.21% cycle reduction. Before
promoting that candidate, this successor tests a different captured query:
query 7 of the same Qwen3-1.7B input, with its actual eight-token causal prefix.
It is not a truncated query-19 computation or a synthetic zero-filled cache.

| Property | First accepted point | Context successor |
|---|---:|---:|
| Query position | 19 | 7 |
| Visible tokens | 20 | 8 |
| Query heads / D | 2 / 128 | 2 / 128 |
| K / V | Q4_0 / Q8_0 | Q4_0 / Q8_0 |
| QBS commands per trial | 1 | 1 |
| K panel rows / bytes | 20 / 1440 | 8 / 576 |
| Output words per trial | 256 | 256 |

The successor reads query 7, mask row 7 and golden output row 7 from the
audited real capture. Cache capacity/layout and VLEN1024 remain unchanged.
ABBA compares current shared RVV with register-PV in a single ELF, including
admission, query quantization, K gathering, QK, online PV and normalization.
The same output bit equality, captured golden tolerance, floating/vector CSR,
guard and independent protocol gates apply. Extra per-call guards remain timed.

Implementation is under `verification/akv/quantized_kv/register_pv/context_pair/`:

- `native_main.c` has a bounded compile-time query index, 0--19.
- `build.py` rebuilds all 17 objects from a fully hash-checked current pair
  recipe, replacing only the main harness. No archived object is reused.
- `check_native.py` checks the actual query/mask length, QK work, copied K bytes,
  and the correct captured golden row. It cannot accept the original 20-token
  accounting as evidence for the eight-token run.
- `test_check.py` covers positions 0,7,19, both K formats, wrong query/golden,
  failed trials and wrong work accounting.
- `run.py` retains the canonical SoC/image/independent protocol checks and
  three-hour simulation bound.

Build directory: `verification/out/register-pv-context8-q4-build-20261028-01`.
Planned separate run directory:
`verification/out/register-pv-context8-q4-vcs-20261028-01`.
Planned service: `register-pv-context8-q4-20261028-01.service`.
Only a final PASS receipt with all four trials establishes its performance;
no result is asserted in this preparation note. The 896 schedule cases and
288 full-runtime reference cases complement this point but are not substitutes
for actual RTL timing at a second context length.
