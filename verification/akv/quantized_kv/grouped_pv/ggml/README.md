# Grouped-PV Actual GGML Successor

Review candidate only. No build, QEMU, EDA, or commit is authorized by this
directory. Existing graph fixtures, runners, snapshots, external source and SDK
are not modified. This successor carries its own explicit external snapshot.

## Contract

Same captured Q4_0/Q8_0 K, Q8_0 V, 12 query heads, two KV heads, D=128;
contiguous and physical token-major views; visible prefixes 128 and 5.
The byte permutation, metadata checks and complete input checks are derived
from the frozen ggml_strided/test.cpp contract, not a new capture format.

For each shape, obtain ordinary GGML and GGML use_ref results. use_ref selects
GGML's vec-only reference schedule; it is NOT a fully scalar/no-RVV build.
Compare all 1536 finite outputs per native call with use_ref using the original
per-output tolerance abs <= 0.004 + 0.002*abs(reference), and with original
captured gold for prefix128. Compare old and grouped native outputs bitwise,
plus repeat bitwise equality. Preserve independent MUL rounding before fused
MAD. No projection or normalization change is introduced by the test.

32 native calls = 16 old/new pairs, with two repeats per shape. Old mode UNSETS
GGML_RISCV_AKV_GROUPED_PV, checking default-OFF rather than only explicit zero.
All calls start with RNE, preexisting DZ sticky flag, VCSR=5, vstart=0.
Check complete FCSR against reference and between old/new; preserve VCSR,
rounding and preexisting DZ. Flags are sampled before host comparisons.

20 fallback calls = both opt-in settings for mask hole, two threads,
normal-memory opt-out, RTZ, and use_ref, for both K types. Require full bitwise
output equality with opt-out ordinary GGML under the same conditions. Native
and every single-thread mode retain exact full FCSR/VCSR equality. Only the
two-thread fallback compares FRM, VCSR=5 and preserved preset DZ, not equality
of newly raised caller fflags across dynamically scheduled jobs. Both caller
FCSR/new-flags observations are recorded explicitly with aggregate=0; secondary
worker flags are not observed or claimed. CSR failure diagnostics precede
assertions. The isolated thread_flags diagnostic reproduced 9/11 caller FCSR
with all 1536 output words identical in 16 calls with quantKV always disabled.
Mask/RTZ require rejection traces with exactly zero commands/decodes/copies;
thread/memory/use_ref must produce no quantized-entry trace. A grouped=1 trace
alone is insufficient: native completed_groups=2 and all work counts must pass.
Totals: 320 command attempts, 4256 value decodes, 80 gathered panels and
221312 gathered bytes. These are software counts, not memory transactions.

Nonfinite-query/K/V rejection and arbitrary-callback side effects remain SDK
admission tests; this graph suite does not claim active NaN payload equivalence.
No whole-model or RTL performance claim follows from this functional suite.

## Pins And Launch

external_snapshot.json fixes the new adapter SHA and the complete rg-visible
ggml+cmake inventory hash, independently of old frozen snapshot manifests.
run.py rejects external drift; pins all those sources, current SDK/QBS sources,
own files, imported helpers, checked capture receipts/data, toolchain/compiler,
native QEMU receipt/model/build inputs, Linux, firmware and init. Recheck before
and after execution. Generated ELF, config, compile commands and initramfs are
pinned before QEMU and checked after it. Fresh distinct directories are required.

Only after parent review, from the signoff worktree:

```sh
python3 -B verification/akv/quantized_kv/grouped_pv/ggml/run.py \
  --preflight-only --build verification/out/grouped-pv-ggml-reviewed-build \
  --output verification/out/grouped-pv-ggml-preflight
```

Preflight writes PREFLIGHT_OK, never PASS, and does not configure/build/execute
the graph. Actual execution uses fresh build/output names and omits that option.
If backgrounded, a direct systemd worker must own run.py, not a short launcher.
Configure/build/init/cpio/QEMU limits are 180/1800/120/60/900 seconds, once each,
no retries. Complete logs are retained. Nonzero exits, input drift, missing or
extra records, partial output checks, changed CSR, wrong work/layout or missing
guest exit reject PASS. No trace is used as timing evidence.

Host-only checker tests (no cross build or guest):

```sh
python3 -B -m unittest discover \
  -s verification/akv/quantized_kv/grouped_pv/ggml -p 'test_*.py' -v
```
