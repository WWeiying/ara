# Candidate06 Build Preparation

Status: PREPARED / HOLD FOR EXPLICIT BUILD AUTHORIZATION. No EDA or DUT launched.

Root: `/home/wangwy/fpga_runs/current_board_memory_candidate06`.
Baseline: `/home/wangwy/fpga_runs/current_board_memory_candidate05`.
Only source delta is `hardware/src/ara_dispatcher.sv`: one dedup condition
replacement and two comments, exactly as `../REPAIR06_ROOT_CAUSE.md` describes.
Approved source SHA256:
`c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d`.
All other 536 original inputs remain byte-identical to M5, including previous fixes.

## Input Identities

- M5 snapshot: `0fb492aebe246deeeacf312b387d0813837afe4b023e53e5fe5d584bca5c0dbf`.
- M5 image ledger: `9349bdae91e72706ffbb22ad20a7f62795215a5263b1ec0cc4e4837fc21d1500`.
- M5 compiled manifest: `f050c1e6420537d7e562bb82056a439f10d17bede8dfe89100b2f71f638368c0`.
- Integration run.py: `c1c3804dbe36fa981ea7b6cbcfa5d7b69fb793b2a14c37831fb96e866f2d2a78`.
- Integration prepare.py: `c8852599c65e0a0812a7dc77dc365eb40398252867a29b226f34d758e5c56cf8`.

The snapshot transitively pins all 539 frozen files (537 original inputs plus
relocated filelist and Bender adapter). The compiled manifest has 453 entries,
including its generated filelist; this is not 453 independent RTL modules.
Script checks the complete source membership and contents before EDA, and the
453-entry compiled manifest after EDA, allowing only approved dispatcher SHA
and exact candidate05-to-candidate06 path relocation. No hardlinks or M5 writes.
Any failure leaves a nonaccepted candidate06 directory for diagnosis; no automatic
cleanup, retry, or reuse. Require BUILD_ACCEPTED.json, not merely image.json.

Configuration is inherited without changes: NrLanes=4, VLEN=1024, L2=2097152,
QBS/AKV/AKV2=1, OSSupport=1, PMP=0, assertion failures enabled, ideal_dispatcher=0,
coverage/UVM extra sources disabled. OSSupport and PMP are inherited from pinned
ara_soc.sv (OSSupport default 1 and cfg.NrPMPEntries override 0), not inferred
from simulator.conf, which does not contain those two fields.

## Commands

Read-only check (already passed; no Bender/EDA/output writes):

```sh
cd /home/wangwy/openproject/ara_dsa_signoff_integration
python3 -B verification/fpga/current_board_review/indexed_overlap_original/repair06_build/build.py \
  --approved-dispatcher-sha256 c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d
```

Only AFTER explicit parent authorization, launch one directly owned build worker
from the normal user shell with a working user bus (do not launch from an
environment-cleared helper). This command has NOT been executed:

```sh
XDG_RUNTIME_DIR=/run/user/$(id -u) \
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus \
systemd-run --user --unit=ara-memory-candidate06-build01 \
  --property=RuntimeMaxSec=1800 --property=KillMode=control-group \
  --property=Restart=no --property=WorkingDirectory=/home/wangwy/openproject/ara_dsa_signoff_integration \
  /usr/bin/python3 -B \
  /home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/indexed_overlap_original/repair06_build/build.py \
  --approved-dispatcher-sha256 c179ddd08b2bdb8648246f187aa892be5853fda38aeca850402d5e5b9b17ef7d \
  --authorize-freeze-and-build
```

Wrapper invokes the pinned integration helper in order:

```sh
python3 -B verification/fpga/current_board_review/integration/run.py snapshot \
  --out /home/wangwy/fpga_runs/current_board_memory_candidate06/frozen --authorize-freeze
python3 -B verification/fpga/current_board_review/integration/run.py build-image \
  --snapshot /home/wangwy/fpga_runs/current_board_memory_candidate06/frozen \
  --out /home/wangwy/fpga_runs/current_board_memory_candidate06/campaign/image --authorize-build
```

Do not bypass the wrapper checks using those inner commands directly.
The helper uses M5's frozen RegressionRunner and same make compile command/settings,
VCS V-2023.12-SP1, Verdi V-2023.12-SP1 and /usr/bin/g++, sanitized tool environment.
Bender's `script verilator` generates only a filelist; no Verilator build is invoked.
Installed proprietary tools/system compiler are external dependencies, not part of
the 539-source freeze; this is same-machine M5 build reuse, not hermetic toolchain provenance.

## Cost And Acceptance

M5 image.json measured build elapsed 116.18566799163818 seconds; run.json records
2026-10-11 10:06:41.137921 to 10:08:36.752685 -07:00 and BUILT, with no tests.
Expect minutes at comparable load; 1800s is a proposed conservative service cap,
not a measured M6 runtime or a promise. The one build worker can spawn compiler
children; runner jobs=1 does not establish a one-core memory/CPU cap. Coordinate
host resources before authorization. No DUT costs or functional PASS are claimed.

Before DUT admission parent must review BUILD_ACCEPTED.json, new image/snapshot
identities, build log, and actual terminal service result. Source/compile checks do
not replace functional indexed-overlap regression or establish the fix is correct.
