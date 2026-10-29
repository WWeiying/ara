# Register-PV Qwen2.5 model acceptance

The actual llama.cpp/GGML Register-PV integration passed the Qwen2.5-1.5B
Q4_K_M model OFF/ON comparison. This is functional acceptance in QEMU with the
QBS instruction model, not an RTL end-to-end performance measurement.

## Scope and result

| Item | Tested value |
| --- | --- |
| Model | Qwen2.5-1.5B-Instruct, Q4_K_M weights, 28 layers |
| Prompt | `The quick brown fox`, exactly 4 tokens |
| K-cache formats | Q8_0 and Q4_0, separate runs |
| V-cache format | Q8_0 |
| Comparison | Register-PV disabled versus enabled in the same linked program |
| Prefill | Grouped quantized Prefill enabled in both modes |
| Generation | Three inference steps per K format and mode |
| Logits checked | 6 paired output arrays, 151936 words each; 911616 bit-exact comparisons |
| Selected tokens | 34208, 916, 279 for both K formats and both modes |
| Architectural checks | FCSR and VCSR equal between paired modes at every step |
| Completed Decode calls | 112 in each mode |
| Completed Prefill calls | 56 in each mode |

The trace checker requires the Register-PV enabled field to match the requested
mode and successful completion. The OFF mode uses the original shared RVV
Decode implementation, not Register-PV. The receipt's historical field
`register_completed_per_mode=112` counts the corresponding dispatch trace
records in each mode; it does not mean the Register-PV mechanism ran while OFF.
Actual Register-PV-enabled completions are 112 in the ON mode.

Processes for the two modes initialize independently, avoiding cached
environment-variable state. All logits must be finite and paired bit-exact;
the test also rejects early end-of-generation, incomplete output records,
guest failure and missing backend dispatch. Identical tokens alone would not
satisfy acceptance.

## Provenance

Run: `verification/out/register-pv-qwen25-model-20261028-01`.
Libraries: `verification/out/register-pv-ggml-build-20261028-02/on`.
Both the worker and a separate replay accepted the result. The replay reran
the log checker and verified all 980 sealed input hashes.

- Result SHA256: `303c12fc2a80d5f43f9adc4b00789e96f283ad0624954463266a8d5c78237ff8`.
- Log SHA256: `115d0cc516337d5761596e941df2ec5964e65c0078ea523ecba02fcbcfbb17ee`.
- Executable SHA256: `70bf599c3cf3b7b45748737619879168d14cf478d9fc65b05c10400bb52c8b95`.

This run uses the promoted runtime before the successor early-CSR guard.
Ordinary model entry has zero vstart. The separate nonzero-vstart rejection
finding and tested successor are recorded in
`register_pv_entry_guard_review_20261028.md`; do not attribute that correction
to this sealed executable. Qwen3 acceptance and guarded-entry RTL performance
remain separate pending results at the time of this record.
