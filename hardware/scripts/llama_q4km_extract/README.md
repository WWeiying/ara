# Qwen2.5 Q4_K_M extraction under QEMU

This flow captures independently selectable leaf cases at three levels from a
real Qwen2.5-1.5B-Instruct Q4_K_M inference running on RV64GCV QEMU with
VLEN=1024:

- distinct F32-to-Q8_K, Q4_K x Q8_K, and Q6_K x Q8_K microkernel shapes;
- all seven quantized layer-0 linear operators for prefill and decode;
- independently replayable RMSNorm, RoPE, attention, FFN, and residual leaves.

This RV64GCV build disables `Zvfh`, and llama.cpp does not select its RISC-V
repacked Q4_K GEMV/GEMM kernels for VLEN=1024. Consequently, the micro level
records the quantize and vec-dot kernels that the real run actually executes;
the complete generic GEMV/GEMM behavior is preserved at the operator level.
The current replay build selects a dedicated VLEN=1024 single-output Q4_K x
Q8_K vec-dot path. It retains the original Q4_K layout and `nrc=1` interface;
multi-output repacking remains a separate follow-up optimization.

Q4_K_M is a mixed format. In this model `attn_v` and `ffn_down` are Q6_K;
the other five layer-0 linear weights are Q4_K. The capture and replay flow
preserves those actual types instead of describing the whole model as Q4_K.

The capture code is inert unless `LLAMA_Q4KM_CAPTURE_DIR` is set. The QEMU
flow uses a separate ext4 virtio-blk data disk, so the model is not copied into
the initramfs. The host extracts results from that disk after guest shutdown.

```bash
cd /home/wangwy/openproject/ara_dsa
hardware/scripts/llama_q4km_extract/build.sh
hardware/scripts/llama_q4km_extract/stage.sh
hardware/scripts/llama_q4km_extract/run-qemu.sh
hardware/scripts/llama_q4km_extract/cases.py prepare --strict
hardware/scripts/llama_q4km_extract/run-case.sh
```

Results are written to:

```text
/home/wangwy/llama/captures/qwen2.5-1.5b-q4_k_m/
```

`run-case.sh` without arguments lists every selectable leaf. Pass one ID to run
only that leaf, for example:

```bash
hardware/scripts/llama_q4km_extract/run-case.sh \
  micro/q4_k_x_q8_k_dot_n1536_nrc1
hardware/scripts/llama_q4km_extract/run-case.sh \
  operator/decode/blk_0_attn_q_weight
hardware/scripts/llama_q4km_extract/run-case.sh \
  operator/prefill/attention_core
```

After staging the RV64 runner, one leaf can also be replayed by itself under
RV64GCV QEMU without loading the model again:

```bash
hardware/scripts/llama_q4km_extract/stage.sh
hardware/scripts/llama_q4km_extract/run-case-qemu.sh \
  micro/q4_k_x_q8_k_dot_n1536_nrc1
```

One captured leaf can be built and run as a static RV64GCV program under
Spike plus proxy kernel from the hardware Makefile:

```bash
cd hardware
make llama_spike_list
make llama_spike_check
make llama_spike case=micro/q4_k_x_q8_k_dot_n1536_nrc1
```

The first invocation creates a separate static replay build under
`platforms/cva6-qemu/build/llama-q4km-spike`. It does not modify the QEMU
replay build or the captured data. Override `SPIKE`, `PK`, or
`Q4KM_CAPTURE_ROOT` when testing another compatible installation or capture.
`llama_spike_check` runs a real Q4_K x Q8_K smoke case with the same patched
Spike used by Ara differential verification. A leaf ID runs one replay; a
suite ID such as `block/decode/attention` expands to its leaves in manifest
order. Each invocation writes immutable per-leaf commands, logs, checksums,
exit codes, and a tabular summary below
`/home/wangwy/llama/captures/spike-runs/`. Set `LLAMA_SPIKE_TIMEOUT` in seconds
to override the default one-hour per-leaf timeout.

The aggregate selectors are `micro/all`, `operator/prefill/all`,
`operator/decode/all`, `operator/all`, `block/{prefill,decode}/attention`,
`block/{prefill,decode}/ffn`, `block/{prefill,decode}/all`, `block/all`, and
`all`. A Block selector runs its independently captured operators in model
execution order. It does not silently substitute synthetic inputs: each
operator reads the real QEMU input and golden captured at its own boundary.

