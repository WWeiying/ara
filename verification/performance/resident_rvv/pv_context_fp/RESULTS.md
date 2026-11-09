# Context-to-shared-FPU acceptance and local throughput

Run: `ara_dsa_signoff_integration/verification/out/resident_pv_context_fp_agent_20261108_01`.
Host VCS, SharedFma=0. The service exited successfully; all recorded source,
image and completed-artifact hashes matched when independently rechecked.

## Functional result

| Item | Checked result |
| --- | ---: |
| Executions | 66 PASS |
| SIMD FMA accepts/returns | 36976 each |
| Final result words/acknowledgments | 2544 each |
| Actual context row reads/latency checks | 5432 each |
| Coefficient pair broadcasts | 814 |
| K/V context fill writes, 128-bit | 21728 |
| Native completions compared against original VMFPU | 330 per lane |
| Ownership acquire/release pairs | 66 per lane |
| Host checker tests | 10 PASS |

The arithmetic is performed by four production VMFPU instances, not additional
private FP units. Every accepted arithmetic operation and active result is
compared to the original independent-SoftFloat records. The additional original
VMFPUs in the testbench are native-path reference instances only.

The selected corpus has three real Qwen3 D128/H2 tiles and 60 synthetic executions
covering D64/D96/D128, one/two heads and all five legal rounding modes. Synthetic
matrix0/matrix1 inputs are tested as separate broadcast-compatible groups; their
original numerical bodies are unchanged. The final three executions repeat the
real tiles without externally injected stalls. Unsupported partial per-lane
shapes and the original special NaN groups are explicitly excluded here, not
padded or counted as passing this gate. Earlier component numerical gates cover
those cases separately.

The real context receives all data through its normal write interface. Distinct
K sentinels, explicit inverse EW16 mapping, actual row addresses, exact stream
order and raw bits are checked. Reader done, floating-point return, result
acceptance and final acknowledgment remain distinct events.

## Local no-injected-stall measurements

Cycle spans are inclusive. Operations below are accepted SIMD FMAs **per lane**,
not scalar FLOPs, instruction retirements or whole-FPU busy-cycle percentages.
All four lanes execute the same count with their own numerical data.

| Real tile | Tokens | FMAs/lane | First FMA to last FP return | First coefficient to last FP return | Cluster launch through done |
| --- | ---: | ---: | ---: | ---: | ---: |
| 0 | 64 | 1024 | 1090 | 1133 | 1154 |
| 1 | 64 | 1024 | 1090 | 1133 | 1154 |
| 2 | 9 | 144 | 155 | 198 | 219 |
| Total | 137 | 2192 | 2335 | 2464 | 2527 |

Within the first-FMA-to-last-return intervals, accepted issue throughput is
`2192/2335 = 0.9388` SIMD FMAs per lane per cycle. This is a deliberately narrow
interval, not utilization over the complete application or architectural command.

The raw timestamps show `16*T + (T-1)` cycles from first through last FMA issue,
followed by three cycles to the last accepted return. The `T-1` gaps correspond
to consuming the next coefficient between tokens. Thus these tested D128/H2
transactions sustain the available one-SIMD-FMA-per-cycle arithmetic port apart
from the required coefficient transitions and return tail. This observation is
not a fixed-latency correctness assumption: all control still uses handshakes
and pending-slot tags.

All lanes report zero FMA-valid/not-ready cycles while owned in these three
replays. Each also reports 25 pre-ownership stall cycles from the retained native
test probes. The 43-cycle coefficient-to-first-FMA prefix overlaps seed delivery
and ownership acquisition; it cannot all be called computation overhead or all
be removed as test overhead. Context stream backpressure remains (420,420,90
cycles), but does not create owned-FPU input stalls here. Larger buffering or a
wider context interface is not justified by this result.

## Integration decision

Continue the bounded PV integration: the real SRAM and existing FPU can execute
the selected recurrence without the old per-row VRF round trip and without
adding multipliers. The next gate is the **actual source import and architectural
ownership/retirement path**, including source-queue drain before commit.

Do not divide the old 4411-cycle PV helper span by these local spans and label it
a measured speedup. The stronger RVV control is a complete call of 34213.5 mean
cycles, whereas this gate has testbench seeds/coefficients, separate context fill,
test-native probes, synthetic final acknowledgments and no CPU custom instruction.
Preparation, conversion/interleaving, source maintenance/import, ownership,
architectural writes and CPU completion still require complete-call VCS timing.
No new runtime capability, SoC acceptance, QK result or end-to-end gain is claimed.

## Independent audit

A second reader reconstructed the original-body mapping and verified 711 source
pins, 45 image pins, 12 completed artifacts, both admissions, before/after
inventories and raw-log/report equality. These are 63 supported regrouped
executions plus three replays, not 66 distinct original workloads. All executed
private masks are `0xf`; observed private flags are limited to zero, NX and
UF|NX. The native signaling-NaN probes do not substitute for private exceptional
input coverage.

The exact issue cadence above is an observation of this pinned run. The runner
checks diagnostic ordering and span arithmetic, not a fixed cadence regression
threshold. Changing a diagnostic timestamp alone can pass that limited parser;
such a change would fail the recorded artifact hash. Future performance gates
must compare independently collected complete-call cycles, not rely on this
numerical PASS as proof of an unchanged latency.
