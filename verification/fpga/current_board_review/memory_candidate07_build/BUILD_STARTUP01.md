# M7 Actual Build Startup

Main authorized one background freeze/build. Final live hashes verified:

- VLDU: 92f9ebbeb136cd3ff11ae1a8ea92ce31b3aac077ae0667f79d82e919a3603401
- VSTU: 37880822b8066fa13e66619dd335cb42db84cdc5730c6f4dff9a3f2fd0af46a0
- build.py: bbb0f67945a309f6b946cdd4e31d273652a6dd8c51cc223b5c468dd2fcba51c3

Read-only approved-pair preparation check returned0. Actual VSTU receipt uses
state=SUITE_ACCEPTED_NOT_SOC_ACCEPTANCE, pins_unchanged=true, matching VSTU
SHA and nine successful cases. An initial read-only lookup used nonexistent
`status` and exited before any service/output creation; corrected to its actual
`state` schema. There was one systemd launch, returncode0, no build retry.

Unit: ara-memory-candidate07-build01.service. Direct worker PID1908066;
active/running, Restart=no, KillMode=control-group. Same cgroup contained:

- integration/run.py build-image PID1908230
- make compile PID1908248
- VCS driver PID1908268
- actual compiler vcs1 PID1909099

Snapshot is SEALED, 539 files, same settings as M6, and exactly VLDU/VSTU
changes in live_source_sha256. Build uses the new candidate07 frozen tree,
NrLanes4/VLEN1024/2MiB, unchanged config and source-manifest checks, no FSDB.
The build script verifies the final453-file compile manifest before acceptance.

Output: /home/wangwy/fpga_runs/current_board_memory_candidate07
Service output: build01.log in this directory. Compilation log is under the
new campaign/image build tree. Startup is not BUILD_ACCEPTED or DUT acceptance.
Original M6 image/tasks were not changed. No DUT launched. No completion
polling was performed after this actual compiler observation.
