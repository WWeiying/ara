# M7 Build Accepted, Ready For SoC Tests

Build finished without restart. Actual run.json status BUILT, tests=[], completed
2026-10-12T22:26:12.324609-07:00; image build elapsed110.971226931s.
BUILD_ACCEPTED.json status BUILD_ONLY_NOT_DUT_PASS. No DUT result is claimed.

Current service observation: MainPID0, inactive/dead, empty ControlGroup,
Result=success, ExecMainCode0/ExecMainStatus0. Do not interpret reset/collected
service properties as a retained historical wait receipt. Historical direct
worker1908066 and vcs1 compiler1909099 were observed at startup; neither is
reported as currently compiling. Durable build acceptance and BUILT metadata
are present. No build was restarted and no original M6 task was modified.

Post-build verification passed:

- All539 frozen file hashes/read-only state, same membership/settings as M6.
- Exactly approved vldu.sv/vstu.sv differences; other sources unchanged.
- Frozen filelist/Bender changes are exact path relocation only.
- All453 compile records match M6 after approved changes/path relocation;
  every compiled record's actual content hash verified.
- simulator.conf is byte-identical to M6; NrLanes4, VLEN1024, 2MiB and
  existing OSSupport1/PMP0 configuration retained.
- All66 image payload hashes verified, including simv and shared libraries.
- comp.vcs.log has no Error-/Fatal-/Error:/FATAL: lines and records successful
  link and KDB completion. Existing warnings are not silently claimed absent.

Image directory: /home/wangwy/fpga_runs/current_board_memory_candidate07/campaign/image

| Artifact | SHA256 |
| --- | --- |
| BUILD_ACCEPTED.json | ab9a704144921c422018fdddaf8845f39ee47acdaef8bc3aa2c554df162545d5 |
| image.json | e807e9243071ae078305ffa818f35c2902b33606fd20730fd6fe844a0924b7ba |
| frozen/snapshot.json | 716324501ac1e5243a4dbe15fd7ad925c47e61d2b40c039f1241b065f9e0ea61 |
| vcs_source_manifest.json | cc1aade5c86b4254601e5120d5063fe7460e63e718b0117ce004dd53a25d652c |
| simulator.conf | 6aaa87d2cdbabde8aee6baebad81dc7109d08361f788e799a44420f7cd037785 |
| simv | 1344bb3496fd1d6f9f455f75e0180071367319e7431fea971bb38a2243d1f462 |

Service log: memory_candidate07_build/build01.log.
Compiler log: candidate07/campaign/image/_build/vcs/comp.vcs.log.
Aquinas can bind this new image for authorized SoC tests, preserving each old
M6 record and pinning the exact software/oracle. This is the VLDU+VSTU candidate,
not the M6 baseline; local acceptance is not full SoC acceptance.
