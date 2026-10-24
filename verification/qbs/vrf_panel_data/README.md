# Real Q6_K VRF Panel Data

Host data preparation only. No RTL, QEMU, production GGML build, or performance
measurement is launched. Existing sources are read, never copied over or edited.

```sh
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 -m unittest discover \
  -s verification/qbs/vrf_panel_data -p 'test_*.py' -v
PYTHONDONTWRITEBYTECODE=1 /usr/bin/python3 verification/qbs/vrf_panel_data/prepare.py \
  --output verification/out/qbs-vrf-panel-data-20261023-01
```

The output must not exist. The wrapper requires GNU host GCC (default
`/usr/bin/gcc`), static glibc/libm development libraries, and the pinned capture
and accepted matrix-reuse vector. Compilation is C11, O2, strict warnings,
`-ffp-contract=off -frounding-math -fno-fast-math
-fexcess-precision=standard`, static linking, no build ID. Exact commands,
compiler metadata, transitive C header dependencies, host tools and libraries,
Python module inputs, pre/post hashes, and generated executable are recorded.
Each subprocess is bounded; no background worker is created.

## Contract

The capture is real prefill FFN-down from Qwen2.5-1.5B Q4_K_M. We select the
first four of fifteen activation rows and first 64 of 1536 weight/output rows,
with full K=8960 (35 Q6_K blocks). Golden output cropping preserves the original
6144-byte stride. The original seven capture files and replay manifest have
fixed expected SHA256 values, checked before and after generation.

`generate.c` links the existing `qbs_ref.c` unchanged. Quantization uses
`qbs_ref_quantize_q8_k`, NOT the production GGML M4 quantizer. The entire packed
Q8_K stream is compared to all A records of the accepted M4/K8960 vector.
The host reference quantizer does not establish production preparation byte or
CSR equivalence; both future matrix schedules must consume these SAME bytes.

Expected results come from two independent full-K reference executions per N32
panel (row-major and R4/M4 layouts), with exact bits and fflags agreement.
Panel 0 additionally matches the accepted vector O records and flags. Captured
llama outputs are independently compared with atol=rtol=0.002, with actual
max errors and bit mismatch counts reported. No bit equality is assumed.
This is not a new implementation of continuation arithmetic: the upcoming
continuation DUT must match these unsplit full-K results.

## Files and Addressing

- `activation_f32.bin`: original first four rows, 143360 bytes.
- `weight_row.bin`: original first 64 Q6_K rows, 470400 bytes.
- `activation_q8k_row.bin` / `activation_q8k_m4.bin`: 40880 bytes each.
- `weight_full_r4.bin`: two contiguous N32 panels, 235200 bytes each.
- `weight_striped_r4.bin`: nine K stripes, each containing two N32 panels;
  eight K4 stripes followed by K3. Total remains 470400 bytes.
- `full_n{00,32}_r4.bin` and `stripe00..08_n{00,32}_r4.bin`: explicit panels.
- `expected_f32.bin`, `llama_f32.bin`: 256 binary32 values, input-major N64.
- `expected_panel_f32.bin`: panel-major, then input-major N32; 1024 bytes.
- `oracle.json`: two panel fflags and their OR, error comparison, byte coverage.
- `panel_data.h`: constants, byte-offset table, expected flags, blob declarations.
- `panel_data.S`: aligned `.incbin` definitions for the declared blob symbols.
  Paths point to this sealed output directory; compile this file once and include
  the header in the future benchmark. Integer values and FP raw bits are LE.
- `manifest.json` and `status.json`: provenance and artifact identity; PASS means
  data generation/validation succeeded, not simulator verification.

For original row-major weights the block address is `(row*35+kb)*210`.
For full R4 it is `((row/4*35+kb)*4+row%4)*210`. A K stripe must be gathered
using the ORIGINAL stride and repacked with its local K length. A base-offset
adjustment alone is invalid. Every stripe logical block is visited exactly
once and every one of its 210 bytes is compared to the original, in C and Python.
The M4 activation block is 1168 bytes: scales at `4*row`, quants at
`16+4*element+row`, bsums at `1040+2*(group*4+row)`. A stripe uses
`k_start*1168`, with no requantization. All packed bytes and bsums are checked.

## Future Timing Boundary

Full-K baseline has two commands; the proposed K4/K3 panel traversal has 18,
with FILL then REUSE+release per stripe, QBEXEC on stripe 0 and QBACC thereafter.
Keep separate live destination groups. Matrix timing must include descriptors,
fences, all command dispatch, context traffic, VRF seed reads, intermediate
commits, final output stores, and any compiler-required spills/restores.
Production quantization/packing and online weight striping, if used, need
separate measured preparation costs. Offline preparation here is not free
runtime work and is not a production preparation benchmark.
