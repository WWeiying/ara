# Graph-preserving probe: functional acceptance

## Result and scope

The isolated graph-probe ON/OFF test completed PASS in
`verification/out/graph-cycles-model-20261029-03`. An independent replay of
the original serial log reproduced the checker result and verified all 1006
sealed input hashes. The background service has exited; it is not still
simulating.

| Check | Observed result |
| --- | --- |
| Model | Qwen3-1.7B, Q4_K_M weights |
| Prompt / context | 40 prompt tokens; context 128; batch and microbatch 64 |
| KV formats | Separate Q8_0 and Q4_0 K runs, both with Q8_0 V |
| Execution | One worker; three inference steps per KV format, in each mode |
| Logits | 6 x 151936 = 911616 paired FP32 words, bit-exact |
| Tokens and CSR | All six paired selected tokens and FCSR/VCSR equal |
| Probe output | 6 distinct graphs; 3894 valid node-group records |
| Accounting | Ordered, nonoverlapping node groups; record counts and sums match |
| Termination | Explicit model-suite PASS and guest exit 0 |
| Provenance | Worker post-run hashes and independent 1006-input replay pass |

Both modes use native custom-instruction QEMU execution, not the software QBS
emulation option. Parallel M4 sums, Register-PV Decode, grouped Prefill and
prepared reuse are configured identically. Only the runtime probe selection
differs. All known per-call QBS/AKV trace-print switches are disabled in both
modes. The same probe-enabled binary launches independent children so cached
environment choices do not leak between modes.

The earlier compilation gate separately proved that compile-time OFF produces
the same preprocessed source and object bytes as the unmodified CPU-loop
source. The runtime comparison here is runtime OFF versus ON in the isolated
probe-enabled build. These are distinct checks.

## Counter environment

The original model attempt failed on a user `rdcycle` instruction. The first
short preflight then established that permission alone permits reads but leaves
the counter stopped. Neither original FAIL was overwritten.

The accepted isolated guest uses Linux's supported
`sysctl.kernel.perf_user_access=2` boot setting plus a pinned system-wide CPU-0
`PERF_COUNT_HW_CPU_CYCLES` event. The parent retains its fd throughout the child
tests. The one-hart launch and an advancing-counter check are required before
loading the model. This changes test-environment counter access, not RTL,
QEMU arithmetic or model algorithms.

Short admission evidence:
`verification/out/graph-cycles-counter-preflight-20261029-02`.
The default-policy child receives SIGILL; the configured child reads a strictly
increasing counter. Both outcomes are required by that checker.

## What this does not prove

These timestamps are QEMU counters and are **not hardware cycles**. No operator
percentage, hardware speedup, model tokens/s or new optimization benefit is
derived from them. The model receipt explicitly records
`performance_measured=false`, `hardware_command_counts_verified=false` and
`reuse_counts_verified=false`.

The probe brackets the original CPU execution loop without splitting graphs
through a callback. It retains fused nodes as a group. Output equality alone,
however, does not prove equal command counts, cache reuse or fusion decisions.
Those remain separate gates, as does paired RTL measurement of instrumentation
overhead. Graph elapsed time includes record bookkeeping but excludes graph
construction, probe-buffer allocation and post-interval printing/freeing. It
is not the complete `llama_decode` interval.

## Evidence identity

| File within the run directory | SHA256 |
| --- | --- |
| `result.json` | `aeda6621a56d37afd44d6139712cd5225c857b57cd20c4ac364d3dcc5677cf18` |
| `qemu.log` | `d8ac7f86b8a25ebbcc0431ec829b082cdfa3fe26be6380579538d49d7d757250` |
| `test` | `2200fc5b964f2c89c454f5e42db1f4c1d21b905d0ba51d12846e53044ff09574` |
| `source-pins.json` | `171d8edbc709aec942bd1b464918d77f498f99c1c0fe6bd83f59e81bc5ff4fbf` |

Implementation and checks are under `verification/qbs/graph_cycles/`.
This acceptance does not install a timer into the external production tree or
change any default optimization switch. It closes the real-model functional
gate for the isolated probe, not the overall software/hardware optimization
goal.
