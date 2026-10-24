# Complete-call stateless candidate gate preparation

The new ELF links the generated candidate runtime, not `native_bench.c` and not
the benchmark's process-wide dispatch switches. The test supplies `getenv` as
a harness fixture so it can request OFF/ON/OFF within one ELF. Only the harness
owns that request value; the runtime selects once into a call-local variable
before FULL. No canonical source or running consumer is modified.

| Case | D | Real heads | KV | OFF / ON / OFF commands |
| --- | ---: | ---: | ---: | --- |
| Small odd group | 64 | 3 | 1 | 197 / 84 / 197 |
| Odd group across tile boundary | 96 | 3 | 65 | 774 / 373 / 774 |
| Existing six-head specialization | 128 | 6 | 7 | 137 / 137 / 137 |
| Even-group neighbor | 128 | 2 | 64 | 386 / 98 / 386 |

Total12 native calls and3680 AKV commands. Q/K/V values come from the accepted
real Qwen2.5 KV128 capture, selecting the actual KV group and its associated
Query heads. D64/D96 channel slices and shorter visible KV are derived inputs,
not new captures of a model with those dimensions. Token/head strides remain
explicit: Query320B, K/V256B, output512B. Initial output/workspace and all
output gaps are poisoned/reset outside the native call.

Every ON and restored OFF output is compared across all4096 output bytes with
the first OFF result, including inactive rows and gaps. Active outputs must be
finite. RNE, VCSR5, FCSR equality, descriptor integrity, Q/mask immutability and
outer guards are checked. This is exact regression against the original
generic numerical path, not an independent complete-Attention oracle. It does
not claim K/V byte-immutability checks, unsupported-capability hardware
execution, multithread acceptance, original model golden or performance.

The raw-log checker validates every command in order, including mixed PANEL4
and single-column commands for odd heads, row loads and lifecycle. Short tiles
use actual resident byte enables: column replay is2*T bytes per logical column,
and `akv_v2_context.sv` issues ceil(T/8) bank groups. These counts depend on
resident T, not the arithmetic VL in an unrelated fixed-residency fixture.
For KV65, the final REFILL has one token, not64. No late checker relaxation
should substitute for proving these RTL semantics.

```sh
python3 -B -m unittest discover -s verification/akv/paired_heads \
  -p native_runtime_test.py -v
python3 -B verification/akv/paired_heads/build_native_runtime.py \
  --output <FRESH_BUILD_DIRECTORY>
```

Recorded build03: `verification/out/akv-native-pair-runtime-build-20261024-03`,
`BUILT_NOT_EXECUTED`. It uses reviewed structured GNU compiler invocations,
rebuilds all objects, links original feature handling/libm and verifies the new
ELF bounds and real runtime/leaf symbols. Three strict log tests pass, including
intentional corruption. Build01 retained a link failure because the original
leaf-only build did not need features/libm; the complete-call successor does.
Build02 linked successfully;03 adds independently checked ELF memory bounds.

The new `run_native_runtime.py` worker requires the pending real KV256 gate,
including actual simulator exit0, independent UVM, original typed build and
raw-log replay. Its host fail-closed tests pass; actual build-only preflight
also passes in `verification/out/akv-native-pair-runtime-preflight-20261024-01`.
That preflight explicitly does NOT claim the still-running prerequisite passed.

The event-driven handoff can wait on the original KV256 owner's pidfd and exec
this worker under the same service after terminal PASS. It does not poll logs,
retry failures or edit any source. The downstream worker still revalidates all
typed prerequisite evidence itself; the handoff's PASS check alone is not
enough. Freeze these helpers after queuing them. Each downstream simulation
also enforces actual exit, original independent UVM/AXI checks, complete
numerical/work logs and pre/post source/image identity. A synthetic checker
PASS or successful link must never be called RTL acceptance.
