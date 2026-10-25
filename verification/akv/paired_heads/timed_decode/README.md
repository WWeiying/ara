# Timed Native Decode Successor

Preparation only. No cross-build or VCS execution is authorized by this directory.
No canonical source or predecessor helper is changed.

## Scope and Timing

The SHA-pinned `../native_runtime_main.c` is rendered with exactly three reversible
substitutions. Cases remain D64/H3/T1, D96/H3/T65, D128/H6/T7 and D128/H2/T64;
each remains OFF/ON/OFF. All real input selection, 4096-byte output comparisons,
FCSR/VCSR, input hashes, descriptor comparisons, finite-value and guard checks
remain byte-for-byte in the inverse-transformed source. Expected work is still
12 calls / 3680 AKV commands. This remains derived captured data, not whole-model
execution or an independent full Attention oracle.

The first `rdcycle` is immediately before the public
`akv_attention_execute_v2_native` invocation, with a compiler memory clobber.
The second is in the existing drain assembly, after `vmv.x.s v12` and
`fence rw,rw`, before FCSR/VCSR reads. This includes runtime validation/admission,
all work inside execute, call overhead and the existing drain/fence. It excludes
caller query preparation, plan construction, post-call numerical/guard checks
and UART. There is no subtraction of timer overhead.

The convention is the same as the predecessor Decode/Prefill harnesses.
`hardware/deps/cva6/core/acc_dispatcher.sv:452` sets the store-barrier wait while
`acc_resp.store_pending` is asserted and drives `ctrl_halt` from that wait.
This is not a new independent proof that every external write response is
drained. The build checks the actual main disassembly for two cycle reads around
the real call and contiguous drain/fence/end-cycle/CSR ordering. No disassembly
acceptance is claimed before a build is authorized and completes.

Each timing line immediately precedes its unchanged RESULT line:

```text
NATIVE_PAIR_TIMING case=0 trial=0 start=100 end=3070 cycles=2970
```

The checker requires all 12 ordered pairs, exact full-line fields, positive
64-bit nonwrapping intervals, `cycles=end-start`, monotonic call intervals and
`cycles >= sum(command busy_cycles)` for the call. Only validated timing lines
are filtered before the original strict checker runs. All command records are
retained for subsequent exact per-command old/unified comparison.

## Build Contract

`build.py` consumes a checked original **canonical live Decode** build, not the
experimental candidate build. Its original flags/link order and pinned capture,
runtime, assembly, support and feature objects are retained. Only timed main is
compiled; all 12 other objects are reused and hash-listed. Link is fresh and
allocation remains within the accepted 16 MiB map. GNU tools and static libraries,
transitive Python helpers, generated main, source dependencies, commands and
artifacts are pinned and checked. `old_runtime_objects_reused=true` is explicit.
The new `akv-timed-decode-v1` schema is NOT the original `checked_build` contract.

Commands for parent review, not executed by preparation:

```sh
python3 -B verification/akv/paired_heads/timed_decode/build.py \
  --base verification/out/akv-live-decode-build-20261024-01 \
  --output verification/out/akv-timed-decode-build-01

python3 -B verification/akv/paired_heads/timed_decode/run.py \
  --build verification/out/akv-timed-decode-build-01 --variant baseline \
  --output verification/out/akv-timed-decode-baseline-preflight-01 --preflight-only

python3 -B verification/akv/paired_heads/timed_decode/run.py \
  --build verification/out/akv-timed-decode-build-01 --variant unified \
  --soc-build /absolute/path/to/checked-unified-soc-build \
  --output verification/out/akv-timed-decode-unified-preflight-01 --preflight-only
```

The baseline selects only the original accepted image receipt; unified requires
`checked_soc` and storage variant `shared_reader_unified_q2_kv32_v1`. Both consume
the same timed ELF. Actual runs require separate fresh output directories, no
`--preflight-only`, and direct-owned systemd workers after explicit approval.
Simulation timeout is at most 10800 seconds, with bounded pre/post and UVM phases.
No queues, polls or automatic launches are implemented. Actual acceptance includes
source/image manifests, image-memory contract, raw checker and independent UVM
backend/AXI/write checks, all bound pre/post to receipts. Functional run PASS does
not assert old/unified performance acceptance. That requires a later paired audit
of the same ELF, every call's cycles and exact command ledgers.

Host-only tests (synthetic logs, no EDA/build invocations):

```sh
python3 -B -m unittest discover -s verification/akv/paired_heads/timed_decode -p 'test_*.py' -v
```
