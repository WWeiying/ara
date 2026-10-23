# QBS split-issue SoC integration

## Ownership and scope

The active verification campaign is owned by `ara_dsa_signoff_integration`.
The candidate remains in the existing `ara_dsa_qbs_activation_overlap`
feature worktree at `dfdd9251`; main and FPGA RTL are not changed by this
integration check. Do not edit the candidate sources or sealed test helpers
while a consumer is running. The VCS source-manifest gate checks the frozen
build inputs before and after each execution.

The candidate contains direct activation overlap (`66e93c07`) and independent
conversion/arithmetic issue (`dfdd9251`). Command-level equivalence and
performance evidence is under `verification/out/qbs-shortblock-20261022/`.
That evidence is not a whole-model or physical-design result.

## Initial integration results

Evidence: `verification/out/qbs-split-soc-20261022-02/`.

| Input | Result | Scope |
| --- | --- | --- |
| `qbs_akv_handoff_smoke` | PASS | QBS/AKV handoff and checked fault/recovery scenarios implemented by this program |
| `rv64uv-ara-vfmacc` | PASS | Ordinary vector FMA regression, not all RVV instructions |
| Old `llama_qwen25_q8_0_decode_attn_q_qbs` ELF | FAIL; stopped | First QBS command rejected; obsolete descriptor version |

The old ELF SHA-256 is
`baac455fd8ef5d5ccf48da81c87db1e46ce4426935077120cc7d65768400dc94`.
Its committed scalar trace and disassembly establish:

1. PC `0x8000019a` computes descriptor address `0x8003e780` in `a0`.
2. PC `0x8000019e` computes header `0x37f12261` in `a3`.
3. PC `0x800001cc` executes `sd a3, 0(a0)`.
4. The first QBS request uses instruction `0x00b5045b` and this descriptor.
5. The interface reports an exception at contract-trace cycle 6387, followed
   by invalid instruction fetches from the program's default trap target.

Header bits `[3:0]` are 1. The current descriptor decoder requires version 2
and rejects the request before compute. This is a definite input-contract
mismatch, not evidence of a split-issue numerical regression. The later
invalid instruction fetches are secondary symptoms, not a reason to extend
the timeout or weaken the decoder.

## Current-source replay

The app was rebuilt in the verification worktree using current source,
ordinary LLVM (not ZCC), RV64GCV+Zfh+Zvfh, four lanes and VLEN=1024:

```bash
make -C apps bin/llama_qwen25_q8_0_decode_attn_q_qbs \
  INSTALL_DIR=/home/wangwy/openproject/ara_dsa/install \
  RISCV_ARCH=rv64gcv_zfh_zvfh -j4
```

New ELF SHA-256:
`3d80aecc0f157d2990a0487ac31972710d5eb1d57e81a1dca474201544760ea8`.
The disassembly builds header `0x37f12262` and stores it to the stack
descriptor before issuing QBS. It follows the current production-command
benchmark path, rather than the obsolete prebuilt-descriptor implementation.
Therefore old/new total benchmark cycles must not be treated as a paired
hardware performance experiment.

The generated inputs match the previous test byte-for-byte:

| Input | SHA-256 |
| --- | --- |
| R4 weights | `42609cb7412815b4d7dd5ff9cc6e4c730f2e6e23e661a8f21f70820d791af94c` |
| F32 activations | `925ecf5a90a8811fd27c89631595df7b9f68ac92571ef0b1d622c2ced9cb07a3` |
| F32 golden | `bdd8c137f93e69d59f0322812a40d5730ec245099da30a261405a87e835e7cbb` |

Replay uses the same candidate image from the initial integration, without
recompilation or RTL edits. Configuration: QBS enabled, AKV-v2 enabled,
VLEN=1024, four lanes, 1 MiB simulation L2, no injected AXI delay.

- Service: `qbs-split-soc-abi2-20261023-01.service`.
- Output: `verification/out/qbs-split-soc-abi2-20261023-01/`.
- Worker: existing `verification/uvm/run_real_dut_case.sh`.
- Limit: 1800 seconds, independent directory, no FSDB.
- Launch confirmed the actual `simv` child in the service control group.

At creation of this record, the replay is running, not accepted. Require
normal application completion, checked numerical output, clean independent
UVM result, and source/image/ELF identity checks before claiming integration
PASS. Preserve the original failed run. No current coverage or performance
claim is derived from that failed run.

## Remaining work

Complete current-source SoC acceptance before merging the optimization.
Keep the broader priorities open: split-K tile geometry and activation reuse,
AKV delivery/compute overlap with singleton protection, shared-resource
organization, and quantized-KV runtime coverage. Existing paired-head kernel
tests do not establish full-Attention or model-level speedup.
