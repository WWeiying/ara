# QBS + AKV-v2 Dynamic Model Closure

Model: `/model/models/Phi-3.5-mini-instruct-Q4_K_M.gguf`

All counts below come from the traced guest execution. No QEMU wall time
or shape-mismatched RTL calibration is interpreted as hardware cycles.

| Phase | Graphs | QBS nodes | QBS chunks | QBS weight bytes | QBS dot elements | AKV calls | AKV Q bytes | AKV K/V bytes | AKV MACs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| prefill | 1 | 129 | 255 | 4542819840 | 74690002944 | 0 | 0 | 0 | 0 |
| decode | 1 | 129 | 129 | 2336288256 | 3722379264 | 32 | 196608 | 8650752 | 4325376 |

| Phase | Kernel | D | GQA | Q heads | KV heads | Active KV | Calls | Q bytes | K/V bytes | MACs |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| decode | v2 | 96 | 1 | 32 | 32 | 22 | 32 | 196608 | 8650752 | 4325376 |

Functional gates:

- guest exit: `0`
- output equal: `1`
- logits top-1 equal: `1`
- logits max absolute difference: `0`

This artifact proves dynamic selection, numerical behavior, and work/traffic
identities. Weight and Q/K/V byte counts are logical payload bytes from the
QBS ABI and AKV F16 contract; descriptor, cache-line overfetch, and output traffic
are not included. This artifact deliberately omits a cycle projection until matching RTL shape
calibration exists.
