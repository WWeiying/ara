# Nine-Format QBS Successor

Build-only assets for the parent `operator_soc_20261115_activity_02` image. No
simulator, hardware build, model capture, production software edit, or commit is
performed. The parent central runner owns execution, at most four VCS workers,
image/protocol identity, and actual commit/activity traces. Do not dispatch these
assets without that owner. The parent's experiment plan is read-only context and
is deliberately absent from source pins.

## Input Classification

The real source is `stage2_qwen3_rows8_20261109_02/attn_q`: Qwen3 actual Q4_K
`blk.0.attn_q.weight` and eight distinct F32 activation rows. All nine evaluation
formats, including the Q4_K control, use the same first 64 full-K weight rows:

`actual captured Q4_K -> upstream dequantize -> F32 derivative -> upstream ref quantizer`

This is controlled two-stage requantization, NOT nine native model captures and
NOT original F16 weights. Each format has its own independent ordered `qbs_ref`
golden; outputs across different formats are not required to agree. M1 and M4 use
the first one/four distinct rows of the same real activation. M1 remains a
**Prefill row slice**, not actual Decode. No synthetic/repeated activation rows,
additional models, operators, or context captures are introduced.

## Minimal Matrix

All points have N64, full K2048, direct execution and first/repeat trials. The
36 ELF files are nine formats x M1/M4 x native/x32. The four nine-case manifests
allow M1 native qualification first and M4 only when the owner's budget allows.

| Format | Profile | Activation | K Blocks | M1 x32 | M4 x32 |
|---|---:|---|---:|---|---|
| Q2_K | 7 | Q8_K, 292 B | 8 | New candidate | Four x32 GEMV calls per N tile |
| Q3_K | 5 | Q8_K, 292 B | 8 | Archived `q3k_gemv_32` | Four archived GEMV calls per N tile |
| Q4_K | 1 | Q8_K, 292 B | 8 | Archived `q4k_gemv_32` | Archived `q4k_gemm_32x4` |
| Q5_K | 4 | Q8_K, 292 B | 8 | Archived `q5k_gemv_32` | Four archived GEMV calls per N tile |
| Q6_K | 2 | Q8_K, 292 B | 8 | Archived `q6k_gemv_32` | Archived `q6k_gemm_32x4` |
| Q4_0 | 3 | Q8_0, 34 B | 64 | New candidate | Four x32 GEMV calls per N tile |
| Q5_0 | 8 | Q8_0, 34 B | 64 | New candidate | Four x32 GEMV calls per N tile |
| Q8_0 | 6 | Q8_0, 34 B | 64 | Archived `q8_0_gemv_32` | Four archived GEMV calls per N tile |
| IQ4_NL | 9 | Q8_0, 34 B | 64 | New candidate | Four x32 GEMV calls per N tile |

Every RVV kernel computes 32 output columns, not a relabeled single-output dot.
Five formats use archived established kernels. The pinned source has no x32
kernel/field generator for the other four; `x32_candidate.c` supplies explicit
format-specific multi-output implementations. Those four remain **non-primary
candidates**, with independent host scalar-layout/numerical audits and RVV
compile/disassembly checks, not claims of established optimization or speedup.

## Numerical Proof

The upstream reference quantizers create weights offline. Actual upstream RVV
`quantize_row_q8_K` / `quantize_row_q8_0` create activation bytes inside each ROI.
Independent `qbs_ref` produces complete Q8, M4 packing, output bits and native
FFLAGS. SDK packing is checked against that independent reference on the host.

Native outputs are bit exact. RVV outputs must be finite and satisfy
`abs(actual-golden) <= 0.0002 + 0.0002*abs(golden)`, evaluated in FP32/RNE on the
target. All Q8/packed bytes and ten 64-byte guards are exact for both paths.
The compiled comparator checks EVERY byte/element outside the ROI. Four compact
records per trial contain extent, mismatch count, first bad index/value, raw
difference count and expected/actual FNV-1a hashes. **Hashes are diagnostic, never
the acceptance predicate.** Failure-only raw output is bounded to 16 bytes at the
first bad position; `--diagnostic` selects that bounded output even on success.

