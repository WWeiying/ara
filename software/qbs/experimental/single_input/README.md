# Guarded single-input SDK loop experiment

This is not a replacement for the production SDK. Apply the registered patch
only to an isolated, checked copy of `qbs_runtime.c`; production sources, public
ABI, native executor, memory fences and RTL are unchanged.

The candidate retains all public validation and specializes only M1 plans with
whole-K commands, no activation gathering and no segmented weight views. It
prepares descriptor headers outside the output-tile loop and advances checked
weight/output cursors. The generic iterator remains responsible for other
plans. Plan, options and input storage must remain stable during the blocking
call, as in the original execution contract. Executor errors return immediately;
the candidate does not retry, fall back or issue an extra context release.

`noinline` keeps the helper as a separate function, but does not prove that the
generic caller's stack frame becomes smaller. Check the actual target assembly.
Do not count host mock execution as native hardware fault-recovery validation.

## Evidence and acceptance

`verification/performance/end_to_end_baseline/prepare_sdk_single_input.py`
creates independent baseline/candidate namespaces and checks complete command
arguments, addresses, context transitions, failures, output/workspace bytes and
canaries. GCC and Clang+UBSan each passed 24,535 cases; all seven original SDK
fixtures passed for each version. Failed preparation attempts are retained.

`build_sdk_single_input_native.py` builds one ELF containing both SDKs and the
accepted real Qwen3 Decode operands. The target order is baseline/candidate/
candidate/baseline. Both cold and warmed baseline times are retained. The
production quantizer, exact output oracle, CSR checks, command work, independent
protocol checker and source/image identity checks are unchanged.

The collector accepts a functionally correct experiment even if performance is
unchanged or worse. A passing experiment is not production promotion: review
repeatable whole-call benefit first. This experiment has no measured area result
and does not establish complete-model timing.

The VCS pair completed with independent replay: original execution cycles
146111/145929 versus candidate 141131/140927, a 1.03539x ratio. Including
preparation, region cycles are 228260/228118 versus 223355/223015 (1.02242x).
Mean QBS busy changes by only +6.5 cycles; the execution reduction is 4991
cycles per trial. All 112 commands and 3584 outputs passed. The compact receipt
is `verification/performance/evidence/sdk_single_input_20261106_01/result.json`.
This scoped benefit is not a whole-model speedup or production promotion.
