# Resident PV Smoke Runner

Only `run_smoke.py`, `test_run_smoke.py`, and this document are new runner inputs.
The reviewed experiment, software receipt/pins, original SDK, wrapper, numerical
golden, resident checker, SoC builder, production snapshots, and old protocol
checkers stay unchanged. There is no ABBA option or automatic successor run.

## Review And Prepare

Run host tests first. Prepare only after the explicitly selected SoC build has a
successful terminal receipt. An unfinished or failed build is rejected and any
attempt directory is retained, never overwritten. The example names build03;
the runner does not hardcode any build number as successful.

```sh
python3 -B verification/performance/resident_rvv/soc_eval/test_run_smoke.py -v
python3 -B verification/performance/resident_rvv/soc_eval/run_smoke.py prepare --soc-build /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_soc_build_20261109_03 --build /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_soc_eval_smoke_20261109_01 --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_soc_smoke_vcs_20261109_01
```

Prepare runs frozen host tests and the existing readelf/image-contract shell
check, not simv. It copies exactly the three new runner files, pins their original
and copied bytes, and binds the sealed software/hardware inputs and artifacts,
golden, helpers, tools, and complete `ara_verify/*.py` inventory. Include/image
closure and new resident-PV receipt checks come from the separate sealed
`experiment.checked_soc`, never the old accepted-SoC gate. Added checker modules
and source/document drift fail closed. No SDK/dependency tree is regenerated.

## Launch After Review

Parent reviews `selection.json`, `prepared.json`, preflight logs, and the SHA256
of `source-pins.json`. The following action only prints a launch command:

```sh
python3 -B verification/performance/resident_rvv/soc_eval/run_smoke.py service-command --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_soc_smoke_vcs_20261109_01 --review-sha256 REVIEWED_SOURCE_PINS_SHA256
```

Execute that command only after explicit parent approval. Systemd directly owns
the frozen Python worker as `MainPID`, with its expected CGroup checked before
execution, `KillMode=control-group`, and dedicated stdout/stderr files. A short
launcher with a detached background child is rejected. Limits are 3600 seconds
simulation, 600 seconds protocol check, and 4500 seconds service lifetime. The
existing `execute` helper handles child-process timeout/termination and records
each argv. Runtime image preflight is bounded at 180 seconds.

Required probes are `+AKV_PERF +AKV_SUMMARY +RESIDENT_PV_PERF
+RESIDENT_PV_WATCHDOG`; the watchdog is the sealed 32768-cycle lease guard. Commit
and vector traces and both passive monitor event traces remain enabled. There is
no FSDB, synthesis, recompilation, or coverage replay. `preflight --output ...`
revalidates a prepared bundle without executing simv.

## Acceptance

A PASS requires one complete D128/H2/T137 candidate call, not just importer or
FP completion. The host independently reads the receipt-pinned 1024-byte native
golden as 256 little-endian F32 raw words and compares every output bitwise.
Target `expected=` values are syntax only, not the oracle. Strict ordered SMOKE
records require one meta/memory/terminal, outputs 0 through 255 exactly once,
FCSR exactly 3, initial CSR zero, VCSR/VSTART zero, memory/guard/query hashes,
successful status/groups, and ordered issue/return/final-drain timestamps.

Work acceptance requires 100 successful, fault-free legacy AKV PERF commands and
one matching closed summary; each tile's vector signature is exactly 32 copies
of `0x0205745b` followed by `0x0485705b` (99 allocations total). The unchanged
parent resident checker independently requires three PV commands (64/64/9),
actual LDU write geometry, source/result/final-ack counts, and four-lane FP work
and flags union. Its numerical/protocol scope flags remain false; separate host
checks supply those obligations. Legacy `uvm_coverage` f7=2 column classification
is explicitly not PV semantic acceptance.

The existing `ara_verify.uvm_dut` must pass with events, backend, AXI reads, and AXI
writes required. Its log/vector/ELF/simulator/library identities must match this
run. All frozen source pins, checker inventory, and full hardware image inventory
are checked again before PASS. `result.json` retains failure or timeout evidence;
no retry reuses the directory. Service stdout/stderr and mutable status are never
stable artifact pins. Smoke acceptance is not a speedup, deployment, or ABBA
authorization.
