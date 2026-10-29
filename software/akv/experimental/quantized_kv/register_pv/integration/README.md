# llama.cpp integration delta

`llama-register-pv.patch` contains only this Register-PV integration's changes
to the existing local GGML adapter and CPU CMake file. It does not include or
commit unrelated changes in the external llama.cpp worktree.

The external repository HEAD when captured was
`8ed9403e37f1ceb43c6279cdefef01354eac6fd3`, with pre-existing local QBS/AKV and
quantized-KV integration. This patch is **not** a complete port against a clean
checkout of that commit or upstream llama.cpp. The required preimage hashes
below match the independently recorded pre-Register-PV integration audit.

| File | Required preimage SHA256 | Result SHA256 |
| --- | --- | --- |
| `ggml/src/ggml-cpu/CMakeLists.txt` | `81d5eeb001884fb27b554b505b01f9e50e4d19507c90bf3c25e9d116b9c0c7ee` | `2168ddbf805dc048b86d868468b4793f8998d635bd55cfa9d247bef4e375275f` |
| `ggml/src/ggml-cpu/arch/riscv/quant-kv.cpp` | `94a7b7a18b2c581f56835ebefe109257d0878341fab09fed50b8e76f80b8d0c4` | `d307c171e6a2e6da9870ad78df55863a95562e5eab07d1bbd46c4fffed082c2f` |

The delta adds a default-OFF CMake option, compiles the guarded shared entry,
adds explicit runtime selection, rejects simultaneous selection of the older
grouped-PV experiment, and reports which Decode path actually ran. Prefill
selection is unchanged. It requires this repository's shared Register-PV source
through the existing `GGML_RISCV_AKV_RUNTIME_DIR` configuration.

Validation performed without editing the live external worktree:

- Forward `git apply --check --verbose` against reconstructed preimages.
- Reverse `git apply --reverse --check` against the current external files.
- Both preimage hashes compared with the previous integration audit.

The external worktree already contains the patch; do not apply it again there.
For a compatible destination, check the preimage hashes, run `git apply --check`
and then apply the patch. Mismatched hashes require review rather than forced
application. This tracked delta provides a reproducible record while final
model tests remain sealed; it does not imply the external repository has been
committed or pushed.
