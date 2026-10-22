# M8 Build Handoff

BUILD ACCEPTED, NOT DUT PASS. One authorized build, no retry or DUT execution.
Static review: REVIEW.md (SHA256
03cfe43f281aa6b53b224a21069530cf30d9b42ccca40cdeb437b61c0a8942aa).

Output: /home/wangwy/fpga_runs/current_board_memory_candidate08
Image: /home/wangwy/fpga_runs/current_board_memory_candidate08/campaign/image

- BUILD_ACCEPTED.json: e93dc5e4582ae5ba8427680ed897f54ba3aac4c3f1a7daf5f52b900fc0cfac9c
- image.json: bd27bf6f7bb90b2b05c4546faaed8a8e32b8e545c182167fef72c170e40bdfd0
- snapshot.json: 8e0ada736b61d0b3ce5dc482e3d85078048d4f81fa0633cba8c340573e02a3be
- compiled manifest: 43a113535b7501c0c64d0e8ac7be142f19efe3f2ffde1635cb050060df6e8531
- simv: c4567ba1eb5e41ed713cfa100d6c51eb2031c4b531bd65d99aa4ceb601fe1550

Post-build independent read-only hash checks passed for539 frozen files,
453 compiled records and66 image payloads. Live-source difference from M7 is
exactly hardware/src/vlsu/addrgen.sv, reviewed SHA
1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2.
The build gate checked exact compiled-record equality after approved source
replacement and output-root relocation. Settings and simulator.conf match M7;
NrLanes4/VLEN1024/2MiB/OSSupport1/PMP0 retained.

run.json status BUILT, tests=[], completion2026-10-12T23:39:55.374311-07:00.
No Error-/Fatal-/Error:/FATAL: lines found in vcs-build.log or comp.vcs.log.
pidfd wait on worker1970205 observed process exit after90.014s of waiting.
Subsequent systemctl showed inactive/dead MainPID0 Result=success but
ExecMainCode=0; do not reinterpret collected/default properties as a retained
numeric child wait status. Build acceptance is supported by the checked
durable build artifacts and build script's checked subprocess completion.

Existing M6/M7 outputs/services unchanged. Previously authorized e64-O2 run
belongs to M7 only; it was not relaunched or attributed to M8.
