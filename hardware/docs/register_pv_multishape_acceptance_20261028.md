# Register-PV: multi-format and context acceptance

## Measured decision

Three real-data VCS ABBA pairs passed on the same RTL image. Register-PV keeps
Q8_0 value decoding and the weighted update in vector registers instead of
materializing the decoded value row in scratch memory. The baseline already
uses the shared RVV decoder. No RTL was changed for these measurements.

| K format | Visible tokens | Baseline cycles | Register-PV cycles | Speedup | Cycle reduction |
| --- | ---: | ---: | ---: | ---: | ---: |
| Q4_0 | 20 | 47852 | 42007.5 | 1.139130x | 12.2137% |
| Q8_0 | 20 | 49152.5 | 43504.5 | 1.129826x | 11.4908% |
| Q4_0 | 8 | 28495.5 | 25811.5 | 1.103985x | 9.4190% |

These are arithmetic means of two repetitions per implementation, in ABBA
order. The two new pairs have raw cycles:

- Q8_0/20: A=49259, B=43831, B=43178, A=49046.
- Q4_0/8: A=28635, B=26110, B=25513, A=28356.

All cases use real Qwen3-1.7B inputs, D=128, two query heads sharing a KV head,
Q8_0 values, and token-major KV layout. The 8-token case uses captured query 7
and its own golden output; it is not query 19 with its context truncated.
Each trial checks 256 output words. Both implementations execute one QBS
command per trial. The measurement includes the complete Decode C call, but
not GGML allocation/dispatch or whole-model execution.

## Acceptance evidence

All three receipts satisfy PASS, paired bit equality, independent protocol
checks, performance measured and unchanged source/image pins. Summary replay
also rehashed inputs and ELF, reran the original checker, and returned ACCEPTED.
For both new pairs FCSR is 1 in every trial. Maximum absolute deviation from
the captured golden is 2.477318048477173e-7 for Q8_0/20 and
7.450580596923828e-8 for Q4_0/8.

Evidence directories under `verification/out/`:

| Point | Run | Result SHA256 |
| --- | --- | --- |
| Q4_0/20 | `register-pv-native-q4-vcs-20261028-01` | `87fa666bd66dbaa7a38769f9587129a6999e6728a628716ebde539c4d95442d8` |
| Q8_0/20 | `register-pv-native-q8-vcs-20261028-01` | `4b97c4062dadcffc5bc5065c23388c97f441db6476b5aa1e0c3295fe666d69b8` |
| Q4_0/8 | `register-pv-context8-q4-vcs-20261028-01` | `2293fed26d4a09bf0636d4370d8c48f9115ab084ae09407c28d765644e431632` |

Use `summarize_optimization_pair.py --run <directory> --mechanism register-pv`
to replay acceptance. Context-pair receipts are bound to the query index in the
build record; mismatched query, visible count or captured output is rejected.

## What this permits next

The accepted offload trace also reproduces reduced load/store/configuration
instruction counts in both additional cases:

| Case | Instruction class | Baseline | Register-PV |
| --- | --- | ---: | ---: |
| Q8_0/20 | Vector load | 177 | 130 |
| Q8_0/20 | Vector store | 139 | 52 |
| Q8_0/20 | vset | 158 | 71 |
| Q8_0/20 | Vector arithmetic | 342 | 362 |
| Q4_0/8 | Vector load | 81 | 58 |
| Q4_0/8 | Vector store | 67 | 28 |
| Q4_0/8 | vset | 86 | 47 |
| Q4_0/8 | Vector arithmetic | 174 | 182 |

Both repeats have identical instruction mixes. The traces contain 3327 and
1695 total records respectively, below their verified 2,000,000-record limits.
These counts cover UART BEGIN/RESULT windows, including setup and checking;
they are not timed-ROI IPC, AXI read/write bytes, or functional-unit utilization.
They support the expected reduction in scratch materialization and configuration
work, while also showing extra vector arithmetic. They cannot assign the whole
cycle reduction to one instruction class or prove memory bandwidth saturation.

The benefit is not confined to one captured point. Proceed to an opt-in shared
implementation and GGML integration, retaining the original path. This is not
yet proof of benefit for all supported head dimensions, long contexts, or full
models. Existing functional shape tests are complementary, not RTL performance
measurements for those shapes.

The integration must preserve:

1. Actual VLEN=1024, RNE and vstart=0 checks before quantization, QBS commands
   or output writes; do not rely solely on caller-provided capability fields.
2. Existing tensor mapping, backing-memory extent, alias and workspace checks.
3. Q4_0/Q8_0 K with Q8_0 V; unchanged QBS descriptor and completion handling.
4. Rejection before work as FALLBACK; failure after starting as terminal
   EXECUTION_FAILED, never an automatic ordinary-path retry over partial state.
5. Per-row online-softmax ordering, separately rounded rescale and FMA update.
6. One canonical kernel source for the backend and subsequent benchmarks.
7. Explicit selection and tracing, with the old grouped-PV experiment kept
   distinct from this register-resident implementation.

The current GGML adapter already distinguishes fallback from terminal failure
and owns QBS execution through `ggml_riscv_qbs_direct_run`. Retain that ownership
boundary. Production activation is pending integration and model-level
numerical regression; no whole-model gain is claimed here.
