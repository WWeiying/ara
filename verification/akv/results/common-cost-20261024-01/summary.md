# Completed Public-Entry Attention Comparisons

All cycle columns are sums of two measured trials within the same ELF.

| K Format | Comparison | Ordinary Cycles | Candidate Cycles | Speedup |
| --- | --- | ---: | ---: | ---: |
| q4_0 | ORIGINAL_DECODERS | 4,248,081 | 1,387,385 | 3.061934x |
| q8_0 | ORIGINAL_DECODERS | 4,229,050 | 1,396,517 | 3.028284x |
| q8_0 | BOTH_RVV_DECODE | 2,578,265 | 1,096,039 | 2.352348x |

Accepted comparisons: 3/6. Missing entries are not classified as failed or accepted.

These contiguous-operand results include mapping and admission, not K gathering or backend allocation queries. Both-RVV uses the same V decoder on each side; V reuse and QBS still change together. Do not label it a pure hardware ablation or a whole-model speedup. Do not subtract cycles across different ELF layouts.
