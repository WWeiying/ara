# M9 Build Handoff

**BUILD ACCEPTED, NOT DUT PASS.** One authorized build, no retry, no SoC tests launched.

Image: `/home/wangwy/fpga_runs/current_board_memory_candidate09/campaign/image`

- BUILD_ACCEPTED.json SHA256: `348aefdc9e2112f939e5456c94a0e454a45f45e7de118b54d47178a5a70c2368`
- image.json: `48d9e4d2acb1fa239e05549fe695caad36af34c1f02aaffe041bb8261e302b5a`
- snapshot.json: `da19a3f298adc7453600db2cc931693a5329e2ad593569136bc0b797578cbe6e`
- Compiled manifest: `21aa13ec7ee385098bfc0b28312f871e7636af2afe4c008386f59823b3a8d125`
- simv: `f75040906f251bf090fc8c03815c1447640d05e2208df3c88fa12e3dca7d0320`

## Identity
539 frozen sources,453 compiled records,66 image payloads independently rehashed after build. Exact compiled-record comparison against M8 passed after only approved AddrGen substitution and path relocation. Frozen differences are solely AddrGen, frozen.filelist and hardware/bender; the latter two are exact output-root substitutions. VLDU/VSTU and all other source hashes match M8.

Approved AddrGen SHA256: `3736b64136ebbf5629dadb0037457279f9bb91307356c468c9677d321c8c51c5`.
Settings and simulator.conf unchanged: NrLanes4/VLEN1024/L2=2097152, FpgaEn0, OSSupport1/PMP0, QBS1/AKV1/AKVv2=1, IDEALoff. code_coverage0/no_fsdb1/ARA_NO_FSDB; inherited vendor library capability is not enabled waveform dumping. No RTL/helper edits.

## Actual Execution
Direct unit `ara-memory-candidate09-build01.service`, worker2147037, actual vcs1 compiler2148038. RuntimeMaxSec1800, KillMode control-group, Restart no. RemainAfterExit preserves actual terminal attributes:
ExecMainCode1, ExecMainStatus0, Result success, active/exited, MainPID0. This is retained exit evidence, not garbage-collected defaults.

build-image actual waited child0,116.265242s. Worker117.754096s/result0.
Resource admission: no existing VCS/vlogan/vcselab build conflict; MemAvailable104887549952 bytes; free disk10838520274944 bytes;64 CPUs. Child resource accounting:154.768371 user CPU seconds,14.036823 system seconds, maxrss429756 KiB (RUSAGE_CHILDREN accounting, not aggregate machine peak). Durable receipts: output-root admission.json/build_process.json/snapshot_process.json and owned worker_result01.json.

One startup observation followed by bounded pidfd wait, no long-running process polling. Post-build run.json is BUILT with tests=[]; no Error-/Fatal-/Error:/FATAL: lines in image logs.

## Next Scope
Ready for separately authorized four small SoC VLSU tests and same-ELF normal controls16. Build acceptance does not establish M9 functional/regression acceptance. M8 images, frozen sources and background tasks remain untouched.
