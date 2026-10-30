# Register-PV integration and guarded-entry evidence

## Model integration before guarded-entry promotion

Qwen2.5-1.5B and Qwen3-1.7B both passed actual llama.cpp/GGML OFF/ON model
comparisons. Each uses Q4_K_M model weights, Q4_0 and Q8_0 K-cache runs, Q8_0
V-cache, and three inference steps per format. Grouped Prefill stays enabled
in both modes. Qwen2.5 uses a four-token prompt; Qwen3 uses the captured
cross-tile prompt from its model test.

Each model compares 911616 logits bit-for-bit and checks identical tokens,
FCSR and VCSR. The ON mode has 112 successful Register-PV Decode calls; the
OFF mode has 112 original Decode calls. Each mode has 56 Prefill calls.
Together this is 1823232 paired logits, not a measured model speedup.

Qwen3 run: `verification/out/register-pv-qwen3-model-20261028-02`.
Independent replay accepted the log and all 978 sealed input hashes.

- Result SHA256: `88d415c689e1a731613936898db1233e3cea0e6557d862f02f7e4c28907f81ee`.
- Log SHA256: `31237ed759a6350e6579f54bab0b7ba39a13bd39957779e42f7f43d078f6a99f`.
- Executable SHA256: `642b8380dff875adf6f269d5b19d6c7e2fba5443a3960cd10e1d85dfe0cee093`.

Qwen2.5 provenance is in `register_pv_qwen25_model_acceptance_20261028.md`.

## Guarded-entry RTL measurement

`verification/out/register-guarded-q4-vcs-20261028-01` passed output equality,
protocol and immutable-input checks, followed by independent summary replay.
The complete-call Qwen3 query19/D128/GQA2/20-token Q4_0-K/Q8_0-V pair gives:

| Implementation | Trial cycles | Mean cycles |
| --- | --- | ---: |
| Existing shared RVV | 48041, 47730 | 47885.5 |
| Register-PV with early guard | 43434, 42717 | 43075.5 |

Speedup is 1.1116644x; cycle reduction is 10.0448%. This supersedes the
unguarded point as evidence for the guarded implementation. The previous
unguarded candidate mean was 42007.5 cycles. The new candidate is approximately
2.54% slower than that earlier binary, so zero overhead is not claimed.

Accepted offload mixes match the unguarded candidate for vector load (130),
store (52), vset (71) and arithmetic (363). Other offloads rise from 26 to 28.
The counts cover UART windows, not exactly the cycle ROI. Different code
layout and scalar execution are not isolated by these counters; assigning the
entire cycle delta to CSR reads would be unsupported.

- Result SHA256: `368198a6bc396b6bb9486ccabef1b2fbe0429990e34d8a174473b5c3c6f97e10`.
- Log SHA256: `2dcc0f957f1f5ab96e1b8265a561165d69232ff146ddf7599c6d3fbece30ad4f`.
- ELF SHA256: `c9717a62a1ba9701e3f2a995e6e289e28dc620c5898d8af267fd6a2ceb15a6e0`.

## Final integration state

The shared `register_pv/entry.c` now uses the measured guard implementation;
the source-identity test permits only its include-path/comment relocation.
The GGML build selects this public entry rather than compiling the internal
runtime alone. The option remains OFF by default; ordinary fallbacks remain.

After promotion, the fresh two-model campaign
`verification/out/register-pv-final-models-20261028-01` completed PASS. It
rebuilt both library configurations and ran the two model comparisons
concurrently. Both guarded-entry model executables passed all 911616 logit
comparisons, selected-token/CSR equality and actual-path checks. Total paired
logits are 1823232. No RTL was changed in this integration step.

An independent final replay reran both log checkers, checked the stage-receipt
hashes and verified 985 unique sealed inputs. Pipeline result SHA256:
`f7971ad525a05f9ef97d3248993e1c6f0bf99388d859ad4aab462a5e5ef68508`.

| Final model | Executable SHA256 | Log SHA256 |
| --- | --- | --- |
| Qwen2.5 | `b13fc006c5ba9fe93b3dc8f6a1e6a194cb573c653d8265d2be66b19b636ec155` | `9a8c9083f9154b715a265de38e782b8835fd788808c67eed0f2c2d5f2e50b6ef` |
| Qwen3 | `1d1ba84fd403c9a278991997d2b48305f38cc7b7c3bb54b19b4b55521ad13df4` | `ef0ba6928302d4118b88330e2ce7f7540e63d6993b9f150fd2cbb96f5e490e52` |

These model runs verify functionality, not end-to-end hardware speed. Their
linked libraries include the guarded entry, unlike the earlier unguarded model
receipts. The option remains disabled by default pending wider deployment;
the original RVV fallback is retained.
