# Candidate model integration gate

`run_model.py` consumes a `coexist/build.py --signed-max` build. That build
pins the private full production repack object to the accepted quantizer
numerical receipt and uses the same accepted GGML archives. No installed
runtime executable is replaced.

The existing model stimulus is copied privately and `model_context.patch`
enables cross-operation context reuse and its trace. All numerical checks
remain unchanged: two independent child processes select generic versus
candidate M4 preparation, two KV configurations produce three outputs each,
and every full-vocabulary output must match bitwise, including selected token
and CSR states. The native accounting checker verifies identical work,
non-emulated execution and balanced context fills/releases. The additional
gate requires actual cross-operation reuse, not merely an enabled variable.

This checks Qwen2.5-1.5B Q4_K_M with Q4_K/Q6_K projections. It does not prove
all models or quantization formats. AKV's ordinary flag remains disabled;
the quantized-KV runtime path retains the settings of the preceding accepted
model test. Neither this test nor graph coexistence provides RTL speedup.

The graph coexistence worker and model worker run independently with sealed
inputs. A PASS from the preceding accepted quantizer is not a PASS for this
candidate. Production promotion requires the new workers' results.
