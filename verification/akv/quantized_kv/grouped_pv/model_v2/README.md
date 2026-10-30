# Grouped-PV Model Successor: Whole-Call CSR Contract

Prepared, not yet accepted. Preserve `../model/` and its failed first run.
This successor retains the same model, inputs, QBS and Attention settings,
all-logit and token checks, projection-call reconciliation, and fresh contexts.
Only the unsupported requirement that an entire `llama_decode` preserve entry
VCSR is removed. Return VCSR must be valid and identical between paired paths.
Return FCSR comparison, RNE and preset sticky-DZ checks remain unchanged.
Local QBS/AKV helper preservation tests remain unchanged.

See `hardware/docs/grouped_pv_model_csr_review_20261026.md`. The production
Q8_K row quantizer writes VXRM=RNE; this is permitted by the RISC-V calling
convention. A minimal diagnostic must confirm the identified nonzero/zero
branch behavior before this model successor is launched. Do not change RTL or
production quantization to satisfy an invalid model-wide calling assumption.

Both paths still use existing QBS projection and quantized Attention. Only
`GGML_RISCV_AKV_GROUPED_PV` differs. Four fresh contexts (two K formats, OFF/ON),
three greedy predictions each, full vocabulary logits, 224 native Attention
calls and 896 commands are required. QEMU is functional evidence only.

Host tests:

```sh
python3 -B -m unittest discover \
  -s verification/akv/quantized_kv/grouped_pv/model_v2 -p 'test_*.py' -v
```

After diagnostic review, launch `run_model.py` with the same graph02 prerequisite
and new build/output paths. Keep this directory and all input sources frozen
while its worker runs. Do not relabel the original FAIL as PASS.
