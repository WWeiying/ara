# Prefill and QuantKV Extensions

Preparation and independent numerical/work checking only. No simulator, hardware
build, QEMU timing, production changes, or historical evidence reuse as a result.
The parent owns execution on `operator_soc_20261115_activity_02`, image identity,
protocol checking and the four-worker limit.
Activity02 has the same RTL as all01 plus a passive unit probe.

```sh
env -u LD_LIBRARY_PATH python3 -B verification/performance/operator_eval_20261115/extensions/prepare.py \
  --case f16 --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/operator_extensions_prepare_20261115_f16_01
```

Use `--case q4_0` or `--case q8_0` and a fresh owned output name for quantKV.
Each directory contains `cases.json` in the central runner schema, an actual ELF,
`source-pins.json`, command logs, archived SDK, capture bytes and `build.json`.
The frozen checker accepts `--build`, `--run {run}`, `--log {log}` and
`--result {result}`; it writes `{state: PASS, metrics: ...}` only after checking
full raw outputs, architecture, guards/input integrity and native work. PASS
does not replace the parent's independent protocol/image gate.

The initial F16 case selects Qwen3 queries 16..19, KV head 0 and its two query
heads from the checked 136-query capture. All 256 original KV slots and original
causal masks remain; the actual Softmax prefixes are 17..20. Golden outputs are
the exact corresponding captured coordinates, not a recomputed truncated-K gold.
The denominator directly includes the archived operator's existing Q64/KV64 RVV
baseline, unchanged arithmetic and tiling. No handwritten replacement baseline
or silent fallback is used. Historical phase-only instrumentation is disabled;
each complete call includes preparation and final dependency/memory drain.
The native API uses canonical Panel4 selection and explicitly opts in to its
existing paired-F32 PV helper. This is an SDK operator slice, not a GGML dispatch,
normal-memory admission proof, board acceptance or whole-model timing.

F16 `--queries {4,16,64}`, `--first-query` and `--kv-head` select only existing
coordinates. No extension beyond the captured 136 queries or KV length 256 is
claimed. SmolLM2, T512, D256 and fallback/stride matrices remain future cases.

The quantKV cases reuse the checked real Qwen3 native ABBA driver and checker:
queries 16..19 / KV head 0, Q4_0 or Q8_0 keys and Q8_0 values. Both arms use QBS
QK plus the same existing RVV value decoder and GGML PV primitives; the contrast
is per-query GQA vs cross-query V sharing, NOT quantKV vs F16 or QBS vs RVV.
Expected value decodes are 74/20/20/74, four QBS commands and 1024 outputs/trial.
GGML quantizers/primitives are extracted from the recorded llama.cpp HEAD.
Only instrumentation and post-call input/VSTART checks are added to this driver.

Every arm has paired CSRRS cycle rd=x0 toggles just outside software cycle reads;
there is no print or additional stage fence in the ROI. Existing final drain is
retained. Raw `[PERF]` and `[LLM_METRIC]` records are retained with the log and in
checker metrics; no fabricated cycle values are emitted by preparation.
The LLM tag is `[LLM_PERF]`, not `[LLM_METRIC]`; the parent also collects the
separate `llm_perf_report_*` files. Run `seal.py --output <fresh-owned-dir>
--build <f16-build> --build <q4-build> --build <q8-build>` to combine ready cases
and add build/manifest receipts to their source identity gate before release.

The SDK is a `git archive` of dbe2b788, without overlays. Dirty
`akv_v2_attention_rvv.S` is never read as a compiler input. Host adapter tests:

```sh
PYTHONDONTWRITEBYTECODE=1 python3 -B -m unittest discover \
  -s verification/performance/operator_eval_20261115/extensions -p 'test_*.py' -v
```

Mock records in unit tests only test rejection behavior and are not measurements.
Once a parent pins this extension, stop editing it and use a successor for changes.
