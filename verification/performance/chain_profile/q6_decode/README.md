# Q6 Decode Slice

Build-only workload for real Qwen3 position40 Decode `blk.0.attn_v.weight`:
M1/K2048/N64, two N32 commands in one complete SDK call, repeated twice.
This is not M4 prefill, a full layer, full GGML, or whole-model inference.

```sh
python3 -B -m unittest discover \
  -s verification/performance/chain_profile/q6_decode -p 'test_*.py' -v
python3 -B verification/performance/chain_profile/q6_decode/build.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/chain_q6_build_20261107_01
```

The output must be new. The builder runs only host reference tools and GCC
cross compilation. It never starts RTL, VCS, synthesis, Verilator, URG or ZCC.
SDK, startup runtime and independent host reference come from `git archive`
of the main workspace HEAD on `ara_dsa`, not the unrelated `main` branch ref.
The linker script is preprocessed from that archive's `arch.link.ld` with
16-byte section alignment and a 1MiB image region, not an untracked local script.
llama comes from its HEAD archive plus the SDK's already registered
`llama-decode-sums.patch`, applied only inside build inputs. No old `.o` is used.

The original capture/result and build receipts are SHA-pinned. Selected data,
original source-pin inventories and original ELF are checked before use.
Independent current `qbs_ref` redoes all 2336 Q8 bytes and all N128 R4 bytes,
checks the indexed N64 crop against a fresh repack of the raw model rows,
then computes a new two-command N64 golden and checks original expected[:64]
bit-for-bit. Scalar host quantization is a reference only, never the workload.
The linked workload calls the real llama RVV `quantize_row_q8_K`; its full Q8
scale, quant and bsums bytes are dumped for independent host comparison.

Each measured call has consecutive `rdcycle` boundaries:

- `prep`: full-K RVV quantization.
- `admit`: native device query, encoding binding, plan creation and context
  admission. Ineligible context uses the SDK DIRECT fallback. Unsupported
  profile/shape/device fails closed, not a fabricated performance result.
- `execute`: one `qbs_execute_with_options`, including unmodified native
  pre-command fences, vsetvli and vector result stores. Context OPERATION is
  FILL then RELEASE; generation changes on the repeat, not cross-call reuse.
- `drain`: the existing end-of-call `fence rw,rw`, separately measured.

No added hardware fence separates preparation, admission and execute. Timing
reads have compiler memory clobbers but are not hardware serialization points.
The quantized `fcsr` sample immediately after the preparation stamp is included
in admission. The initial/final CSR samples are outside the timed interval.
The resulting phases are software issue-side intervals, not proof that all
vector stores have completed at the preparation boundary. Deferred stores and
native fencing remain charged where the unchanged SDK encounters them.
Timestamp/branch costs remain in their enclosing intervals. No overhead is
subtracted. There is no timed weight repack or output/UART/numerical check.
The same work buffers are used twice; snapshots and checks occur between calls,
all UART output follows both calls. Report first/repeat separately; do not
assert particular instruction/data cache residency or guaranteed warm speedup.
Before each call, mutable guards and output/Q8 poison are reset and fcsr/vcsr/
vstart are zeroed. Raw 64-byte guards on each side of Q8, output, input and
weights are captured after each call. The checker checks every guard byte,
all CSR samples (including preserved post-quant fcsr and final VL32/e32m1),
one quant/plan/execute call, two planned commands and observed native work.

The owner supplies the current area-baseline SoC, single-worker execution,
native-extension capability guarantee, background service and independent
protocol/image identity checks. This bare-metal ELF uses flat simulation RAM;
it makes no board `NORMAL_MEMORY` eligibility assertion.

Run with the owner's `+QBS_PERF` collection and pass the resulting raw UART /
`[QBS_PERF]` log to the checker command recorded in `build.json`. It rejects
missing/extra commands, wrong geometry, failed commands, incomplete/duplicate
records, phase-accounting errors, any Q8 byte drift and any output bit drift.
`check.py` exposes `check_run(log_path: Path, build_dir: Path) -> dict` for the
unified runner. It returns `state=PASS` only after full workload scope, raw
output/Q8 bytes, CSR, raw guards, call work and native counter/ROI checks pass;
missing evidence or drift raises an exception. This is explicitly a workload
PASS, never an independent protocol PASS or current-SoC acceptance. Engine phases are
exclusive; dot issue capacity is not physical lane utilization. The execute
residual cannot separate native fences/stores from SDK overhead by itself.

After the owner pins a build, all pinned sources (including this document and
tests) are sealed until collection finishes. Use successor files for changes.
