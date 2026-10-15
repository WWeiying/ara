# Full682 Independent Model Cross-Check

The main reviewer executed a read-only Python cross-check of
`full682_vcs_m8_plan01/model.py` against the archived fixture in
`prepared02/prepared/alias_v8_e16m8_prefix682/original/fixtures.h`.

All six comparison operations times 16 times 16 input pairs (1536 result and
exception-flag pairs) agree. All 682 modeled parameters and their order match
the original `call_sequence.json`, including seed, operation, VL, predicate
mode, sticky flags and vstart. The modeled scope is 349184 result bits and
1364 guards. The actual command returned zero with zero mismatches.

This finite fixture check does not prove every FP16 encoding, dynamic helper
execution, VRF history or DUT results. Those require the strict full trace
checker and a completed frozen-M8 simulation. This separate note does not
alter the preparation's pinned evidence or previously accepted receipts.

## Independent Dynamic-Checker Host Tests

The main reviewer ran `python3 -B -m unittest` selecting all four current
`StrictTests` methods, without invoking the module's artifact-writing main.
Actual process exit was zero: four tests, 202.402 seconds, `OK`.

The positive witnesses cover all 682 calls with both allowed-tail choices.
The negative matrix rejects 18 mutations: repeated capacity, helper interior
without entry, omitted predecessor, bad input, byte enable, unknown source,
wrong pointer, bad boxing, vstart, flags, omitted CSR restore, duplicated
interior, missing final result byte, wrong VL0 alias bit, active bit511,
corrupt golden table, guard and terminal exit. Each helper's interior was
also rejected when presented outside a valid helper window. These synthetic
Host witnesses do not establish an actual Spike or DUT trace PASS.

`strict.audit` filters non-retirement events after checking their whitelist.
Therefore a separate lifecycle audit is required for any claims about CVX,
architectural request or backend allocation/completion matching. This gate
was communicated to the worker owner; no such matching claim follows from
these four Host tests alone.
