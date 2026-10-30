# Current Attention retirement findings

## Result and scope

The accepted current ELF was rerun with COMMIT_TRACE, without changing its
program, inputs, compiler options or RTL. All four complete-call numerical,
guard, CSR, work and independent protocol checks pass. The eight retired cycle
CSR values reproduce the run's own printed timings exactly. The four cycle
totals equal the earlier untraced run: 480814 / 485698 / 484920 / 480503.
There is no observed processor-cycle perturbation in this comparison.

This is one real Q4_0-K/Q8_0-V Decode Attention group, H6/D128/T128, not a
complete layer or model. The ordinary shared schedule is the production
default; grouped PV remains OFF after its 0.9675% complete-call regression.

## Exact dynamic instruction evidence

The two repetitions of each schedule have identical retired instruction
counts. The table gives one complete timed call, excluding both CSR boundaries.

| Retired category | Ordinary shared V | Grouped PV | Difference |
| --- | ---: | ---: | ---: |
| Native QBS commands | 8 | 8 | 0 |
| RVV compute | 2506 | 2506 | 0 |
| RVV configuration | 1425 | 740 | -685 |
| RVV memory | 3502 | 2772 | -730 |
| Scalar FP category | 45446 | 49414 | +3968 |
| Other scalar | 144276 | 151678 | +7402 |
| Total | 197163 | 207118 | +9955 |

The scalar increment is **11370**, not 13924. Scalar FP is the analyzer's
instruction class, including scalar FP loads/stores and moves, not a count of
arithmetic operations. The reduction in vector instructions is real but does
not outweigh the additional scalar work in this measured implementation.
Instruction count alone still does not explain every latency difference.

The default path retires 83184 instructions in `expf` and `__ieee754_expf`,
42.1905% of all measured instructions. It retires 737 scalar FP divides inside
those functions. Another 48 occur in Q quantization and six in final
normalization, for 791 total. These counts are actual PCs matched against ELF
bytes, not estimates from source loops.

## Retirement gaps are diagnostic context, not execution latency

For the first default trial, the next-PC interval labels are:

| PC context | Retired instructions | Assigned next-PC gap cycles |
| --- | ---: | ---: |
| Exponential helpers | 83184 | 134628 |
| MAD leaf | 10752 | 96744 |
| Scale leaf | 612 | 4702 |
| Value decode leaf | 13312 | 52832 |
| Value callback | 4736 | 17357 |
| Query quantize leaf | 606 | 5760 |
| Native submission | 320 | 10080 |
| QK callback | 3274 | 5703 |
| Shared memory helpers | 8531 | 14936 |
| Unclassified mixed orchestration | 71836 | 138063 |

Intervals use `[previous retirement, next retirement)` and charge the gap to
the next PC; the final CSR gap is separate. They are not exclusive execution
or stall times and cannot be called functional-unit utilization. In particular,
the largest default MAD context is `0x80002b7c`, a `vse32.v` following
`vfmadd.vf`. Its assigned gap can include completion/dependency effects from
earlier work. It does not prove that storing itself consumes 79746 cycles.

The grouped path's largest context is likewise a vector update/store region.
Do not remove ordering barriers or add an arithmetic unit based on the PC-gap
table alone. Unclassified mixed orchestration stays unclassified until a
separate machine-code/source mapping proves a narrower label.

## Important runtime-library mismatch

The bare-metal VCS ELF uses Newlib's `expf` wrapper, its finite/error handling
and an FP32 `__ieee754_expf` implementation with FP division. In contrast, the
actual normal-library Linux llama.cpp model executable resolves `expf`,
`__expf` and `__ieee754_expf` to the same 216-byte function at `0x3adec6`.
Its ordinary path uses table-based FP64 arithmetic and conversion, not the
same division-heavy routine. Calls from the actual Linux
`akv_quant_strided_execute_impl` resolve to that function (for example,
`0x2a5488`, `0x2a5536`, `0x2a560c` and `0x2a5654`).

Inspected Linux ELF:
`verification/out/m4-prepared-installed-model-20261027-01/test`, SHA256
`a6dd98b6dc3719867f85ac63e3d4048d1b839abfd3a5bd6dddac3387dd4e54e0`.
Inspected bare-metal ELF SHA256:
`1e65300ee0561194c7f13118f4b7f09f2f0ec8a0abce842db322028edc9e8a67`.

This is a verified code-generation difference, not a measured Linux latency
comparison. It prevents transferring the bare-metal exponential instruction
fraction to model inference or motivating an exponential/divide accelerator
solely from this trace. It does not invalidate the paired software comparison:
both arms of that comparison use the same library. It limits extrapolation.

## Next discriminating step

Before another Attention optimization, align the math-kernel implementation
used for profiling with the actual runtime, or explicitly measure both library
paths on the same real captured inputs. Keep independent output, FCSR and
fallback checks. A vector exponential is an approximation unless demonstrated
otherwise; do not silently replace scalar libm or relax numerical checks to
manufacture a gain. Reusing the existing GGML RVV exponential could be studied
only under an explicit numerical policy, with complete Attention/model checks.

For resource-preserving RVV improvements, investigate whether scalar setup and
vector update scheduling can be reduced without changing libm or per-head
arithmetic order. The current evidence rejects unconditional grouped-PV
promotion; it does not identify a proven safe replacement yet. No RTL was
modified in this attribution campaign.

Raw output: `verification/out/attention-retirement-vcs-20261027-01`.
Strict analyzer and accounting contract:
`verification/akv/quantized_kv/grouped_pv/attribution/`.
