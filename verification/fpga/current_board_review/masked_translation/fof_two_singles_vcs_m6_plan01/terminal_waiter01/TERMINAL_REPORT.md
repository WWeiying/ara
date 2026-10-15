# FOF2 Terminal Acceptance

Metadata-only closeout: producer and independent terminal results both PASS.
No CSV/raw reparse, new test, service query, or sealed-file modification was
performed for this report.

| Selected source single | Actual seconds | Scalar checks | Business VL | Completion VL | vstart | CVX exceptions |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| e8/scenario0 | 234.0308 | 5477 | 4 | 8 | 0 | 0 |
| e64/scenario5 | 246.7186 | 5481 | 8 | 8 | 0 | 0 |

Both persisted monitor and child numeric exits are0, elapsed values agree with
producer/independent results, and no abort, timeout or failure is recorded.
Exact two-case membership and original SoC ELF identities match the sealed plan.
The producer records unchanged744 input pins; the plan retains all118 reference
pins. This closeout checked metadata bindings, not a repeat hash walk of raw
inputs. The independent terminal audit already checked those pins and performed
one full CSV pass per case.

Original defined oracle is unchanged: e8 final out[5..8] remains unconstrained;
126 final output elements are checked, versus130 for e64. e64 old-vd remains
uint64 value0x5b. Both retain original guards0/9, initial130 elements, full page
maps/mask checks, original helper/capacity and completion CSR context.

## Bound Evidence

- Plan `../prepared01/plan.json`:
  `da842f3be54dc8d15eaf4b6551766152c375e97321624c525f9350dbc16affa1`
- Producer `../prepared01/complete.json`:
  `aeada7563cde5c17c7df9ab8e28187b0df52882da0b282d061be810656bac5bb`
- Independent `terminal01/result.json`:
  `0a305cbdd84a6acc88ab710356845ebef0e5b9a34fe8de3e4d39e3f1d72a2aa7`
- Waiter READY:
  `c4632f8f1706862fc1bc5859155ac7ac8ea258a99c1ac1a52ad9a4fe1a960211`
- Parent authorization:
  `3ab346dd13ece0c535ec5b9e01679e394ff0f4fac045ca4fe8246fefc429eb50`

Main reports a live observation while both units were still present (chunk
`e21a39`): `inactive`, `Result=success`, `ExecMainStatus=0` for
`ara-fof-original-two-m6-01` and `ara-fof-original-two-m6-terminal01`.
This is explicitly Main's observation, not a new measurement by this report or
an inference from garbage-collected unit defaults. The sealed independent
result's earlier NOT_QUERIED service field is preserved unchanged.

Accepted scope: **two selected source-derived real Sv39 FOF singles on M6**.
Not all eight historical failures, not Linux signal equivalence, and not proof
of zero physical MMU activity.
