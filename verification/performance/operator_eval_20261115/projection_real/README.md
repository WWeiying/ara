# Real Qwen3 Projection Successor

Owned source copies, not imports of sealed `formats/` or `qbs/`. No simulator,
production edit, new model capture, requantization, or git commit. The parent
experiment matrix is read-only context and is not pinned. All execution belongs
to the existing current all-on `operator_soc_20261115_activity_02` central runner,
with at most four VCS workers and its independent image/protocol gates.

## Static Selection

Exactly four pairs, each native QBS vs archived established x32 RVV:

| Phase | Operator | Native Format | M | N | Full K | RVV |
|---|---|---|---:|---:|---:|---|
| Decode position40 | FFN down | Q6_K | 1 | 128 | 6144 | `q6k_gemv_32` |
| Decode position40 | Attention Q | Q4_K | 1 | 64 | 2048 | `q4k_gemv_32` |
| Decode position40 | FFN gate | Q4_K | 1 | 64 | 2048 | `q4k_gemv_32` |
| Prefill first four distinct rows | FFN down | Q6_K | 4 | 64 | 6144 | `q6k_gemm_32x4` |

K/type/full shape are obtained from the locked capture receipts and independently
checked with the pinned upstream GGUF reader against the actual Qwen3 GGUF.
FFN down is K6144, not an assumed K2048. Native weight rows are compared byte for
byte to the GGUF tensor. N64/N128 are legal independent output-channel crops;
all K elements and quantization groups remain intact. The four-pair budget is
not expanded into all combinations of phase/operator/width.

The actual Decode capture is `e2e_decode_capture_20261106_01`, after 40 prompt
tokens at position40, input token22406. Its graph completed Prefill and captured
Decode operands before vocabulary; this is not a claim of complete model Decode.
Prefill down comes from `e2e_ffn_capture_20261106_02`, four actual different graph
activation rows captured before the first down projection. The Decode input is
different from all four Prefill rows. No Q4 Prefill K2048 M4/M8 point overlaps the
`qbs_reuse` ownership. These inputs are native quantized model captures, NOT
original F16 weights and NOT the controlled requantized derivatives in formats.

`review.py` requires receipt/inventory/log identities, reextracts all indexed
activation words, rejects missing/duplicate/out-of-bounds words, verifies all
bytes against captured F32 files, checks row uniqueness and then independently
checks native weights/type/shape against the GGUF. It performs no C compile.
`extract.py` is also a standalone, non-destructive extraction tool. Qualified data
exists, so no new capture run is needed. Old emulator traces establish operand
provenance only; they are never current RTL correctness or timing evidence.

## Numeric And Timing Contract

The owned `oracle.c` uses archived independent `qbs_ref` for complete Q8 bytes,
M4 packing, ordered outputs and FFLAGS. It separately compares SDK packing with
the reference. It rejects split-K, gathers/workspace, missing/duplicate outputs,
or any command that omits K blocks. K2048 uses eight Q8_K blocks; K6144 uses24.
Row-major consumers alias Q8 directly: no redundant pack copy is charged to
either M1 path or the Q6 M4 RVV baseline. Its PACK comparison checks that same
complete consumed row-major byte view; native M4 checks the interleaved buffer.
N64 issues two full-K Mx32 commands per trial, N128 four commands.

Target firmware uses actual upstream RVV `quantize_row_q8_K`. Native output bits
are exact; optimized RVV must be finite with
`abs(error) <= 0.0002 + 0.0002*abs(qbs_ref)` evaluated in FP32/RNE. Every Q8/packed
byte, every output element and all ten 64-byte guards are compared outside ROI
against compiled golden const data. Compact records give counts, mismatches,
first difference, actual/expected hashes and raw difference counts. Hashes do NOT
replace the exhaustive comparisons. Raw failure diagnostics are bounded to16 B;
`--diagnostic` selects the same bounded data on success.

Postquant FCSR/VCSR are captured. Actual quantizer disassembly sets VXRM=1, so
VCSR=2; execute must preserve it and leave VSTART=0. Quantization allows NX/UF
only. Execute FFLAGS seeds are0 and DZ=8: native requires independent ref flags
OR seed, RVV may add NX only and must preserve DZ. Host tests do not establish
actual target CSR correctness; that remains a runtime acceptance gate.

Issue-side `rdcycle` boundaries include full quant, pack, SDK query/encoding bind/
plan/enumeration, complete execute (all commands/rows/N tiles and result stores),
and final drain. One final `fence rw,rw` and a commit-side marker pair per trial
are audited in disassembly. Native SDK pre-command fences are inside execute.
All comparator/UART work is outside timing. First/repeat use identical inputs;
they are not next-token or stale-context reuse. No performance is measured here.

Offline weight repacking is excluded symmetrically and recorded in artifacts.
To fit the unchanged archived 1MiB link region, weights occupy a single guarded
`.data` payload, not a const payload plus a duplicate BSS copy. Input copying and
guard initialization are outside ROI on both paths. No link/RAM capacity or RTL
parameter is enlarged. The parent16MiB simulation RAM is not an FPGA admission.

## Build And Handoff

SDK `dbe2b78817ef45b912444afcb85ad6e01a2be135`, llama
`a2b7f30da9aadf88b0a068c447383ed2e26ee867`; only `git archive` inputs and the
reverse-checked registered decode-sums patch. No dirty SDK/AKV assembly is used.
The archived upstream GGUF parser plus installed NumPy are host inspection inputs.
All source/dependency/compiler/library/ELF/golden inputs are pinned. Parent plan
files and sealed sibling helpers are absent from dependency inventories.

```sh
python3 -B verification/performance/operator_eval_20261115/projection_real/review.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_projection_real_prepare_20261115_review_new
python3 -B verification/performance/operator_eval_20261115/projection_real/prepare.py \
  --review /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_projection_real_prepare_20261115_review_new/review.json \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_projection_real_prepare_20261115_release_new
python3 -B verification/performance/operator_eval_20261115/projection_real/audit.py \
  --build /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_projection_real_prepare_20261115_release_new
```

Fresh owned output directories only. Static review must qualify before any host
compile. `--host-only` stops before firmware compilation. Each tool/compile is
bounded to120 seconds. Preparation runs host parser/work/CSR/proof mutation tests
and the compiled exhaustive comparator tests at28032 activation-byte positions
and256 maximum selected output positions. Delivery audit checks linked `.data`
weights/guards, all golden const data, paired input/output identity, exact archive
bytes, actual link footprint and host-only synthetic checker success/rejection.

Deliverables: eight ELFs, overall `manifest.json`, four two-case pair manifests,
per-case build/plan receipts, `goldens.tar`, `source-pins.json` and the additional
`runner-source-pins.json` sealing manifests/receipts. `asset-audit.json` and
`preparation.csv` record preparation only; measured cycles stay empty. The checker
accepts the parent's `--build/--log/--output` schema and emits `state=PASS,metrics`
only after full workload evidence; current image/protocol closure remain external.
