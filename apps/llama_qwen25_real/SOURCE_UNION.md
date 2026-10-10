# Apps Source Union (2026-09-26)

This is source consolidation, not a new DUT result or coverage campaign.
The donor is `/home/wangwy/openproject/ara_dsa_verification/apps`.
The `ara_dsa_masked_indexed_fix` and `ara_dsa_store_fault_fix_20260925`
apps trees were also compared. Their newer RTL-related directed sources are
already present in the integration tree and were not overwritten.

## Imported Files

Each of these directories contributes exactly `case.json`, `main.c`, and
`script/gen_data.py` (36 files, six RVV/QBS pairs):

- `apps/llama_qwen25_iq4_nl_decode_attn_q_qbs`
- `apps/llama_qwen25_iq4_nl_decode_attn_q_rvv`
- `apps/llama_qwen25_q4_0_decode_attn_q_qbs`
- `apps/llama_qwen25_q4_0_decode_attn_q_rvv`
- `apps/llama_qwen25_q5_0_decode_attn_q_qbs`
- `apps/llama_qwen25_q5_0_decode_attn_q_rvv`
- `apps/llama_qwen25_q2k_decode_ffn_down_qbs`
- `apps/llama_qwen25_q2k_decode_ffn_down_rvv`
- `apps/llama_qwen25_q2k_decode_ffn_down_4r_qbs`
- `apps/llama_qwen25_q2k_decode_ffn_down_4r_rvv`
- `apps/llama_qwen25_shape_prefill_n33_qbs`
- `apps/llama_qwen25_shape_prefill_n33_rvv`

Two additional bounded AKV entry points were retained:

- `apps/akv_column_coverage_smoke/{main.c,runtime.c,native.S}` reuses the
  portability test with two cases and an explicit success marker.
- `apps/akv_coverage_minimal/main.c` checks descriptor setup and a 128-element
  Q-stream read against the source bytes.

No generated `data.S`, tensor blobs, provenance output, object files, ELF,
dump, or generated `link_sim_4m.ld` / `link_sim_16m.ld` was imported into apps.

## Independent Capture Archive

The four IQ4_NL, Q4_0, Q5_0 and Q2_K capture directories were copied without
overwriting existing files to:

`/home/wangwy/openproject/ara_verification_archive/captures/<campaign>/capture`

The campaign names are `qbs-format-closure-iq4-nl-20260923-03`,
`qbs-format-closure-q4-0-20260923-03`, `qbs-format-closure-q5-0-20260923-03`,
and `qbs-format-closure-q2k-20260923-03`. All 380 regular files (53,971,257
bytes), including 172 `.bin` tensor files, have matching source/target
SHA-256 hashes and independent source/target inodes. The originals remain
untouched. All ten applicable case specifications now reference this archive,
not the old verification worktree. N33 retains its existing default capture
under `/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m`.

`verification/out/consolidation-20260926/captures.json` records the source and
destination roots, per-file sizes and both hashes, and before/after hashes
for the relocated case specifications. This is copy provenance, not numerical
or DUT validation.

## Merged Dependencies

- `apps/llama_q4km_micro/micro_kernels.{c,h}`: Q4_0, Q5_0, IQ4_NL and Q2_K
  block types and RVV dot products, retaining all existing kernels.
- `apps/llama_qwen25_real/common/benchmark_impl.h`: format dispatch and the
  explicit Q4_K row-major path required by the N33 RVV case.
- `apps/llama_qwen25_real/common/qbs_benchmark_impl.h`: corresponding weight
  profiles, activation types and Q8_0 quantization selection.
- `apps/llama_qwen25_real/common/generate_case.py`: format sizes and the shared
  `Q8_0_ACTIVATION_WEIGHTS` set.
- `apps/llama_qwen25_real/common/generate_qbs_case.py`: use that set for both
  activation provenance and exclusion from the K-quant M4 activation pack.
- `apps/akv_portability_smoke/main.c`: optional bounded wrapper; the original
  default remains seven cases followed by its existing additional checks.
- `apps/Makefile`: strict FP flags and dependencies for the AKV wrapper;
  shared micro/repack dependencies for Qwen app objects, including `.o.spike`.

The existing software QBS ABI already defines all four added profiles and
their activation contracts. No software/RTL dependency changes were needed.
`apps/common/crt0.S` and all existing `apps/riscv-tests/isa/rv64uv` files,
including `Makefrag`, were preserved byte-for-byte during this import.

## Host Verification

Run from the repository root:

```sh
python3 -B apps/llama_qwen25_real/tests/test_source_union.py -v
LLAMA_TEST_REAL_CAPTURES=1 python3 -B apps/llama_qwen25_real/tests/test_source_union.py -v
```

The second command passed all 11 test methods with no skips during import
and again after relocating the four captures to the independent archive.
The final post-relocation output is saved in
`verification/out/consolidation-20260926/real-capture-host-tests.log`.
It covers nine weight formats at M=1/4/8 for QBS layout/provenance, all nine
row-major paths, the five existing x32 formats, N33 zero padding, cropped
golden rows, hardlink isolation, rejection of invalid capture metadata/data,
host C block-size assertions, and all 12 imported wrappers using the real
archived captures. All generation output is confined to temporary directories.
Synthetic fixtures test layout only; they are not numerical benchmark inputs.

## Remaining Limits

- No target compilation, Spike, VCS, Verilator, or RVV/QBS numerical execution
  was performed. Host generation success does not establish target correctness
  or performance. The imported kernels are not newly validated for arbitrary
  VLEN configurations; retain the established Ara test configuration.
- Capture data is archived outside the source repository rather than vendored.
  Moving to another machine still requires the matching archive or a
  `LLAMA_CAPTURE_ROOT` override, but no active imported case needs the old
  verification worktree.
- The main consolidation has added root `.gitignore` exceptions for all four
  imported AKV source files. These sources are no longer hidden by `/apps/*`;
  generated artifacts remain ignored. This sidecar did not edit those rules
  or the Git index.
- Existing simulation launchers and format matrices outside `apps` were not
  expanded. The apps Makefile discovers the new `main.c` entry points, but
  this task does not schedule them or claim broader campaign coverage.