Compiled host mutation tests corrupt all 9344 maximum activation-byte positions,
all 256 maximum output positions, and check tolerance/nonfinite rejection. Python
tests cover all profiles/M/backends, work-counter corruption, missing/duplicate
proof, incorrect guards/flags/VCSR, and ROI truncation. `audit.py` verifies linked
ELF const data byte for byte, archive integrity and paired inputs/goldens. Its
synthetic logs are explicitly HOST TESTS, never simulation or performance proof.

After quantization, the firmware captures FCSR and VCSR. Q8_K sets VXRM=1, hence
postquant VCSR=2; Q8_0 leaves VCSR=0 from the explicit initial seed. Execution must
preserve that captured value and leave VSTART=0. FFLAGS seeds are 0 and DZ=8.
Native final flags must be `qbs_ref.flags | seed`; these real derivatives all
expect NX=1, hence FCSR=1/9. RVV may add NX only and must preserve seeded DZ.
Quantization FCSR allows only NX/UF. These are enforced contracts, NOT observed
runtime outcomes until the owner runs the manifests.

## Complete-Call Timing

Consecutive issue-side `rdcycle` boundaries measure quantization, packing, SDK
admission, complete execute, and final drain. Admission includes query, encoding
binding, planning and command enumeration. Execute includes the whole SDK call,
SDK pre-command fences/result stores, or all x32 tiles/input rows. Q4_K M4 output
scatter is included in execute, not hidden after the ROI. One final `fence rw,rw`
drains each trial. A commit-side marker pair encloses all phases and CSR snapshots;
its monitor totals include overhead and are reported separately from issue timing.

Native requires exactly two actual Mx32 full-K commands per trial. Activation
bytes, weight bytes, useful products, tile count, dot issue capacity, zero context
reuse, exclusive phase sums and faults are independently checked per profile.
All observed command fields, including FP updates and AXI counters, remain in
metrics. Pair capacity is NOT a claim of physical multiplier utilization.

Const inputs/weights are copied before timing. Offline weight conversion/repack
and its storage are recorded as artifacts but excluded equally on both sides;
no cold-setup or end-to-end model speedup is measured. First/repeat are same-input
steady-buffer calls, not next-token or persistent-context reuse. All comparisons,
snapshots and UART are outside the timed region.

## Reproduction And Delivery

```sh
python3 -B verification/performance/operator_eval_20261115/formats/prepare.py --requirements
python3 -B -m unittest discover -s verification/performance/operator_eval_20261115/formats -p test_formats.py -v
python3 -B verification/performance/operator_eval_20261115/formats/prepare.py --suite all \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_formats_prepare_20261115_new_run
python3 -B verification/performance/operator_eval_20261115/formats/audit.py \
  --build /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_formats_prepare_20261115_new_run
```

`--host-only`, `--suite native`, `--suite rvv_x32` and `--case ID` permit narrower
preparation, never simulator dispatch. Each compile/tool subprocess is bounded
to 120 seconds. Use a fresh authorized output directory; never overwrite reports.

SDK `dbe2b78817ef45b912444afcb85ad6e01a2be135` and llama
`a2b7f30da9aadf88b0a068c447383ed2e26ee867` are extracted using `git archive`.
Only the registered decode-sums patch is accepted, with apply/reverse identity
checking in the archived inputs. No working SDK/AKV assembly/RTL or unchecked
dependency enters the build. Compilers, dependency headers, libraries, generated
data, objects, ELF files, source helpers and tests are pinned. Existing qbs and
all historical assets remain untouched.

Delivery contains `manifest.json`, four `manifest_<backend>_m<M>.json` small
suites, per-case `build.json`/`plan.json`, `goldens.tar`, `source-pins.json`, and
`runner-source-pins.json`. The runner inventory also seals build receipts and
manifests. `asset-audit.json` and `preparation.csv` record preparation only, with
measured-cycle fields empty. No plan file from the parent is pinned.

Only the parent may turn these `BUILT_NOT_EXECUTED` artifacts into checked
performance results. Its current image, protocol closure and actual ROI/custom
command traces remain mandatory. This is not a new FPGA acceptance and makes no
NORMAL_MEMORY, Linux admission, whole-model or nine-native-model assertion.
