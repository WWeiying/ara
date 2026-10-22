# Host Clone Member Review

Static review only. No Host, reference, CSV parse, or DUT execution performed.
Host02's actual timeout remains a failed Host execution, not a DUT failure.

## Strict

The reviewed clone still omits two mutable members: `counts` (list) and
`console` (bytearray). `consume()` modifies these through indexed increment
and append. They must be copied when capturing pre-call snapshots as well as
when cloning a snapshot for a negative test. Without this, a captured snapshot
changes as its original positive stream continues.

All other members were checked against constructor and consume/finish paths:

| Members | Required treatment and current finding |
| --- | --- |
| regs, memory | Separate dictionaries; values are integers. Present. |
| calls | Separate list and each call dictionary; each nested reads set separately copied. Other values are scalars. Present. |
| active | Must alias the corresponding new calls[ordinal], never the original call. Present. |
| offloads | Separate list and each record dictionary; fields are scalar. Present. |
| fresh | Separate dictionary and each nested set. Present. |
| counts, console | Separate list and bytearray. Missing in reviewed Host03 draft. |
| spec, gold, s, code, helpers, lookup | Mutable Python types but read-only throughout the current checker and negative tests; sharing is justified only under that contract. |
| rows, retired, csr_count, capacity, parking, cycle, main_entered, body_entered, exited, bss_next, helper, index, exit_retire, init_index | Integer/boolean/string/None state; shallow object copy isolates subsequent assignments. |

The current negative tests do not modify gold/spec. Any new test that modifies
these or their aliases must explicitly deep-copy the affected model and
rebind its dependent views; it must not mutate the shared baseline.

## OwnerObserver

Separate copies exist for count, pcs, pending, uops, owner_alloc, owner_done,
requests, arch, and retvec. Counter/dictionary values are integers or immutable
(order, insn) tuples, and list elements are integers. SHA state uses hash.copy().
first/last/maxcvx/maxuop are scalars. The shared protocol module supplies
validation functions and is not mutated by the clone or these tests.

## Required Closure

Keep all existing test assertions and time bounds. After adding counts and
console copies, demonstrate bidirectional isolation between original,
pre-call snapshot, and a negative clone, including nested reads/fresh sets,
active-to-calls identity, owner counts, and hash state. Preserve the actual
Host03 result and code identity; a narrowly scoped isolation successor can
establish the cloning correction without another reference execution.

This is not final worker admission. Final actual Host results and exact plan
binding remain required.
