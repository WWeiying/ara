# Register-PV full-call RTL experiment

## Scope

This experiment compares current shared RVV Q8_0 decode plus PV with the
register-PV candidate. It is not an old scalar decoder comparison, a change
to QBS hardware, or a whole-model speedup measurement. Production defaults
remain unchanged.

Real inputs are the audited Qwen3-1.7B capture used by the current Prefill
campaign: query position 19, D=128, two query heads associated with KV head 0,
20 visible tokens in a physical cache with 8 heads and capacity 256. K is
Q4_0 for the first run; V is Q8_0. The builder also supports the separately
captured Q8_0 K dataset. Head-major payloads are byte-permuted to token-major
storage, never requantized. All five tensor binaries and metadata files are
checked against the capture audit.

## Controlled comparison

| Item | Baseline | Candidate |
|---|---|---|
| Complete call | `akv_quant_strided_execute` | `quant_register_execute` |
| Admission/content checks | Current shared implementation | Same, plus actual CSR guard |
| QBS commands per trial | 1 | 1 |
| Query rows quantized | 2 | 2 |
| K panels / copied bytes | 1 / 1440 | 1 / 1440 |
| Q8_0 V rows processed | 20 | 20 |
| V intermediate | F32 workspace | RVV registers |
| Output words | 256 | 256 |

ABBA order is baseline/candidate/candidate/baseline in one ELF. The timer
includes admission, query quantization, K gather, QBS QK, online softmax/PV,
normalization and completion drain. Output formatting/checking is outside the
ROI. The comparison includes any cost of the candidate's extra guards; it
does not subtract them analytically. No CPP dispatch/allocation or other model
layers are included.

The same scalar scale/fused-MAD arithmetic contract is retained. All four
outputs and FCSR must match exactly; each output is also checked against the
captured GGML reference with `2e-5 + 2e-5*abs(reference)` tolerance. Padding,
guards, activity, VCSR and ordered trial completion are checked. An independent
AXI/protocol checker and simulator source/image checks are mandatory before
declaring PASS. Failed or truncated trials are not performance results.

## Build and run

Files are in `verification/akv/quantized_kv/register_pv/`:

- `native_main.c`: real data full-call ABBA and in-guest checks.
- `build_native.py`: fresh 17-object build, audited capture and dependency pins.
- `check_native.py`: strict experiment identity plus shared ABBA/output checks.
- `test_native_check.py`: positive cases and malformed/incorrect result tests.
- `run_native.py`: canonical VCS worker, independent protocol checker, 3h bound.

First build:
`verification/out/register-pv-native-q4-build-20261028-01`.
ELF SHA256:
`c055eb4a6014a09d086dd6849a4659207075e086140b6aba257468b861e7e086`.
Preflight:
`verification/out/register-pv-native-q4-preflight-20261028-01/result.json`
is PREFLIGHT_NOT_RUN with matching pins. This is not execution evidence.

The intended run directory is
`verification/out/register-pv-native-q4-vcs-20261028-01`.
The directly owned worker service is
`register-pv-native-q4-20261028-01.service`; its separate stdout/stderr log is
`verification/out/register-pv-native-q4-service-20261028-01.log`.
Consult its result JSON and protocol receipt for final status; this document
does not predict or assert a speedup. Do not edit pinned inputs while it runs.

## Acceptance beyond this point

This first paired point is discriminating, not sufficient for promotion.
Any benefit must survive another real shape/head/context point and model-level
numerical regression before integrating the shared implementation into GGML.
If whole-call performance regresses, retain the current runtime and analyze
the issued instructions/register moves and memory traffic before another change.
