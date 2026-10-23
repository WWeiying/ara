# REFILL overlap in complete shared-runtime Attention

## Decision

Keep `AKV_REFILL_OVERLAP=0` by default. The restricted RTL admission mechanism
works, but moving REFILL in this real Attention schedule does not improve
operator latency. Do not extrapolate the isolated probe's 6.48% reduction to
complete Attention, and do not enable the candidate just because it is correct.

The test uses genuine captured llama.cpp Qwen2.5 data: D128, twelve query heads,
two KV heads, one query and a 128-token causal prefix. All 1536 outputs are
checked. Two complete shared runtime translation units, compiled with schedule
OFF/ON, are linked into one ELF. The same tensors, output and workspace are
used for all four timed calls; the mode order is OFF/ON/ON/OFF.

## Measured result

| Trial | Schedule | Complete cycles | Retired instructions in timed interval |
| --- | --- | ---: | ---: |
| 0 | OFF | 107236 | 28350 |
| 1 | ON | 108986 | 28630 |
| 2 | ON | 108489 | 28630 |
| 3 | OFF | 106930 | 28350 |

The sum is 214166 cycles OFF and 217475 ON: speedup 0.984784x, or 1.5451%
more cycles. This is an incremental schedule comparison on the same AKV RTL,
not AKV versus ordinary RVV and not end-to-end model performance.

Every trial has checksum `a7bc111334389dea`, FCSR=3, VCSR=5 and 774 successful
AKV commands. Each has 558 AR transactions, 8392 response beats, 526 logical
ranges, 134272 external payload bytes and 131072 replay bytes. There are no
fault records. The preceding separate-ELF pair had different tensor addresses
and 32 extra page splits on ON; the fixed-address experiment removes that
traffic difference and still observes a slowdown.

## What the cycle evidence establishes

`analyze_refill_attention_abba.py` reads the actual GNU symbol table and locates
the two `rdcycle` PCs in `main`. The returned CSR values in the retirement trace
must reproduce each printed cycle count exactly. It partitions the surrounding
retirement gaps by current-PC function and counts retired instructions. This
gap partition is diagnostic, not an exclusive or causal hardware stall breakdown.

The `[AKV_REFILL_ORDER]` trace shares the vector trace's cycle and architectural
sequence domain. For each REFILL, the analysis finds the last six older
`vfmacc.vf` requests and their final observed VRF write cycles:

| Mode | REFILLs observed | First AR relative to older last write |
| --- | ---: | --- |
| OFF | 4 | 181--182 cycles after |
| ON | 4 | 23 cycles before |

Thus real arithmetic/read overlap exists; it was not lost during integration.
However, its observed window is only 23 cycles per REFILL, while each refill
occupies about 2085--2087 command cycles. The standalone probe had a different
arithmetic tail and cannot predict this operator's benefit.

The ON path retires 280 extra instructions per complete Attention call. Of
these, 272 are in the C native schedule, two in descriptor validation, and six
net extra instructions in the PV assembly entries. The source adds workspace/
KV alias validation, overlap eligibility and next-tile scheduling. The raw
instruction counts demonstrate added execution work, not merely noise in the
final cycle counter. Function-placement and cache effects may also contribute;
the available trace does not uniquely identify their hardware stall cycles.

The result supports keeping the serial shared schedule as the deployed path.
A successor should create a substantially larger useful overlap window or
remove repeated intermediate/data movement, rather than repeatedly tuning a
short tail or weakening alias/fault checks to obtain a favorable result.

## Reproduction and scope

- Run: `verification/out/akv-refill-attention-abba-20261023-01/`.
- Build: `verification/out/akv-refill-attention-abba-build-20261023-02/`.
- Analysis receipt: `results/refill-attention-abba-attribution-20261023.json`.
- Functional/performance receipt: `results/refill-attention-abba-20261023.json`.

```bash
python3 verification/akv/analyze_refill_attention_abba.py \
  --run verification/out/akv-refill-attention-abba-20261023-01 \
  --build verification/out/akv-refill-attention-abba-build-20261023-02 \
  --output /absolute/new/attribution.json
```

No new simulation is needed for this attribution. Source/image/input hashes,
raw hardware subtotals, independent boundary checks and the four numerical
checks must all pass before analysis. This experiment does not establish a
new REFILL fault-retry contract: a failed refill still requires reestablishing
context and restarting with clean software state, not retrying PV accumulation
blindly. Architectural fault integration remains a separate gate.
