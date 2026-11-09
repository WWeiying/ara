# Four-lane production VMFPU numerical integration

Accepted run: `ara_dsa_signoff_integration/verification/out/resident_pv_cluster_fp_20261108_02`.
Host VCS, SharedFma=0. No synthesis, SoC program or FPGA run.

| Check | Accepted result |
| --- | ---: |
| Four-lane groups | 68 |
| Per-lane case records | 272 |
| Included real Qwen3 tiles | 3 (T=64,64,9; D128/H2) |
| SIMD FMA accepts and returns | 19128 each |
| Result words and final acknowledgments | 1912 each |
| Native completions compared to original VMFPU | 340 per lane |
| Ownership acquire/release pairs | 68 per lane |
| Native/private cancellations or resets | 0 |

All four instances use the actual production VMFPU borrowing interface. The
extra original VMFPU instances are test-only native references, not additional
hardware. Every private FMA input, mask, tag, rounding mode, returned active
element and flag is checked against the unchanged, previously accepted
independent-SoftFloat expectation body. Seeds, stream delivery, accumulated
output, slot/byte enables and final-write accounting are also checked.

The 65 non-model groups exercise common per-lane shapes 16/24/32 (corresponding
to D64/96/128 for four lanes), partial-word tails 1/3/31, one/two heads, all five
legal rounding modes, and signaling NaNs. They are synthetic arithmetic tests,
not additional captured model workloads. Prepared scaling/conversion flags are
excluded from this FMA-only gate, not silently charged twice.

The test deliberately inserts lane-specific stalls and delayed write completion.
Native FMA, multiply, divide and exceptional maximum probes plus a deferred
multiply are checked cycle-for-cycle against the original VMFPU around each
ownership interval. These limited probes are not a full ordinary-RVV regression.
No speedup is inferred from this testbench's scheduled stalls or native probes.

Independent review checked the raw numerical records, four ownership receipts,
11 artifact hashes, 508 source pins, 45 image pins and before/after inventories.
The parent separately rechecked source and artifact hashes. Eight host tests
cover corpus grouping, snapshot/inventory checks and checker failure detection.

The earlier run `resident_pv_cluster_fp_agent_20261108_01` passed numerical
checks, but its receipt included the still-open service stdout file. That file
changed after receipt generation. The original evidence was preserved; run02
excludes open service output and reruns the unchanged numerical test. Do not
represent run01 as a wholly immutable artifact bundle.

Remaining gates: SharedFma=1 four-lane replay, actual context read/VRF import,
native issue drain, instruction/CSR/exception integration, full-call performance
against the rotation-and-loop control, QK and conditional runtime integration.
The production SoC still ties the resident interface off.
