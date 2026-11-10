# Cooperative Integer Result Queue Gate

PASS closed 2026-11-09 20:41:27 PST. Output root:
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/stage2_matrix_queue_vcs_20261109_01`.
376 source/input pins and both 40-file image inventories match; each depth
compiled once. No retries, SRAM/MAC/FP-array expansion, or SoC acceptance.

## Implementation

Only production `qbs_compute_engine.sv` changed; profile is unchanged.
`IntegerResultQueueDepth = CooperativeWaves ? 16 : 0`. The typed fifo_v3 entry
contains slot/index/first/dot/aux/weightD/Dmin/activationD, 140 bits, 280 bytes
of payload registers plus control. Only cooperative Q4_K M8 uses the FIFO;
other shapes/formats and depth=0 keep the direct path.

The destination index and all operands are captured before integer context
release. FIFO ordering and the FP accumulator's existing conflict protection
retain each output's K order. Final/fault drain includes FIFO busy; fault
does not discard entries. INIT/FAULT_CLEAR require empty hidden work. Seed
admission/assertions include FIFO empty. Seeded commands were not dynamically
exercised by this canonical bench, whose command_seed remains zero.

## Same-Output Measurements

Historical sources/images are archived matched references, not current-root
audits. Fresh queue=0 reproduces every historical cooperative real-case cycle.
Both real Qwen3 projections use the same 8x32 outputs, full K2048, ordered C-ref
golden/flags, and the unchanged canonical SV checker. No GGML output golden.

| Both attn_q and ffn_gate | Two-command cycles |
|---|---:|
| Historical best M4/N32 | 18216 |
| Historical original M8/N16 | 20406 |
| Fresh cooperative queue=0 | 16194 |
| Fresh cooperative queue=16 | 13604 |

Queue=16 reduces cycles by 25.32% versus best original M4 (1.339x), 15.99%
versus old cooperative, and 33.33% versus original M8. M4 remains unchanged.

Per M8 command: context-start blocked 2112 -> 816; context1-only blocked
1680 -> 384; scheduler 2153 -> 857. Compute phase stays 3248, drain 158 ->159,
FP blocked stays 1728, FP uops 6144. Thus 1296 scheduler cycles are recovered
at one extra terminal cycle, without changing arithmetic work.

FIFO: 1024 accepted/popped requests, max occupancy 16, 480 pushes while FP
blocked, 24 next-tile starts with old results queued, 86 final-drain cycles
with queue nonempty. Payload order/geometry/first/K counts were checked.

## Coverage And Handoff

12 host tests; both depths passed minimal M8/N4/Kb2, two real projections,
original 12-case context/fault/reset suite and 36-case format/fallback suite.
Context queue=16 observed 46 queued fault-drain cycles and one reset-discarded
entry. No early architectural commit or dropped fault-drain entry was accepted.
The minimal case is 823 ->824 cycles: no inter-tile gain is claimed there.

Compute SHA256: `ccce293865758a95a7ec402a540078cc409bced83ded8b56c7ff9e9688f6cbb5`.
Profile remains `6003482718f62e2b1831d89035941dc31495551903200883abc3b6a2903d7ac4`.
Queue worker has exited; production/helper active pins are released. The
separate special-scale gate must not overwrite or relabel this PASS. No further
optimization is planned; SoC/firmware integration belongs to the parent.
