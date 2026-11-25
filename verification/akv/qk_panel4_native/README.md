# PANEL4 native prerequisite gate

This directory currently implements a fail-closed **capability preflight**, not
the requested QK/whole-Attention numeric matrix. Static inspection of the named
QEMU model finds QBS INFO/EXEC, but no native AKV decoder/helper. The probe links
the unmodified production `akv_device_query` and `akv_native_info`; it does not
invent capabilities, emulate AKV, or skip a faulting instruction.

The runner attests QEMU with `verify_native_build`, pins source/tool/header
inputs before execution and rechecks them afterward. The actual AKV INFO PC is
obtained from the linked ELF disassembly. Only an exact illegal-instruction
trap at that PC with instruction `0x0005455b` and QEMU exit 2 is classified as
`BLOCKED`. Every other response is `FAIL`; discovery alone can never be PASS.
QEMU is bounded to 60 seconds and its process group is killed on interruption
or timeout. A full numeric gate requires an accepted AKV-capable model first.

The original KV128 capture is the `kv128` child of
`qwen2.5-1.5b-q4_k_m-attention-contexts-20260830_070252`, not the base model's
16-visible-token decode capture. Capture files are verified against the original
accepted ABBA manifest. They are provenance-only in this preflight; no numerical
execution or output equivalence is claimed.

From the signoff worktree:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover \
  -s verification/akv/qk_panel4_native -p test_probe.py -v
PYTHONDONTWRITEBYTECODE=1 python3 verification/akv/qk_panel4_native/run_probe.py \
  --out verification/akv/qk_panel4_native/out-native-probe-20261023-01
```

The second command intentionally exits nonzero for an unavailable model. No
QEMU timing is performance evidence. Shared C/assembly, QEMU, captures, and
existing evidence remain untouched.
