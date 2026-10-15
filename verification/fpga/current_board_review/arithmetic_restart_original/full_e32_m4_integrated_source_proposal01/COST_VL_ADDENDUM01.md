# Explicit VL-Group Accounting Correction

This independent addendum corrects the constructive cost interpretation;
the already frozen source,37-pin STATIC_BINDING and original cost document
are unchanged. No compiler, Host test, reference or DUT was executed.

Hilbert's static review identified that105 is3 seeds*35 operations, whereas
there are735 length groups (3*35*7). The original cost table's105*12 outer
allowance must not be treated as explicitly covering all735 VL selections
and transitions. Its prose was insufficient on this point.

Retain every original allowance without crediting any overlap or reducing
other rows. Add a separate735*12=8820 positive-instruction allowance for VL
groups. Within each group's12, one possible allocation is4 for length
address/index/load,2 for cap-bound decision,1 for mode initialization,3 for
length increment/limit/branch, and2 spare. The previously retained105*12 row
now accounts for seed/operation outer transitions only. The2205*8 row remains
mask/trial/mode group handling, not coverage for omitted VL groups.

```text
Original constructive sum                 2836527
New explicit VL-group allowance 735*12       8820
Corrected constructive sum                2845347
Nominal room below3000000                  154653
```

This is deliberately conservative about possible overlap with the original
allowances. It addresses the counting omission, not actual GCC lowering.
The full5985 calls,65 actual reads/call,256 FP SW/call and154350 selected mask
SB remain unchanged. Actual code, stack/caller/runtime costs and full-history
CFG have not been compiled or measured. The corrected2.845M schedule is still
not a cost gate, a compiler upper bound, reference admission or DUT admission.

Frozen identities retained:

- STATIC_BINDING.json: `884fc38a56ff96d595d2040774803d7c8879cb6b8efce9ab45fcc2fd8660e55c`
- CONSTRUCTIVE_COST.md: `5161ce1bc1e433adc1be54d72b0e0a2e1e1f318cb056879358e64f6db3e120c9`
- SOURCE_PLAN.md: `64731214bef55b769522f83f2584a11fda8caadd8cb24c6b76c4209c425bbe2f`
