# F32 PV native gate preparation

The prepared ELF exercises the original generic F32 PV and the experimental
two-head F32 PV leaf on the same accepted VLEN1024/four-lane VCS image. It
does not change RTL, the canonical runtime, a running consumer, or GGML.

## Fixture and independent checks

Three shape pairs: D64/T1/KV-head0, D96/T63/KV-head1, D128/T64/KV-head1.
Q/K/V come from the hash-validated genuine Qwen2.5 KV128 capture. Only the first
D channels and first64 tokens of the selected KV head are gathered. Scores
and scales are directed finite coefficients, not captured model softmax
results. Initial FP32 numerators are exact conversions of captured V. This
tests the leaf contract, not a complete Prefill operator or model dispatch.

Each mode FULL-loads64 resident tokens, processes the requested T, and RELEASEs.
An independently compiled head-major scalar C `fmaf`/`fenv` oracle checks all
active output bits and flags. The on-chip test additionally compares the entire
1024-byte output including poison tail, original versus paired, initial sticky
DZ, RNE and VCSR5, all input buffers, the descriptor, and1024 guard bytes.
The printed `inputbytes=35072` counts the checked query512, K16384, V16384,
scores512, scales64, mask128, unused output1024 and descriptor64. The fixture
record itself is34880 bytes, including the initial output1024. Those are
different quantities and must not be conflated.

Expected actual work:6 FULL +384 V-row loads +6 RELEASE =396 commands.
Replay=85824 bytes; external payload=150144 bytes. No QK or PANEL4 instruction
is required by this PV leaf. D96 exercises D-axis tail. The checker rejects
missing/extra commands, bad flags, unexpected traffic and malformed summaries;
synthetic test PASS is not native acceptance.

## Preparation evidence

```sh
python3 -B -m unittest discover \
  -s verification/akv/paired_heads/f32_pv -p rtl_test.py -v
python3 -B verification/akv/paired_heads/f32_pv/rtl_build.py \
  --output verification/out/akv-f32-pv-rtl-build-20261024-02
```

The recorded build02 exists and is `BUILT_NOT_EXECUTED`. It verifies fresh GNU
ELF calls, exact drain/CSR instruction sequence, memory bounds, source/tool/
input hashes, accepted image inventory and source manifest pins. Build01 is
retained as a failed preparation attempt: missing repository include path for
the existing lifecycle wrapper, fixed before build02. No simulator ran in01.

The future worker must independently check simulator exit, original UVM
backend/AXI reads/writes, source inventory before/after, all source/artifact
pins and actual-log numerical/work checks. There is no actual RTL PASS,
performance result, odd-head caller test or complete Attention acceptance yet.
Do not infer those from the host object-mapping result or the ELF build.
