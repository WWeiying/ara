# Independent Host Evidence Review

Decision: **ACCEPTED_FULL10752_HOST_COMPOSITE_ONLY_NOT_REFERENCE_OR_DUT**.

Reviewed existing receipts/logs/UART and input/evidence identities only. No Host binary, compiler, generator or CFG analyzer was rerun by this reviewer.

## Actual Outcomes

- Original Host compile: actual0, 4.977836seconds. Original independent-C positive: actual0, 0.216550seconds, all10752 calls / 5526528 output-and-guard bytes /10752 saturation values checked.
- All eight diagnostic runs: actual0 with the required original-versus-packed error behavior. The active mixed case produces35 counted errors and20 printed details. Ten complete original/packed UART pairs (nine original runs plus the sanitizer positive) are byte-identical.
- All four lifecycle mutations: actual90 at the intended first mismatch, not an unrelated generic rejection: source assignment bank/offset/value (calls0), cumulative mask offset/value (calls0), missing second-call initialization offset (calls1), and missing actual-read offset (calls1).
- Original UBSan link: actual1, 7.933966seconds, exactly `/usr/bin/ld: cannot find /usr/lib64/libubsan.so.1.0.0`. host01/FIRST_FAILURE.json and all failed link artifacts remain. This was an environmental link failure, not a numerical result or sanitizer finding. host01 itself was not relabeled successful.
- Narrow successor: same three Host translation units and original sanitizer flags, plus `-fsanitize-undefined-trap-on-error` and a fresh output path. Actual compile0 /6.682128seconds; full positive0 /0.416730seconds. Its positive output log equals the original positive log byte-for-byte.
- Explicit signed-overflow control: actual **-4 (SIGILL)** /0.216228seconds, confirming trap instrumentation is active; the control disables core dumps. Trap mode intentionally lacks the dynamic runtime's detailed UB diagnostic, but does not recover or silently disable undefined-behavior checks.

The accepted composite binds18 actual child receipts:13 exit0, four expected exit90, one expected SIGILL. All are below120seconds, with no timeout/executor error. The old failed link receipt is separately preserved and excluded from those18. The already completed nine positive/diagnostic and four lifecycle runs were reused, not repeated; only the previously missing sanitizer stage and its small trap control were added. No outer-process exit is inferred from the presence of a composite file.

## Scope And Identity

Full source-data/event obligations remain10752 calls, 5505024 result bytes plus21504 guards,10752 saturation values,4416 ordered source assignments,336 mask epochs,5376 clear SD events,70644 selected mask SB events,698880 output initialization stores and698880 actual output reads. This is native Host behavior using the independent original C oracle, not original RVV/CSR execution.

Independently rehashed31 input pins and85 evidence pins with no mismatch. Actual on-disk receipts equal the composite copies; log hashes match. The sanitizer compile command differs from the failed one only by the stated trap flag and output location. SOURCE_STATUS and all reviewed generator/source/harness pins remain unchanged.

Composite: `execution01/ubsan_trap01/HOST_COMPOSITE.json`, SHA256 `f7155fe4f778fe42884f022aa0489d9c3531ca664deaecf9989d8bf9169b5ac4`.

This closes the Host prerequisite for the parent's already authorized fixed-flags SoC/Spike compilation and actual code/cost inspection. It does not accept linked helper identity, the memory map, CFG cost, a firmware reference or DUT run. **Any actual complete CFG cost above3M remains HOLD.**
