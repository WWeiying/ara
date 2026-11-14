# Resident Direct-Gate Focused Tests

These tests check the current main-worktree gate candidate without modifying
production RTL. Test sources and results belong to `ara_dsa_signoff_integration`.
The campaign fixes RV64, no hypervisor, one issue port and two commit ports.
The directory date in the evidence names is UTC.

## Results

All three VCS runs completed successfully, without retries or production fixes.
Counts are checker evaluations, not independent instructions or coverage scores.

| Test | Result | Checked behavior |
|---|---|---|
| Original gate regression | 77,878 checks | 24,672 decoder cases, including 3,072 denied cases; CSR semantics, ID flush, and already-authorized request preservation |
| Real commit-boundary integration | 4 scenarios, 913 checks | CSR permission changes, delegated trap, SRET/MRET, younger queue/ID flush, and transaction-ID reuse |
| Real backend in an existing SoC image | 4 paths, 768 output elements | Row/column reads and Resident QK/PV, actual VRF writes, following vector-CSR drain and stores |

The commit test connects real ID, scoreboard, CSR buffer, commit stage, CSR
regfile, controller and accelerator dispatcher. Scalar completion and the
accelerator INFO response use testbench drivers; this is not full-core execution.
All five positive replays have exactly one request, queue pop and retirement.
Nine targeted flush boundaries and five same-cycle commit races passed.

The backend test reuses the sealed November 12 SoC image. Its 83 files under
`hardware/src` and `hardware/include` match current main exactly. Five CVA6 files
and `ara_tb.sv` differ; `inputs/identitydiff.json` records all differences.
Therefore this is current-backend evidence, not new-gate-plus-SoC acceptance.

## Nonvacuous Completion Evidence

Cycle numbers below come from accepted VRF writes, not write requests.

| Path | Command response | Following CSR first offer | Last VRF write | Backend done | CSR response | Store first offer |
|---|---:|---:|---:|---:|---:|---:|
| Row load | 18236 | 18237 | 18260 | 18261 | 18262 | 18263 |
| Column load | 18385 | 18386 | 18442 | 18443 | 18444 | 18445 |
| Resident QK | 20831 | 20832 | 20825 | 20831 | 20833 | 20834 |
| Resident PV | 22261 | 22262 | 22255 | 22261 | 22263 | 22264 |

Both early-response load paths exercise a real CSR waiting window. QK and PV
return only after terminal backend completion. Exact rational reference values
check all 768 output elements; 512 PV source elements remain unchanged. Five
memory buffers have 64-byte guards on both sides. All guards, stored outputs,
sticky `fcsr=1`, and `vstart=0` checks pass. The protocol checker reports 32
requests and responses, with zero exceptions, outstanding requests or errors.

## Evidence and Reproduction

`results_20261114.json` lists result paths and SHA256 values. `receipts/` contains
byte-identical result snapshots included in version control. Each run keeps its
source pins, frozen inputs, launch command, logs and cycle trace. No old result
was overwritten. Backend simulation plus checking took 36.8 seconds.

Prepare a fresh output before running either new test:

```bash
python3 -B verification/performance/resident_direct_gate/commit_boundary/run_commit_boundary.py prepare --output "$PWD/verification/out/resident_gate_commit_NEW"
python3 -B verification/performance/resident_direct_gate/backend_drain/run.py prepare --output "$PWD/verification/out/resident_gate_drain_NEW"
```

Review the generated `plan.json`, `source-pins.json` and `launch-command.json`
before launching. The frozen runner must be owned directly by its systemd
service. Helpers must not change while a consumer is running. The backend
checker rejects missing early-response/CSR waiting windows as insufficient
evidence, rather than silently treating them as passing tests.

## Version Scope

The commit and annotated tag `resident-direct-gate-focused-tests-20261114`
identify this test source and receipt package, not a new production RTL release.
The tested main worktree had HEAD `4a7361f51ba5447a616217dad1c8e72e3ee2b45b`
plus local dependency changes. The four gate file hashes in `campaign.json`
and each run's full source pins identify the actual candidate; HEAD alone does
not. Frozen RTL, simulator images and full traces remain in the local evidence
directories, outside this commit. The runners intentionally require those pinned
local inputs; the receipt package alone is not a standalone simulator build.

This campaign does not validate Linux scheduling, signal/page-fault handling,
multi-process isolation, a rebuilt FPGA bitstream, or end-to-end performance.
It does not establish zero Resident call overhead or change runtime defaults.
