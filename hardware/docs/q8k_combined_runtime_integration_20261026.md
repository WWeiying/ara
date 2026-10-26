# Combined RVV/Zvfh Q8_K preparation integration

## Change and benefit

The combined QBS/AKV llama.cpp build enables Zvfh. Its previous Q8_K M4
selector excluded Zvfh at preprocessing time, so the preparation opt-in did
nothing in that build. The tested change removes that exclusion from the
shared enable/trace helpers and the Q8_K selector only.

The external runtime file is:
`/home/wangwy/llama/llama.cpp/ggml/src/ggml-cpu/repack.cpp`.
The reproducible two-guard patch is
`verification/qbs/combined_zvfh_m4/enable_q8k.patch`.

| Current-RTL projection, two trials summed | Generic | Vector preparation |
| --- | ---: | ---: |
| Admission | 5195 | 4949 |
| Preparation | 534484 | 392004 |
| QBS execution | 713964 | 713881 |
| Total cycles | 1253643 | 1110834 |

For real M4/N1536/K1536 Q4_K projection data, the complete measured slice
improves by **1.12856x**, or **11.3915% fewer cycles**. Preparation itself uses
26.6575% fewer cycles. This is software feed improvement on unchanged RTL;
the QBS execution interval is effectively unchanged. Do not multiply this
number by a differently scoped historical speedup.

The slice includes current production preparation, SDK plan admission and
native execution. It is not a full GGML operator or whole-model measurement:
allocation, graph scheduling and offline weight repack are outside the timer.
All four ABBA trials, byte/bsums checks, independent output oracle, canaries,
input integrity, before/after weights, custom writeback trace and UVM checks
passed. The run completed in approximately 2 h 15 min, without a second VCS run.

## Correctness and preserved behavior

The private candidate passed combined-ISA native preparation tests, 384 GGML
graphs, and the actual Qwen2.5-1.5B Q4_K_M model. The model check compared two
KV configurations and six full-vocabulary outputs: 911616 pairs of logits
matched bitwise, with equal generated tokens and CSR states. All 386 enabled
M4 preparation calls selected the vector path. Native projection commands
were identical between modes, with no software-emulated commands.

- Q8_0's existing Zvfh selection is unchanged.
- The generic default remains available; exact environment value `1` opts in.
- Rejected rounding modes or numerical domains still use the generic path.
- Single-row Decode quantization is unchanged.
- Existing cross-operation residency is unchanged. It requires M1; this
  candidate changes only M4 preparation. The model gate disabled cross-op
  residency for isolation, so it does not measure the best default Decode
  configuration or establish a cross-op speedup.
- No RTL, instruction encoding, context capacity or weight layout changed.

## Use in a rebuilt runtime

The follow-up combined-ISA coexistence gate has now passed 88 synthetic GGML
graphs: 48 context-policy cases, 32 input-alias/mutation cases and eight expert
barrier cases. This enables the accepted M4 preparation together with cross-op
context and checks both eligible reuse and mandatory re-preparation. Sixteen
M4 calls actually used the RVV quantizer. Original dispatch/lifetime checkers
and source pins were independently replayed. This is functional coexistence
evidence, not additional model or RTL performance evidence, and does not cover
the newer signed-max candidate. See
`verification/qbs/results/q8k-coexist-complete-20261026.json`.

Rebuild the llama.cpp executable after updating the source. Setting an
environment variable cannot change an older binary's preprocessor selection.
Inside the target Linux environment, use:

```sh
GGML_RISCV_QBS_M4_PREPARE=1 ./llama-cli <existing model and execution arguments>
```

For an initial dispatch inspection, also set
`GGML_RISCV_QBS_TRACE_M4_PREPARE=1`. Disable tracing for performance collection.
Use `GGML_RISCV_QBS_M4_PREPARE=0` for the generic comparison. Set these variables
inside the guest when running system QEMU; host variables alone are not passed
through to guest programs.

## Evidence and version boundary

- Performance: `verification/qbs/results/q8k-current-projection-acceptance-20261026.json`.
- Model: `verification/qbs/results/q8k-combined-zvfh-model-20261026.json`.
- Original external source SHA256:
  `a075a21276c8b7e1b26eaefaf0821cf31e9b427b3f5dc1a3c07b32256d433e9c`.
- Integrated source equals the tested candidate byte for byte, SHA256:
  `4657efb9ed044846a8a4dd99748d774f3beb20a5177899f75e7705842928aa7a`.
- The original source is preserved as
  `verification/out/q8k-combined-zvfh-integration-20261026-01/repack.before.cpp`.
- The integrated translation unit compiles successfully with the same flags.
  Its 218024-byte `.text` section equals the tested candidate's, SHA256
  `ca3f9128a7dff6efaf59c80a29e3439ba24fc6c1c1c481f1a603a69c95d84460`.
  The complete objects differ; this is not a claim of whole-object or installed
  executable identity. No existing user executable was overwritten.

Source-identity audits were completed before integration. Historical workers'
manifests intentionally retain the old external source identity; do not rewrite
them to make the new checkout appear identical. Their artifacts, candidate
source and promotion receipts preserve the tested version boundary. The
external runtime has unrelated existing edits, which this integration does
not revert or silently include in an external Git commit.
