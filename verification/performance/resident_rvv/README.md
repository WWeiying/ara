# AKV resident-to-RVV investigation

## Scope

The active goal fixes bus widths, DDR interface, clock, lane count and arithmetic
unit count. No synthesis or FPGA update is part of this campaign. The reference
is the accepted native-auto software, not the older single-head implementation.
Existing dirty SDK assembly and testbench files are excluded from builds.

Milestones:

1. Attribute the accepted Qwen3 D128/H2/T137 complete-call trace, including its
   64+64+9 token tiles. Separate retirement spans from actual execution activity.
2. Replay the same ELF on the same frozen RTL with passive, bounded cycle probes.
   Require identical ABBA cycles, output bits, CSR, instruction work and protocol
   checks. This is measurement validation, not an optimization speedup.
3. Only after attribution, select the smallest useful change. A resident-PV
   controller using existing RVV arithmetic is a candidate, not a predetermined
   outcome. Preserve token order and F16 accumulation; QK retains dimension order
   and widened F32 accumulation. Do not remove architectural dependency checks.
4. Validate the selected change against the complete call, representative shapes,
   tail tiles, ordinary RVV and QBS. Integrate a shared GGML helper only after
   reproducible benefit, with capability/type/shape fallback.

## Frozen references

- Main source checkpoint: `af05b65362f78f8ad45e9a44423e8b41a40dd064`.
- Accepted SDK: `b7c9e6c3c1f8c5e469c130f46ec5bbfaf37a55d1`.
- Accepted ELF SHA256:
  `eea222d18cdff8b7e7353b66beebad87bd6385b1b66a6c303aec6e8bf2179ef0`.
- Accepted image SHA256:
  `3ed8bc6b761d49664162b9f3b45e525e5c051923618950cbdb2b38ea403486a6`.
- Evidence root (sole verification worktree):
  `../ara_dsa_signoff_integration/verification/out/`.
- Accepted evaluation: `akv_pair_integration_vcs_20261107_01/`.
- Accepted software: `akv_pair_integration_build_20261107_01/`.
- Accepted hardware: `chain_soc_admitted_20261107_01/`, built from the frozen
  source in `chain_soc_20261107_01/`.

Never modify these sealed helpers or inputs. New outputs have new names. The
long-running worker is owned directly by a transient user systemd service.

## Measurement meanings

`analyze.py` uses retirement-PC spans and allocation/completion records. A span
starts at the helper's first retired instruction and ends at the first retired
instruction outside it. This is not a count of FPU busy cycles. It can include
frontend, memory and dependency waits and exclude work draining after return.

The passive lane probe records FPU input/output handshakes, instruction/operand
availability, latency gating and result backpressure. An input handshake is an
accepted SIMD micro-operation, not a count of useful FLOPs or occupied pipeline
stages. The AKV probe distinguishes request acceptance from final VRF write
grant. In particular, the existing replay-backpressure counter includes waiting
for final grants; it must not be called a pure VRF bank-conflict counter.

These overlapping observations are not an additive stall breakdown. Do not
interpret time outside QK/PV helpers as removable control overhead: it also
contains real data preparation, context fill, softmax and output conversion.

## First offline result

The archived trace passed its artifact-hash checks. All twelve `rdcycle` values
map to the monitor cycle with a constant +1 offset. Auto trial 1 takes 36,203
cycles, including QK retirement spans of 9,901 cycles and PV spans of 6,574.
Auto trial 2 takes 36,579 cycles, with spans of 9,888 and 6,581 respectively.
There are three calls of each helper per auto trial; the last is the nine-token
tail. The combined spans are about 45% of the full call, not its entire cost.

Receipt: `verification/out/resident_rvv_attribution_20261108_01.json` in the
verification worktree. No new simulation was needed for this observation.

## Background execution

Run from the main worktree, using a new output name for each attempt:

```sh
systemd-run --user --unit=ara-resident-profile-20261108-01 \
  --property=WorkingDirectory=/home/wangwy/openproject/ara_dsa \
  --property=StandardOutput=journal --property=StandardError=journal \
  --setenv=PYTHONDONTWRITEBYTECODE=1 \
  /usr/bin/python3 -B verification/performance/resident_rvv/run_profile.py \
  --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_rvv_profile_20261108_01
```

The Python owner stays alive through compilation, simulation and independent
checks. `status.json` distinguishes preflight, build and actual simulation.
`PASSIVE_REPLAY_PASS` requires the accepted four timings and work counters to
match exactly, and all four lanes plus AKV to have complete bounded samples.
It is not acceptance of an optimization. Final interpretation of the probes is
a subsequent step. Failed evidence is preserved without modifying the checker
or the original acceptance records.

```sh
cat /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_rvv_profile_20261108_01/status.json
journalctl --user -u ara-resident-profile-20261108-01 -n 20 --no-pager
```