For example, these select one microkernel, one operator, one Transformer
sub-block, and one full captured block, respectively:

```bash
hardware/scripts/llama_q4km_extract/run-case.sh \
  micro/q4_k_x_q8_k_dot_n1536_nrc1
hardware/scripts/llama_q4km_extract/run-case.sh \
  operator/decode/blk_0_ffn_down_weight
hardware/scripts/llama_q4km_extract/run-case.sh block/decode/attention
hardware/scripts/llama_q4km_extract/run-case.sh block/decode/all
```

The attention leaf consumes the captured post-update KV-cache view. The
stateful cache append itself is intentionally outside the stateless replay
suite because a correct standalone case also needs the pre-cache state, write
indices, current K/V, and expected post-cache state.

The bare-metal Attention-core harness keeps two explicit online-Softmax
implementations over the same captured Decode tensors. `ref` is a scalar
functional baseline; `rvv` follows the F16 K/V path in llama.cpp
`flash_attn_ext_f16_one_chunk`: it converts Q to F16, performs widening F16
dot products, updates the running maximum and normalization sum, accumulates V
in F16, and converts the normalized result to F32. Both paths validate after
the measured region. Phases 1, 2, and 3 in `llm_perf_monitor` correspond to Q
conversion/accumulator initialization, the online KV loop, and output
conversion/normalization.

Capture coherent Decode tensors from real Qwen2.5-1.5B Q4_K_M execution at
effective KV lengths 16, 128, and 256 with:

```bash
hardware/scripts/llama_q4km_extract/capture-attention-contexts.sh
```

The capture uses one generated token after prompts of 15, 127, and 255 tokens.
It restricts the callback to the five Attention-core boundaries Q, K, V, mask,
and pre-output-projection golden output; model, executable, source, prompt, and
tensor hashes are recorded beside each case. The `latest` symlink is updated
only after all three cases pass shape, type, size, mask, and hash checks.

Run one implementation and context with:

```bash
hardware/scripts/llama_q4km_extract/run-ara-attention-core.sh rvv 128 --all
```

`--spike-only` and `--ara-only` select the functional or RTL part of the same
case. Omitting the KV argument preserves the original 16-entry behavior.

Results are written to a timestamped directory below
`hardware/llama_attention_runs/`; existing QBS and paper result directories
are not reused. After both `ref` and `rvv` complete, collect their total and
phase-specific counters with:

```bash
hardware/scripts/llama_q4km_extract/summarize-ara-attention-core.py
hardware/scripts/llama_q4km_extract/analyze-attention-baseline.py
```

For this Attention case, the CSV renames the monitor's generic phase slots as
`q_convert`, `online_kv`, and `output_norm`; raw log field names and strict
counter semantics are otherwise preserved. Ara request counters are internal
request handshakes, not necessarily one-to-one ISA instruction counts.
`unit_load_span_bytes` and `unit_store_span_bytes` are diagnostic for this
case: whole-register operations encode register-group size differently from
ordinary unit-stride operations, so those fields must not be used as strict
traffic totals. The baseline analyzer derives Q/K/V and accumulator traffic
from the captured shape and source-level access contract, uses Spike traces for
dynamic ISA counts, and uses RTL reports for cycles, activity, stalls, and AXI
handshakes.

Use `status.sh` to inspect a background capture without attaching to QEMU. Ara
execution is deliberately outside this flow.

## Validation status

The strict manifest contains 48 selectable IDs backed by 86 captured tensors:
six microkernel leaves, seven quantized linear leaves per phase, eight
non-linear/dataflow leaves per phase, natural Attention/FFN sub-block suites,
and aggregate suites. `run-case.sh all` passes on the host. Independently
selected microkernel, generated RMSNorm, and real Q4_K linear leaves also pass
under RV64GCV QEMU with exact results and propagated process statuses of zero.
The patched Ara differential-reference Spike additionally passes all six Micro
leaves, Decode Attention RMSNorm, and the Decode Attention-K Q4_K linear
operator. Spike replay is statically linked and fixed to one GGML execution
thread to match capture conditions and the proxy-kernel runtime.
