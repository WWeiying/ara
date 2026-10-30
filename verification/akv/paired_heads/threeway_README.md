# Ordinary RVV / generic AKV / paired AKV preparation

Build only. No worker, simulator execution, canonical edit, old object reuse,
numerical acceptance, or performance claim is part of this preparation.

## Data and ABI

Source: accepted genuine Qwen2.5 KV128 Decode capture at
`/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m-attention-contexts-20260830_070252/kv128`.
Offline crop original Q heads0,1,6,7 and matching output heads. This is a derived
four-head/GQA2 subset, **not a Qwen3 capture**. K/V/mask remain byte-identical;
the original physical KV capacity is256 and visible mask prefix is128.

The builder imports original `gen_data.py.make_spec(..., "rvv")`, updates only
args[2] and Q/golden tensor descriptors, and calls original `emit_blob` for all
blobs. Q becomes F32[128,1,4,1],2048B; golden becomes F32[512,1,1,1],2048B.
Every crop byte is validated by source head/dimension/byte coordinate. The
linked180B configuration and every input/golden blob are checked against the
prepared bytes, not just source assembly text. Linked output capacity is exactly
2048B; its64B guards are outside start/end, never included in ABI capacity.

## Actual paths and timing

The new main includes original `apps/llama_q4km_operator/main.c` with its main
renamed. `threeway_ordinary_rvv` calls actual `run_attention_rvv(cfg)`, **not
run_attention_tiled_rvv**, which does not admit this GQA2 shape. No native
capability query is attached to the RVV path.

AKV uses sealed `software/akv/experimental/paired_heads/native_bench.c` and
canonical assembly. Generic requests mode0; paired requests mode1 and must
actually admit both KV groups. Original RVV Q conversion reads cropped
`kvhead*2+head` rows, with no extra runtime gather. Both groups create real plans
and execute the complete native Attention, including softmax and normalization.
Overlap remains OFF. No partial-issue retry or silent ON fallback is accepted.

All paths write the same output address. Order is
**rvv, generic, paired, paired, generic, rvv**. Each call resets RNE FCSR0/VCSR5
before timing. Timed work includes real query conversion, actual path-specific
query/plan/admission, execute and output stores, followed by scalar-extract and
fence drain. The accepted `hardware/src/ara_sequencer.sv:619` gates scalar
extract behind all older vector work; this is not a register-specific dependency.
Cycle end precedes CSR snapshots, which precede any numerical checking.

Offline cropping, output/query poison, guard setup and workspace reset are
outside every timed call. No simulated wall-time or host build timing is a
performance measurement. Summed repeated cycle values will be reported per
variant only after actual independently checked execution.

## Numerical checks and compact protocol

Every call checks all512 outputs finite and within unchanged original
`atol=0.004 + rtol=0.002*abs(golden)` tolerance. Each variant's two runs must
match all raw output bits and FCSR. Generic and paired must also match exactly.
RVV may differ from AKV in raw bits/flags, but must meet original tolerance and
its own exact repeat. All samples require RNE and VCSR5. Checks/hash/UART are
outside timing; only the first numerical mismatch is printed on failure.

```text
THREEWAY_SUBSET source=qwen25_kv128 qheads=0,1,6,7 kvheads=0,1 outputs=512 derived=1 outputbytes=2048
THREEWAY_BEGIN trial=<0..5> variant=<rvv|generic|paired>
THREEWAY_END trial=<0..5> variant=<...> executed=1 native=<0|1> admitted_groups=<0|2> outputs=512 cycles=<positive> fcsr=<flags> vcsr=5 checksum=<16hex> guardbytes=384 errors=0
THREEWAY_SUITE_PASS trials=6 outputs_per_trial=512 within_variant_exact=1 generic_paired_exact=1 rvv_tolerance_only=1 guards=1 derived_subset=1
```

FNV64 summaries are secondary: exact comparisons occur on chip. No expected
CSR/checksum is invented before execution. The suite marker alone is not proof.

## Later mandatory hardware accounting

| Per call | AKV commands | column loads | panels (subset) | V row loads | replay bytes |
|---|---:|---:|---:|---:|---:|
| ordinary RVV | 0 | 0 | 0 | 0 | 0 |
| generic AKV | 1542 | 1024 | 0 | 512 | 262144 |
| paired AKV | 390 | 128 | 128 | 256 | 131072 |

Each native call: FULL2, REFILL2, RELEASE2, Q1024B, KV131072B,
payload132224B, ranges518. Six trials total3864 commands; ordinary RVV intervals
must contain no AKV commands. A later worker must check each actual record and
the final **raw AKV_PERF_SUMMARY**, enforce zero faults and correct lifecycle,
and independently require UVM vector/backend/AXI-write evidence and source/image/
artifact pre/post identity. Current pair numerical PASS does not substitute for
this six-trial gate, and neither preparation nor mechanism ABBA proves a gain
against ordinary RVV or general production deployment eligibility.

## Reproduce preparation

```sh
python3 -B verification/akv/paired_heads/threeway_build.py --self-test
python3 -B verification/akv/paired_heads/threeway_build.py \
  --output verification/out/akv-paired-heads-threeway-build-20261023-01
```

Fresh GNU rv64gcv_zfh_zvfh objects; original app/native wrappers/shared source,
all transitive C/assembly headers, tools/libm/libgcc, original capture receipts,
accepted simulator and image-source manifest are pinned. Generated crop/data,
objects, disassembly, ELF, and ABI/data proof are included in artifact hashes.
The script verifies start/post pins and records BUILT_NOT_EXECUTED in build.json.
Use a fresh output directory for another build. No simulation command is run.
