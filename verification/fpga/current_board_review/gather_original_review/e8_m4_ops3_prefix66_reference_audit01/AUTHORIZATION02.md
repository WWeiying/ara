# Single Reference Audit Authorization

Main authorized one offline full raw audit, at most600s, against READY02 SHA
11aec353de588baa6981aa0e46757b76efdbcf7c0656585d5174e96aca523ebc.
Producer REBUILD02_RESULT.md explicitly confirms all readiness-bound inputs
frozen, with no further edits or runs. This written confirmation is the freeze
prerequisite. No compiler, Spike, Host or DUT execution is authorized here.

Verify retained READY SHA
f090f0d597b9e35a101a1f018a93ca9f61a04349c4243724f5c55e97094a7649
and supplemental proof SHA
7cc7582e71120bce71e5c29de897c271330ce0fa7a5c32dd6dad97dfb5c9cddd.
The latter must establish complete original/rebuilt ELF equality at SHA
a68279eaedf724eaf3efa03c71c6d039f40bc1d0c6d128b552d04e6e7ba4706b.
PRE_RAW_BLOCKER.md remains historical and unmodified; only successful actual
verification of this proof resolves its binary-identity prerequisite.

Scope: numeric first66 natural calls and65 predecessors; e8/m4/VI31,
VL256/vstart128 endpoint, capacity512, vlenb128, physical predicate128bytes.
Not unknown-stall reproduction, full2688 execution, Linux replay or DUT PASS.

invoke_once.py exclusively creates execution records, runs audit.py once with
590s inner alarm/600s outer bound, waits for actual exit, and records even failure.
No automatic retry. Auditor and its code inputs are pinned before invocation.
