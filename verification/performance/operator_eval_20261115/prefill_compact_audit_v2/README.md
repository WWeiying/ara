# Compact Prefill Successor

Only this directory and independent `operator_prefill_compact_prepare_20261115_*`
outputs are owned here. Existing extensions, three released builds, the parent's
Q64 build and their pins are read-only. No RTL/production edits or simulator runs.

```sh
env -u LD_LIBRARY_PATH python3 -B verification/performance/operator_eval_20261115/prefill_compact/prepare.py \
  --queries 16 --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_prefill_compact_prepare_20261115_q16_01
```

`--queries 64` prepares queries 72..135; 16 selects exact queries 72..87. Both
retain all 256 original KV slots, complete original causal masks and exact real
Qwen3 KV-head0/GQA2 golden coordinates. Softmax prefixes are respectively 73..136
or 73..88, never truncated to create a different operator. The SDK, prior optimized
Q64/KV64 baseline and native Panel4/paired-F32 PV arithmetic remain unchanged.
Compilation replays the parent's frozen ancestor recipe with independent inputs,
new output/check instrumentation and fresh objects. No old object is linked.

Each of four ABBA calls includes preparation and the established final drain.
No print, new phase fence, input hash or numerical check is inside the ROI. Each
call has two cycle-to-x0 markers. Outside ROI the target checks **every output**
for finiteness and the unchanged `.004f + .002f*abs(gold)` tolerance using RVV
comparisons and population counts. It prints the first 64 raw values plus full
checked counts, guard/input/CSR evidence and a full-output consistency hash.
Hashes consume every little-endian 64-bit word; hashes do not replace numerical
comparison. Repeated same-arm outputs are also compared byte-for-byte in full.

The host independently binds dimensions, operator configuration, scale/tolerance
constants, and every embedded input/golden byte to the ELF and original real
capture. It checks the 64 printed values, all-output audit counts, exact native
command/payload schedule and summary, and commit-trace ROI/readcycle/audit entries.
Unprinted outputs are checked by the audited ELF-bound target loop, not recovered
independently from the hash. Strict independent FFLAGS gold has not been derived:
only the existing FRM=0, VCSR=5, VSTART=0 and same-mode repeat contract is checked.
The parent's image/protocol/activity gates remain mandatory. This is not GGML
dispatch, normal-memory admission, board acceptance or whole-model performance.

`budget.json` is a conservative engineering estimate, **not measured Prefill
timing**. It pins the completed current-RTL Decode calibration's whole-run rate,
scales the two arm ROIs by actual query/key work, allows 2x for the different
schedule, 2M non-ROI cycles and a 25% rate reduction. If its upper envelope exceeds
10800 seconds, `manifest.json` has no cases and `held-case.json` explicitly forbids
dispatch. No timeout is extended and no automatic simulation is launched.
Q16 is below the production 64-query threshold and cannot claim threshold coverage.
Q64 may be compiled and held; it is not relabeled as measured or accepted.

The parent consumes **manifest.json**, whose pin map also seals build/manifest
receipts. Callback arguments are `--build ... --run {run} --log {log} --result
{result}`. Raw PERF/LLM_PERF logs and separate LLM report files remain parent-owned.

```sh
python3 -B -m unittest discover -s verification/performance/operator_eval_20261115/prefill_compact -p 'test_*.py' -v
```

Tests include real-capture coordinates, budget gating, full-output scalar numeric
checks including a bad last value, and numerical/work/ROI mutations. Artificial
unit-test records are mocks, never timing evidence. Freeze this successor when
released; further changes require another successor.
