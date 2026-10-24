# Shared Quantized-KV Execution Entry

The experimental implementation now has one C-callable entry suitable for a
C++ GGML adapter and a native benchmark. It packages the previously prepared
DIRECT-QK/shared-V online schedule; it does not enable a production fast path
or add an optimization variable to the running experiments.

| File | Responsibility |
|---|---|
| `software/akv/experimental/quantized_kv/runtime.h` | Public C/C++ ABI, callback bindings, status/report and workspace queries |
| `runtime.c` | Checked public entry; rejects insufficient or misaligned caller workspace |
| `native.h` | Private C implementation: admission, packed Query preparation, DIRECT descriptors, group traversal |
| `selection.h` | Exact type/shape/layout/capability/numerical-domain admission before issue |
| `online.h` | Shared score tiles and token-order online Softmax/PV |

The public function is `akv_quant_native_execute`. The caller supplies the
production Query quantizer, V decoder, F32 scale/MAD helpers and existing QBS
executor. No quantizer, fake arithmetic or reference model is compiled into
the implementation. C++ includes only the public ABI; arithmetic is compiled
as C with an explicit FP contraction policy. The sealed online header consumed
by running experiments has not been edited for this packaging work.

## Execution And Storage

1. Validate bindings and workspace capacity/alignment. Run full-operation
   admission, including all groups' visible scales and Query inputs.
2. Reject workspace overlap with any input, mask or output before changing
   workspace or destination tensors. Report storage must be private as well.
3. For each KV head, quantize its actual Query heads into tight row-major
   scratch. The packed row size is `D/32*34`, not the maximum allocated row
   capacity: using a fixed D256 stride for D128 would be incorrect.
4. Invoke the common online schedule: DIRECT QBS groups4/2/1 and N32/tails;
   each V token decoded once per KV group, then used by all its Query heads.
   K is read directly from the admitted actual head/token base.
5. Write through the caller's actual output head stride. Complete a group only
   after normalization returns. No padded output words are intentionally written.

The fixed caller-owned workspace is about 4.25 KiB in this ABI. It contains
quantized Query rows, one descriptor, score tiles, one decoded V row and online
M/S state. This is software scratch, not a new hardware SRAM. There is no heap
allocation, global accelerator reservation or activation-context reuse in this
entry. Caller controls whole-call serialization, lifetimes and normal-memory
properties; DIRECT must not be replaced with implicit reuse of another operation's
activation context.

## Failure Contract

- `AKV_QUANT_NATIVE_FALLBACK`: returned before quantization, executor callbacks
  or destination writes. The ordinary runtime can execute the original path.
- `AKV_QUANT_NATIVE_EXECUTION_FAILED`: a callback failed after execution began;
  output may be partial. Propagate the error; do not silently restart fallback.
- `AKV_QUANT_NATIVE_OK`: every admitted KV group completed.

The report's `command_attempts` counts calls to the executor, including a failing
attempt. It is not a hardware issue/accept counter. `value_decodes` counts logical
decoder callback completions, not DDR transactions or functional-unit activity.
Hardware exceptions and OS recovery remain responsibilities of the actual
executor/system; an injected callback error is not a Linux page-fault test.

## Host Contract Tests

`python3 -B verification/akv/quantized_kv/test_native.py` runs:

- 96 combinations of D32/96/128, GQA1/3/6/7, one/two KV heads, visible length
  1/33 and both exact K profiles. QBS arithmetic uses the actual `qbs_ref.c`.
- Comparison with a head-major online arithmetic reference, including complete
  output padding. The fixture quantizer deliberately emits valid scale-1 Q8_0
  blocks from integer Query inputs. It is a binding/layout unit fixture, not
  proof that the production GGML quantizer or real model executes correctly.
- A reference-only alignment copy allows M1 arithmetic comparison for odd
  packed Query rows. Candidate command bases must already be aligned; the
  candidate is not allowed this hidden copy. QBS reference output has register
  stride 32, including N tails, rather than tightly packed M-by-N rows.
- Disabled selection, insufficient workspace and workspace aliasing must call
  no compute callback and preserve output. A NaN in the last Query head or
  later KV group's visible K/V scale, and a mask hole, must also reject before
  the first command, not after an earlier group executes.
- First-command and later-group executor failures must return execution failure
  with exact completed-group/attempt counts and no automatic retry.
- GCC execution, host Clang ASan/UBSan execution and public C++17 ABI compilation.

The shared C implementation also compiles with the actual GNU bare-metal RV64
toolchain and exports only the public entry/workspace queries. That object
compilation is not VCS execution or a model/performance result.

## Integration Gate

The running whole-Attention inquiries still use their sealed benchmark sources.
They are not retroactively claimed to execute this new entry. After their
numerical and benefit gates pass, a successor real-data benchmark must bind
production callbacks to this entry, include admission in full-path timing, and
regress ordinary/F16 fallback. Only then should the same C entry be installed
in GGML selection. Existing source defaults, ISA, RTL and runtime remain unchanged.
