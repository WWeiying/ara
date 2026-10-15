# M8 Actual Build Startup

User authorized one independent background M8 build after static review.
Read-only preparation returned0 and exactly one changed source: AddrGen.

- Unit: ara-memory-candidate08-build01.service
- Direct worker:1970205; actual vcs1 compiler:1971263
- Observed active/running, Restart=no, KillMode=control-group, RuntimeMaxSec=1800
- Frozen539 files; NrLanes4/VLEN1024/2MiB; same settings as M7
- build.py SHA256: bd3cfbe1ae41e17fac6a71e6307570183f76e2d33bfed00285ca4500ba6bfc6c
- REVIEW.md SHA256: 03cfe43f281aa6b53b224a21069530cf30d9b42ccca40cdeb437b61c0a8942aa

Command (direct systemd worker):

```sh
/usr/bin/python3 -B /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/memory_candidate08_build/build.py --approved-addrgen-sha256 1cc40e2669e310ae25e23f5c9ee1f7ee493dc1ac990d70d8b8122f47e93742b2 --authorize-freeze-and-build
```

Service stdout/stderr: build01.log in this directory.
Output: /home/wangwy/fpga_runs/current_board_memory_candidate08.
One launch, no retry. No DUT started and no M6/M7 task modified.
Startup does not assert build completion. A bounded pidfd wait on1970205
is used for completion, not a process/simulation polling loop.
