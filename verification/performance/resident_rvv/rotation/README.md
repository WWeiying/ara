# PV register-rotation control

This is a diagnostic software experiment, not the resident-execution hardware
goal or a production SDK change. The accepted native-auto path is used in both
arms; only the candidate PV helper alternates V row destinations v8:v9 and
v10:v11. It keeps the two accumulators, token order, FP16 conversions and FMA
order. The two-row loop also handles the odd nine-token final tile. The SDK
admission guarantees positive token counts and D64/D96/D128; this first measured
case is the complete real Qwen3 D128/H2/T137 call, not all supported shapes.

Question: how much of the 45-cycle PV row recurrence can software remove by
avoiding overwrite of the immediately preceding row? This control is necessary
before justifying a new shared-arithmetic controller. It does not eliminate
VRF replay or accumulator read/write traffic.

The accepted SDK objects and real data are reused by verified hash. Only the
caller and one linker wrapper are compiled; the old PV function remains linked
and runs in the baseline arm. Both arms pay the wrapper-selection overhead.
Nothing is compiled from the dirty SDK assembly. Full-call timing, ABBA order,
output/CSR/guard/input checks are inherited from the sealed caller. Independent
vector tracing must prove the candidate actually alternated register groups;
all four calls must contain identical resident command and payload work.
The original native entry is explicitly retained at link time, so the accepted
ELF identity check remains intact even though both measured arms call auto.
The first build was rejected by that check because garbage collection removed
the unused entry. Its original files are preserved; a fresh build is required.

Build and run in separate fresh directories under the signoff worktree's
`verification/out`, using `experiment.py build` and `experiment.py run`.
The runner reuses the sealed VCS process owner and independent protocol check.
Run long simulations through a direct-owner user systemd service, then leave
them in the background. No new simulator build, RTL change, synthesis, bus
change or FPGA deployment is involved.

The numerical checker inherits field names `generic_mean_cycles` and
`candidate_mean_cycles`; in this experiment **generic means accepted native
auto**, not the old single-head implementation. Explicit arm labels are stored
in both build and result records. Do not compare the two field names across
experiments without reading those labels.
