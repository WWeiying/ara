# Pre-Execution Host Harness Review

No static blocker found in host.c6106227c... and execute.py7121df40...
under the existing conditional authorization. Reviewer did not execute them.

The independent reference is literal original C: execute.py extracts its exact
oracle block and index functions, and separately ports the whole original C
loop with only entry/syscall/exit adaptation. C helper outcomes use original
fixtures and indices, not generated Python rows or packed record predictions.
Packed error C is retained byte-for-byte; only scalar SD/SH/LWU are instrumented.

Each call checks actual32-bit input values, untouched upper4032B per bank,
128 mask bytes,130 initialized output bytes, argument/order and49 fresh events.
Both allowed values of every result bit are exercised through each legal base
and single-bit inversion; additional two-bit, guard and status mutations compare
exact original error counts and flags. The original and packed whole17920
transcripts are compared for positive, first21 erroneous calls and mixed-error
modes. Status changes include high bit63, avoiding accidental32-bit flag masking.
The five fixture mutations require numeric exit90 plus the specific rejection
condition; missing same-value fresh stores cannot pass by stale equal memory.

This is C source/oracle evidence only. It cannot establish real FMV payloads,
RVV behavior, target memory instruction counts or actual ABI. Those remain
linked/runtime obligations. UBSan trap instrumentation is configured; no claim
of its actual execution is made by this static review.

Generation and each Host/build command have120s caps. common.command persists
actual wait exit/timeouts before enforcing expected outcomes. Any exception is
recorded as FIRST_FAILURE and prevents subsequent target builds. Both target
builds are downstream of all six complete original/packed modes and five
specific negative receipts. There is no reference/simulator invocation here.
Full linked CFG cost remains a separate bounded stage, not implicit compile PASS.

Reviewed hashes:

- host.c: `6106227cc6549b1621c3c9315a063532fde87ea361ad971b8586bf6bfc156807`
- execute.py: `7121df40fa2bb45bd2c6a049d22bf0824ab9d367fe663dcc00697377696ea065`

No source or harness edits requested. Preserve failed attempts, if any, rather
than weakening diagnostics or retrying target compilation with different flags.
