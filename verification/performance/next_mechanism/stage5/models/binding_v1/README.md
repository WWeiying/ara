# Held Model Binding Successor

NEW files only. Models04 / ffb83941c and overlay09 stay sealed. This preparation
does not build libraries, link a provider or model ELF, run QEMU, or authorize
inference. It freezes the interface between the separately owned static-library
build and a future parent-approved model runner.

## Inputs And Scope

The models04 case headers/token lists and actual model/format inventory are
reused byte-for-byte. Their 2162-pin receipt remains the input authority; this
small successor rechecks consumed inputs, not every multi-GB model asset. The
future launch must recheck the full inherited source/model/image inventories.
Runtime source is da56 + reviewed adapted06 + overlay09, not clean HEAD03959.
SDK f500 and models04 c492 have identical software/akv, software/qbs and
apps/common trees. This does not authorize importing dirty assembly or llama.

Both requested0/1 children use the SAME resident-ON static libraries, provider
object and final ELF. `GGML_RISCV_AKV_RESIDENT` is only a request; it grants no
provider authority. Both resident and separate legacy contracts must be explicitly
registered after S3 approval. Null providers must never become a positive case.
Keep QBS, QUANT_KV/PREFILL/REGISTER_PV, explicit pairing and other models04 options
identical across arms. Features-v2 and refill overlap remain disabled by overlay09.

`prepare.py` checks exact models04/overlay09 receipts and the sealed harness SHA,
then applies five exact text insertions to a COPY in a fresh output. The original
tokenization, teacher forcing, full-logit comparison and CSR checks are retained.
The new observe.h calls the real entry.h twelve-field counter type, before the
CSR setup and AFTER post-decode CSR capture. It exports every F32 logit as raw
hex bits, never decimal FP formatting. Five scalar-compiled GNU syntax checks
and synthetic checker tests run. There is no numerical SDK stub or native test.

```
python3 -B verification/performance/next_mechanism/stage5/models/binding_v1/prepare.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage5_models_binding_prepare_20261110_02
```

## Checker Contract

check.py streams a causally ordered guest-serial plus architectural-event log.
It independently compares all F32 bits, derives the greedy token from the entire
vocabulary, checks exact OFF/ON CSR results, enforces unique ordered phases and
raw-output coverage, and rejects malformed/duplicate/truncated records.
Snapshots must be cumulative and continuous. Eligible F16 Decode must have the
exact model-layer/group count, native for requested0 and resident for requested1;
all-fallback is rejected. Prefill, quantized KV and D256 have separate legacy
counts. D256 must retain ordinary fallback. Any unexpected denial, partial SDK
completion, lease miss or mixed route fails. Completed route traces must agree
with every expected layer's shape, active length and route.

Architectural AKV events are NOT replaced by these control counters. The checker
consumes actual begin/read/end records, validates monotonic sequence, successful
completion, RNE, QK no-source encoding, PV source separation, exact QK/PV controls
and querybase/tail/order, descriptor/query/K/V read work and FULL/REFILL/RELEASE
group balance. OFF/Prefill/fallback may not execute resident commands. Resident
PC matching is performed only when explicit final-ELF PC lists are supplied to
the pure checker API; the current held CLI does not invent them. Legacy detailed
arithmetic/individual-column work is not independently reconstructed here.
Native F16 Decode context starts, tails and releases are checked in order too;
this is not a substitute for its detailed legacy-column arithmetic work audit.

Existing QBS per-format summaries must be native, balance command counts and
context fill/release, and match exactly across request arms. Those summaries do
NOT independently prove QBS instruction retirement. Ordinary RVV PV_PREP also
has no AKV helper event; its actual execution is an explicit remaining proof,
not inferred from the PV count. The report always says CONTENT_CHECKED_NOT_ACCEPTED
and explicitly leaves release binding, QBS retirement and PV_PREP execution open.
It is not an S3/S4 acceptance checker by itself.

The future launcher must prove ordered correlation of serial phase markers and
all AKV trace events (for example a validated common output descriptor). Do not
merge separate logs by guessed timestamps or attach an unscoped aggregate trace.
The exact transport is NULL in binding-held.json until reviewed. No tracing mode
is switched on or new emulator instrumentation added by this helper.

## Remaining Binding

The held manifest leaves exact library/archive hashes, QEMU/S3 receipt, provider,
ELF/PCs, launcher, trace transport and parent approval unresolved. The checker
CLI rejects a NULL binding identity. Even a filled identity cannot turn a content
report into release acceptance. Future binding must be a reviewed successor,
not edits to models04 or these frozen inputs.
The held static link order is frontend.o, accepted provider.o, an archive group
containing libllama/libggml/libggml-cpu/libggml-base, then lm/pthread/dl/atomic.
Library includes/archives must resolve from James's reviewed build receipt, not
from a live llama tree or a guessed installation. No recipe identity is approved
merely by recording this interface.

Reviewed resource adjustment: guest4GiB, host MemoryMax8GiB, one CPU quota/guest
vCPU and one model worker; no automatic retry. This covers emulator overhead and
does not change model tokens, shapes, arithmetic or outputs. No QEMU timing is
hardware/model speedup evidence. No launch interface is provided here.
