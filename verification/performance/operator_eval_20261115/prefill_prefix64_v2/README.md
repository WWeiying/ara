# Real Prefix64 Prefill

Independent successor of the frozen compact Prefill helper. Existing extensions,
compact helpers, builds and inherited pins are read-only. New files and outputs
are confined to this directory and operator_prefill_prefix64_prepare_20261115_*.

```sh
env -u LD_LIBRARY_PATH python3 -B verification/performance/operator_eval_20261115/prefill_prefix64/prepare.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_prefill_prefix64_prepare_20261115_q0_63_01
```

Real Qwen3 queries0..63, original KV head0/query heads0..1, D128/GQA2,
KV capacity256. Every original causal mask row and every visible key1..64
is retained; golden values are exact original captured coordinates, not a
recomputed/truncated-K reference. Four ABBA full calls compare the unchanged
existing RVV Q64/KV64 baseline against SDK native Panel4/paired-F32 PV.

The causal prefix sum is2080. Each native call has2048 Panel4 commands,2080
paired-PV loads, one FULL and one RELEASE (4130 commands; no REFILL). QK and
PV each have532480 useful scalar FMAs. External payload is33344 bytes,
including the descriptor; local replay is1064960 bytes. The baseline computes
1048576 QK FMAs and1081344 PV FMAs including padded query rows.

The unchanged budget envelope predicts about5249 seconds for all four calls,
using the pinned completed current-RTL calibration, a2x schedule allowance,
2M non-ROI cycles, and a25% rate reduction. This is an engineering estimate,
not measured Prefill timing or a guarantee. Timeout remains10800 seconds.
No VCS, QEMU timing or hardware build is launched by this helper.

The target compares all16384 outputs per trial to captured gold outside ROI,
using the unchanged .004f+.002f*abs(gold) tolerance. It prints only the first64
values plus full counts, flags, guards, input/full-output hashes and repeat
checks. Hashes are consistency evidence, not replacements for numeric checking.
The scalar/RVV validation helper is byte-identical to its frozen predecessor.
Host checks bind the complete capture, golden data, dimensions, tolerances,
configuration and guards to the ELF, check raw printed values, full target
check counts, exact native work/summary, and commit-trace ROI/audit entries.

This is explicitly **batch64 SDK numerical/performance evaluation** via forced
SDK APIs. The query-count geometry satisfies64; GGML production admission,
runtime selection and production dispatch are **not verified**. Report fields
state forced_sdk_api=true, actual_ggml_dispatch=false,
production_dispatch_verified=false, runtime_admission=false. No independent
strict FFLAGS gold has been derived: retain FRM=0, VCSR=5, VSTART=0 and same-mode
repeat equality. Parent image/protocol/activity gates remain mandatory.

Consume **manifest.json**, with run-source-pins.json sealing build/manifest
receipts. The frozen callback accepts --build, --run {run}, --log {log},
--result {result}. All artifacts remain BUILT_NOT_EXECUTED until the parent
runs and independently checks them.

```sh
python3 -B -m unittest discover -s verification/performance/operator_eval_20261115/prefill_prefix64 -p 'test_*.py' -v
```

Host tests include exact real coordinates, complete masks, budget gating,
unchanged numerical helper identity, bad last-output detection, and
numerical/work/ROI mutations. Artificial test records are mocks, not timing
evidence. Freeze all helper files after release; later changes need a successor.
