# Profile-bound tail acceptance and H/S/B continuation

The four completed tail runs are unchanged. The original combined gate rejected
them because it required identical quantized Query bytes across both KV formats.
That condition does not describe these captures: Q4 and Q8 came from separate
model executions, whose preceding generated tokens already differ. Pair baseline
and candidate within each profile and capture; do not assume that changing KV
quantization leaves later model activations unchanged.

| Profile | Complete F32 Query capture SHA256 | Used head slice |
| --- | --- | --- |
| Q4_0 K / Q8_0 V | `8ce68ffcab546c82be541eca2182feb692c2f4910100aab3ba6130b7117efd93` | First six of twelve heads |
| Q8_0 K / Q8_0 V | `c8605130e06a3034a0d833fd7fa8618e338f47e46908e0b2ed6bf0ca45f8430f` | First six of twelve heads |

Each full capture is 6144 bytes, shape `[128,1,12,1]`. The test uses the first
3072 bytes; Q8_0 quantization produces six 136-byte rows. Prefixes 5 and 33 must
have identical Query and provenance within the same profile. Between profiles,
neither equality nor inequality is a requirement.

## Checks retained and added

`combine_v2.py` delegates every individual raw log, golden, QK, image, source-pin
and independent protocol check to the immutable predecessor `checked_run`.
It additionally binds the profile's capture to the actual ELF `attention_query`
symbol, the linked production quantizer object and the captured layout. An exact
rational RNE reference reconstructs the exported Query bytes for this finite,
normal captured dataset. It does not claim a general quantizer or fflags oracle;
out-of-domain inputs are rejected, not approximated.

The combined schema requires four distinct runs, both profiles, both prefixes,
12 trials, eight native calls and 24 QBS commands. Actual records and Query bytes
are retained. Original incomplete TIMEOUT records remain prior failures. The new
acceptance tag is `TAIL_SPLIT_COMBINED_PASS_V2`; a V1 consumer must reject it.
No old report, source pin or RTL file is rewritten, and no kernel rerun is needed
to repair this aggregation error.

## Continuation

`threeway_v2.py` keeps the original H/S/B execution and numerical checker, using
the V2 tail APIs and recording the correct acceptance tag. `coordinate_v3.py`
keeps the original owner identity, raw prerequisites, combined audit, dual
preflights and direct-owned service launch. It redirects only the combine script
and downstream worker, retaining the simulator's 10800-second maximum. The
cancellation-safe pidfd wait is reused from `coordinate_v2.py`.

The `fast_hex` build changes only untimed output formatting, not the six-trial
scope or stdout contents. It does not guarantee a run under three hours or
support comparing an old ELF's absolute latency to the new ELF as an optimization.
All H/S/B ratios must use the same executable and its actual measured results.

Host checks:

```sh
python3 -B -m unittest \
  verification.akv.quantized_kv.tail_split.test_combine_v2 \
  verification.akv.quantized_kv.tail_split.test_v3_routing -v
```

The combined gate can be run offline with `combine_v2.py --runs RUN1 RUN2 RUN3
RUN4 --output FRESH`. A V3 coordinator requires a fresh launch receipt/output,
explicit Q4/Q8 build directories and a new unit prefix. A failed coordinator's
output and one-launch claim must not be reused. Scheduling inspection is not
functional execution, and service creation is not simulator confirmation.
