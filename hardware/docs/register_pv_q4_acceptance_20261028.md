# Register-PV Q4_0 K: measured whole-call result

The first real-data RTL experiment is PASS. This is a software optimization
on unchanged QBS/RVV hardware, not a QBS hardware speedup or whole-model result.
The production backend has not been switched to this experimental path.

## Result

Qwen3-1.7B captured data, query 19, D=128, GQA=2, 20 visible tokens,
Q4_0 K and Q8_0 V, token-major physical KV storage. Baseline already uses the
shared RVV V decoder. The candidate fuses Q8_0 decode and PV through registers.

| ABBA trial | Path | Cycles | FCSR |
|---|---|---:|---:|
| 0 | Current shared RVV | 47880 | 1 |
| 1 | Register-PV | 42192 | 1 |
| 2 | Register-PV | 41823 | 1 |
| 3 | Current shared RVV | 47824 | 1 |

Baseline mean: **47852 cycles**. Candidate mean: **42007.5 cycles**.
Speedup: **1.1391299173x**. Cycle reduction: **12.21370058%**.
Each trial executes one QBS command, processes 20 V rows and produces 256
output words. All four outputs are bit-identical. Maximum absolute difference
from the captured reference is `2.998858690261841e-7`, within the established
`2e-5 + 2e-5*abs(reference)` tolerance. Guards, FCSR/VCSR, completion, independent
protocol checking and pre/post source/image identity checks passed.

The cycle ROI covers the C runtime call, including admission, preparation,
QK, online softmax/PV, normalization and completion drain. It excludes C++
dispatch/allocation, other layers and token generation. No token/s estimate
is derived from this point alone.

## Instruction evidence

The accepted offload monitor contains 3339 total records, below its actual
invocation limit of 2000000. Repeated baseline instruction mixes match exactly;
repeated candidate mixes also match exactly.

| Accepted request category | Baseline | Candidate | Reduction |
|---|---:|---:|---:|
| Load opcode | 178 | 130 | 48 |
| Store opcode | 140 | 52 | 88 |
| vset | 159 | 71 | 88 |
| Other vector arithmetic | 343 | 363 | -20 |
| Other offload | 3 | 26 | -23 |

These counts use UART BEGIN/RESULT windows, which also include setup and
checking. They are not timed-ROI IPC, memory byte counts, lane utilization or
an additive cycle breakdown. The drop in loads/stores/vset supports the source
analysis of removed intermediate V materialization and fused output updates.
It does not establish that every saved cycle has that single cause. Register
assembly and actual-CSR guards add instructions; the full-call measurement
includes those costs.

## Evidence and next gate

- Run: `verification/out/register-pv-native-q4-vcs-20261028-01`.
- ELF SHA256: `c055eb4a6014a09d086dd6849a4659207075e086140b6aba257468b861e7e086`.
- Result SHA256: `87fa666bd66dbaa7a38769f9587129a6999e6728a628716ebde539c4d95442d8`.
- VCS log SHA256: `506e418e8c75ae62ca1428a4d8fbf7ce9bcc0a3379fb87297465d4ce6fdc04a5`.
- `summarize_optimization_pair.py` replayed the output checker against the
  golden data and verified unchanged pinned inputs before accepting this result.
- `register_pv/analyze_trace.py` checks ordered/uncapped trace windows and
  repeated mixes. Its positive/mutation tests pass.

The Q8_0 K counterpart has been freshly rebuilt and passed preflight:
`verification/out/register-pv-native-q8-build-20261028-01`, ELF SHA256
`aaddd9ca60dfee8465794996462474fab549eab94b64c08c663c833933fc9f6d`.
Its separate VCS service is `register-pv-native-q8-20261028-01.service` and
result directory is `verification/out/register-pv-native-q8-vcs-20261028-01`.
Its outcome is not asserted here. This checks a second K format, not a second
shape. A distinct captured context/head shape and model-level regression are
still needed before production promotion.
