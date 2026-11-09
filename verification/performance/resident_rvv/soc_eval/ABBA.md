# Resident PV ABBA Successor

Only `run_abba.py`, `test_run_abba.py`, and this document are new inputs. The
smoke runner, all existing helpers/checkers, SDK, assembly, RTL, and build pins
remain sealed. This successor does not compile or change simulator options.
No prepare or launch is authorized by writing or host-testing these files.

## Admission

An explicit `--smoke-run` is mandatory. The smoke must have completed PASS with
numerical, independent-protocol, post-source-pin, and post-image checks on the
same `resident_pv_soc_build_20261109_03`. Admission verifies its frozen bundle,
complete stable artifact inventory, executed simulation/protocol argv, source
pins, ELF/image/library identities, log/vector/protocol hashes, and result hash.
It reconstructs the smoke numerical/work reports and independently rechecks the
passive CPU/backend/AXI protocol from the original evidence. A PASS string or
copied/forged report is insufficient; RUNNING, missing terminal evidence, drift,
or another image fails closed. Mutable service logs/status are excluded.

The software must be the sealed `resident_pv_soc_eval_abba_20261109_01` build,
ELF SHA256 `4057d833a46f8b5f402303de68df2a3f67311b990dd3cf466128bbeec7c1baa5`.
All original/copied runner inputs, inherited smoke evidence, software and hardware
sources/artifacts, helpers/tools, and the exact ara_verify Python inventory are
pinned. Source/document/image and admission evidence are checked again after run.

## Parent Operation

First review the three files and host tests. Only after independent smoke
acceptance, explicitly prepare a fresh output:

```sh
python3 -B verification/performance/resident_rvv/soc_eval/test_run_abba.py -v
python3 -B verification/performance/resident_rvv/soc_eval/run_abba.py prepare --soc-build /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_soc_build_20261109_03 --build /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_soc_eval_abba_20261109_01 --smoke-run /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_soc_smoke_vcs_20261109_01 --output /home/wangwy/openproject/ara_dsa_signoff_integration/verification/out/resident_pv_soc_abba_vcs_20261109_01
```

Prepare runs frozen host tests and the unchanged image-contract shell check,
never simv. Parent reviews the prepared selection and source-pins SHA256.
`service-command --output ... --review-sha256 ...` prints, but never executes,
the separate systemd launch command. `preflight --output ...` revalidates without
simulating. The frozen Python worker must be the actual systemd MainPID in its
expected CGroup. Limits remain 3600 seconds simulation, 600 protocol, 4500 service;
the same probes/watchdog and CPU/backend/AXI requirements apply. There is no
automatic transition from smoke, retry, further experiment, or deployment.

## Checks And Reporting

The original `check_log` checks complete AKV_PAIR numerical/CSR/guard/data
records unchanged. Additional host checks compare all 1024 output words bitwise
to the receipt-pinned native golden and across all four arms, with FCSR exactly
3. Original captured-golden tolerance checks remain required too.

Order is strong rotation, resident PV, resident PV, strong rotation. Legacy
commands per call are 237/100/100/237: baselines retain all 137 V-row loads;
candidates use three PV commands instead. Exactly 674 fault-free legacy PERF
records and a closed summary, 664 ordered vector signatures, 136 rotated-v10
baseline allocations, and six PV commands are required. The unchanged resident
checker verifies `(64,64,9)` twice, actual writes, source drain/final acks, lane FP
work, and flags. Old column coverage classification is not PV semantic acceptance.

The reporter separates issue-to-return, return-to-final-drain, and complete-call
cycles per trial. The only complete-call speedup ratio uses the mean of trials
0/3 (strong rotation) divided by the mean of 1/2 (resident PV), including actual
preparation and final drain. Local PV probe cycles are reported as work evidence,
never substituted for complete-call speedup. Correctness PASS does not require a
speedup and does not claim whole-model, deployment, or performance acceptance.
Failed/timeout output is retained and cannot be reused. No EDA is run by host tests.
