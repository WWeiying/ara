# Indexed Early-Illegal Prefix Recovery

New e64m1 VL3 boundary, not original16 Linux replay. See `PLAN.md` for the
precise cause6/skip/prefix/index-repair/poison contract and scope limits.
Fixture, oracle, reference, checker and worker are now pinned; do not edit.

## Actual Preparation

- Unique `reference.py indexed` returned0: 3.227113718s,167827 retired,
 966 checks, cause6 then ecall9, exactly two target attempts, HTIF1.
- Host C/Python oracle:2320 rows match;20 whole-state negatives rejected.
- Complete fault/final checkpoints:32600/32592 bytes. Prefix memory,
 source snapshots/tails, repaired index, same-PC vstart2 retry, poison,
 different-source indexed successor and CSR restore all checked.
- SoC ELF SHA256:
 `bab01b98f12ee9b9930995b8c73965c5db833772e3aac2a328b9d7002db686fb`.
- `host_dut_check01.json`:11 focused tests PASS. Existing actual Spike raw
 additionally passed the same checker via an explicit Host-only scalar-row
 bridge:966 expected operands, actual saved/trap CSRs, full8KiB scalar
 prefix snapshot and14 restore readbacks;5 adapter negatives rejected.
- Initial bridge regex incorrectly matched a literal backslash-b. Its
 failure/source remain in `host_actual_reference_bridge01/`; correcting
 only that unsealed bridge and rereading the same raw passed. No second
 Spike, ELF/source change or DUT checker change. HTIF1/CTRL0 endpoint
 conversion is explicitly Host-only, not manufactured DUT evidence.

## Actual M7 Entry

Plan `vcs_m7_indexed01/plan.json` SHA256:
`e83158226b6d59668069109b8e2b63b0e70dd197653c8b1131d50d0177778d4b`.
Service `ara-indexed-prefix-m7-01.service`, direct worker, one job,
900s simulator/1200s outer service, no retry/build. Local output:
`vcs_m7_indexed01/service.log`, `launch.json`, `startup_observation.json`;
actual numeric child receipt goes to
`run/tests/indexed_prefix_vl3/child_exit.json` before artifact validation.
Only terminal `complete.json` with actual rc0/full checker/pins/noabort
can accept the DUT result. Reference PASS or service startup is not DUT PASS.

Use the accepted unchanged M7 fixed AXI input delay3/output0. No FSDB or
runtime W-delay overrides were added. This is a real queue/CSR/prefix/retry
recovery regression. Without internal timing capture it does not assert
the old good-descriptor/pendingB0 race window; local M6 counterexample
remains the root-cause evidence. Further W pressure requires a separate
explained TB, never arbitrary production delay/timeout changes.
