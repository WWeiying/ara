# Derived GQA2 whole-Attention ABBA preparation

Build-only isolated candidate. No canonical source edits, production integration,
environment opt-in, simulator launch, or numerical/performance acceptance.
The existing focused pair gate and future whole-Attention gate remain necessary.

## Source and numerical contract

Use the original genuine Qwen2.5 KV128 Decode capture: F32 Q[128,1,12,1],
F16 K/V[128,256,2,1], with visible causal prefix128. Select original Q heads
0,1 for KVhead0 and6,7 for KVhead1, giving four total heads/GQA2 and512 outputs.
This is a derived subset, explicitly NOT a genuine Qwen3 Decode capture.
The original full capture blobs remain unchanged in the ELF. Query head selection
and RVV F32->F16 conversion happen at runtime within the measured region; the
two selected query rows are contiguous with256B stride. K/V retain original
physical head stride65536B and token stride256B, without repacking.

The app includes the canonical captured app to reuse its Q conversion helper and
configuration ABI. Its new entry selects the corresponding original golden heads
0,1,6,7 and checks every output with unchanged atol0.004 + rtol0.002*abs(expected),
including finite-value guards. All512 raw FP32 values must also match trial0
bitwise. FCSR must match trial0 with RNE and only valid flag bits, VCSR must be5;
flags are sampled before numerical checking. No expected checksum/flags are
invented before actual execution. Query/output/workspace guard regions total384B.

## Shared native code and admission

`software/akv/experimental/paired_heads/native_bench.c` includes the actual
canonical native C, with exactly two symbol redirects: generic F16 QK and PV
calls go through thin benchmark wrappers. OFF calls original generic assembly;
ON uses paired assembly plus an original generic one-real-head odd remainder.
Canonical softmax, F16 rounding, normalization, full/refill/release scheduling
and the existing six-head special path are unchanged. Refill overlap is OFF.

The single-thread benchmark entry takes an explicit0/1 mode; no getenv/global
external mode setter exists. It snapshots admission once per native call before
FULL. ON performs one real device query at that boundary, validates enabled
PANEL4/row/tail/D capabilities, and reuses the decision through all tiles and
head pairs. OFF skips this new capability query; the ON selector cost is included,
not hidden or added artificially to the baseline. Unsupported admission falls
back to canonical generics; the benchmark nevertheless rejects ON fallback via
`admitted_groups != 2`. Six-head D128 remains special, and D256 is not admitted.
The private selection state requires one synchronous caller and existing context
ownership; this is not a thread-safe production API. No fallback after issue.

Odd-head QK count remains floor(H/2)*(D/4)+(H%2)*D when the odd head uses the
original generic. Do not claim ceil(H/2)*(D/4) without a one-head PANEL4 helper.

## Timing and output protocol

OFF/ON/ON/OFF use one ELF and fixed buffer addresses. Timing includes device
query, active-prefix scan, selected-head F16 preparation, both plan creations,
per-call admission and both complete native Attention executions through
normalization/output stores and final scalar-extract/fence drain. Buffer poison
and workspace reset precede timing equally in all trials; golden comparison,
byte equality and hashing follow timing. This is not isolated QK timing or whole
model timing. FCSR/VCSR setup is outside the region in all modes.

```
AKV_PAIR_SUBSET source=qwen25_kv128 qheads=0,1,6,7 kvheads=0,1 outputs=512 derived=1
AKV_PAIR_TRIAL_BEGIN trial=<0..3> paired=<0/1>
AKV_PAIR_ATTENTION trial=<0..3> paired=<0/1> admitted_groups=<0/2> native=1 kv=128 outputs=512 cycles=<positive> fcsr=<flags> vcsr=5 checksum=<16hex> guardbytes=384 errors=0
AKV_PAIR_ABBA_PASS trials=4 outputs_per_trial=512 bytewise_equal=1 guards=1 derived_subset=1
```

Static expected work per trial (not cycle evidence):

| Mode | QK commands | PANEL4 subset | PV commands | All commands | Replay bytes |
| --- | ---: | ---: | ---: | ---: | ---: |
| OFF | 1024 | 0 | 512 | 1542 | 262144 |
| ON | 128 | 128 | 256 | 390 | 131072 |

Both modes: FULL2, REFILL2, RELEASE2; external Q1024B, KV131072B,
descriptor128B, payload132224B, ranges518. Entire ABBA has3864 commands.
QK dimension and PV token order per output are unchanged; sharing reduces
replay, not FMA work. A later runner must enforce requested/effective admission,
these exact hardware counters, all output/CSR checks, real UVM acceptance and
pre/post pins. An application PASS line alone is insufficient.

## Build only

```sh
python3 -B verification/akv/paired_heads/attention_build.py \
  --output verification/out/akv-paired-heads-attention-build-20261023-01
```

Fresh GNU rv64gcv_zfh_zvfh objects only; no old object reuse. The builder checks
the original capture receipts, existing paired object gate, accepted16MiB VCS
image and current image-source manifest hashes, dependency/tool/source hashes
before/after, actual calls to both original and paired helpers, and libc object
recursion hazards. Build.json records ELF alloc sections and all artifacts.
The existing image is pinned but never executed by this script.
