# Grouped PV: fewer vector requests, longer complete call

## Measured evidence

The accepted same-ELF ABBA result is a 2.3609% cycle regression. Replaying
the existing `ARA_CONTRACT_TRACE` records gives identical counts in the
two OFF trials and in the two ON trials:

| Accepted request category | OFF | ON |
| --- | ---: | ---: |
| Vector load | 2123 | 1438 |
| Vector store | 1379 | 1334 |
| Vector arithmetic/configuration | 3934 | 3249 |
| Other offload | 11 | 11 |
| PV FMA at the identified instruction encoding | 768 | 768 |

Counts use UART BEGIN/RESULT boundaries. They include setup and result
checking outside the timed call, and must not be divided by the measured
call cycles to claim IPC. Only accepted requests from one trace source are
counted; the accompanying UVM records are not counted a second time.
No scalar retirement trace was enabled.

Reproduce with:

```sh
python3 -B verification/akv/quantized_kv/grouped_pv/trace_mix.py \
  verification/out/grouped-pv-vcs-pair-20261026-01/work/run.vcs.log
```

## Static findings and limits

The exact measured ELF disassembly is
`verification/akv/quantized_kv/grouped_pv/pair/out/build-gnu-01/07-disassemble.log`.
The baseline MAD callback at `0x80002b56` uses LMUL8, loads V and Y, and
executes `vfmadd.vf`. The grouped loop at `0x80003e6e` uses LMUL4,
loads V once outside the head loop, and executes `vfmacc.vf` at `0x80003eac`.
For D128/VLEN1024 both LMUL choices fit the dimension in one vector chunk.
There are no whole-register vector spill instructions in this disassembly.

The grouped path computes coefficient arrays before the PV loop and revisits
the heads to update sums afterward. It also executes `divu` at `0x80003e1c`
on the per-token path when heads exceed one. This implements the safe
span-overflow check in `akv_grouped_pv_update`, not numerical division.
The measured shape has six heads and 128 tokens. The check's placement is
a concrete candidate for avoidable scalar work; its dynamic cycle cost has
not been measured. It is not yet a proven explanation of the entire regression.

Removing the check without replacement is incorrect. The public leaf accepts
arbitrary stride, and the schedule invokes callbacks. Any future hoisting
must preserve overflow, alias, argument validation and failure behavior,
including the documented response to a callback corrupting the plan.

## Decision

Keep grouped PV default OFF. Do not infer that fewer vector requests guarantee
lower latency, or that additional QBS hardware is needed to solve this result.
Prioritize the independently validated Q8_K preparation integration. Revisit
grouped PV only with a clear invariant-preserving change and a bounded paired
measurement that can separate scalar checking/coefficient overhead from the
vector execution path.
