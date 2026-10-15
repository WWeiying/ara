# Diagnostic Budget Stop And Constructed Short Profile

## Preserved Outcome

The sole closed-CSV diagnostic failed its own fixed deadline. This is not a new RTL failure, not a completed prefix acceptance and not a reason to rerun the DUT. No further captured CSV/reference read or hash was performed for this investigation. Frozen diagnostic, checker, transport and producer remain unchanged.

- `../diagnostic01/diagnose_wait.json`: actual child wait1, elapsed598.9808413609862s, timed_out=false, retries0. SHA256 `6079cc8a090cf193cda4b1bab4576faf69bdb561920b33656e09ffcf52ea8638`.
- `../diagnostic01/run01/firstcause.json`: `ValueError: Abort/fixed diagnostic deadline`, elapsed595.5447973748669s,978944 consumed rows,111733676 bytes hashed, active original call1457. SHA256 `27e5354a8a85a3a9623727ba58dcb5fc9e2828b232bed784ed254966b02bf04b`.
- Last consumed record: cycle7634276, retire914452, PC800004ac, insn2f06b703. Next attempted record at physical line978946: cycle7634277, PC800004b0, insnc0c710e3; deadline check occurred before its strict consume. Do not label this instruction a numerical failure.
- Original CSV stat identity before/after is equal, size296607084B. The recorded SHA is only the111733676B actually read, not a whole-file hash. The stopped transport may have observed the final yielded row before strict consumption; it has no completed before/after-delivery proof.
- Original DUT timed_out/rc255, producer NOT_PASS and collector NOT_ACCEPTED remain authoritative. Accepted scope stays18/22. Previously consumed calls are not independently accepted by this failed diagnostic.

## One Authorized Short Profile

`run_once.py` bounded one child to120s and durably saved numeric wait before result inspection. Actual wait0/17.38245306396857s, timed_out=false, retries0. It did not open the captured CSV or old reference. No compilation or ISA/simulator execution occurred.

The existing sealed real-ELF Builder supplied10994 constructed records: four complete original calls plus the fifth helper entry. Original4095 model was initialized but no full4095 stream was generated/consumed. Strict, six-event observer and per-completed-call owner checks were unchanged. Profile excludes fixture/model/Strict construction; it includes transport consumption and partial-EOF summary.

| Component | Measured |
| --- | ---: |
| Specification/model setup (unprofiled wall) | 9.4086s |
| Fixture construction | 1.1518s |
| Strict construction | 0.1153s |
| Profiled consumer wall | 4.8211s |
| cProfile accounted time | 4.762s |
| Two JSON dumps/row,21988 calls (cumulative) | 1.396s |
| Generic rows wrapper (cumulative, includes JSON/observe) | 2.655s |
| Strict.consume (cumulative, includes begin_call) | 1.509s |
| Five Strict.begin_call calls (cumulative) | 0.515s |
| Strict.value,31398 calls (cumulative) | 0.417s |
| Two digest updates/row,21988 calls | 0.138s |
| memory_op,10813 calls (cumulative) | 0.106s |
| Three per-event gap calculations,32754 calls | 0.102s |
| Eager Counter construction,10994 calls | 0.078s |
| Four completed-call owner checks | 0.001s |

Nested cumulative figures are NOT additive. JSON is29.3% of accounted short-profile time; begin_call10.8%, SHA updates2.9%. This proves avoidable overhead, not an exact raw-run attribution. Short profiled consumption is about438.5us/row; the failed real scan averaged about608.4us/consumed row including all startup, parsing, hashing, workload differences and shared-machine scheduling. cProfile adds overhead; no CPU-time/resource measurement was collected. These are compatible with multi-minute Python processing, but do not prove JSON alone explains all596s or establish a whole-file completion estimate.

## Static Findings

1. `ordered_reduction/original_remaining9_terminal_audit01/observer.py:47-57` serializes all14 field/value pairs twice per record. Equality already proves the post-yield tuple matches the pre-yield snapshot. JSON serialization/validation dominates the measured transport cost; SHA itself is relatively small.
2. Sentinel `checker.py:132-151` repeatedly constructs per-byte source values using `value(address,1)`, which itself performs both membership and sum generator traversals. It also rechecks upper BSS bytes with the same helper. This is real every-call work, not repeated model generation.
3. `diagnostic.py:100` executes `setdefault(bin,Counter())` every row, constructing and discarding a Counter even for an existing bin. Point dictionaries and gap checks also allocate at row rate.
4. `model`, `specification`, `rom` are lru-cached. `Machine.initial` only walks in-memory ELF segments; it does not reread ELF on scalar loads. No per-row full model/ROM regeneration or growing whole-call-list scan was found in consume. Endpoint summary scans occur only at EOF and were not reached in the failed raw run.

## Proposal Only, Not Implemented Or Authorized To Rescan

For a future separately reviewed sidecar, keep the original semantic checker and token observer unchanged:

- Serialize the exact original14-field tuple once before delivery. After exact post-yield tuple equality, update the after digest with the retained identical serialized bytes. This preserves existing JSON digest bytes, full field coverage, ordering, type checks and before/after SHA; do not remove the equality assertion or reuse bytes before proving equality. Require mutation/drop/duplicate/field/type/order negatives plus digest equality to the old wrapper on constructed fixtures. This removes only the second serialization, not all1.396s; no600s completion guarantee follows.
- Remove eager per-row Counter creation using an explicit missing-bin branch. Keep every event and cycle counted. This is an allocation optimization only.
- If still necessary, a later strict successor could gather exact initialized bytes with missing-byte rejection and compare immutable source byte strings rather than repeated width1 generator/sum calls. Preserve all1028 fresh output bytes, every a/b/mask value and upper BSS byte, source epochs, original gold and all129 output reads. Prove byte-for-byte equivalence and missing/changed-byte rejection before use. Do not omit checks because values were equal on a prior call.
- Immutable instruction decoding can be cached by actual insn with unchanged illegal-instruction rejection, but measured2.2% memory_op cost makes it lower priority.

None of these proposals changes the raw-read authorization. No successor scan is started, no sealed code is edited, and no bound is extended. Hilbert reviews the failure using small metadata only.

## Evidence

- `actual_wait.json`: `81d9d23f233b24ccf560aed896afbc14a7be8f8563a435909696f0727c3ff19e`.
- `result.json`: `a098d366503725696ba3c66701ea8c1d2f87117c249ebdecba64aabcbb39dd0a`.
- `consumer.pstats`: `641a4d7ae004e902e7bb91e7141f92d0c9f4e45303a635f3306510368c3af6da`.
- `consumer_top.txt` contains actual pstats cumulative ranking; `result.json` contains all function counts/times, source hashes and explicit constructed-only scope.
