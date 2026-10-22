# M9 Build Startup

One authorized build; no DUT launched or M8 background task queried.

- Direct service ara-memory-candidate09-build01.service; worker2147037; actual vcs1 compiler2148038.
- Independent root /home/wangwy/fpga_runs/current_board_memory_candidate09.
- RuntimeMaxSec1800, KillMode control-group, Restart no, RemainAfterExit yes for retained exit properties.
- Admission: no vcs/vcs1/vlogan/vcselab conflict; MemAvailable104887549952 bytes, disk available10838520274944 bytes,64 CPUs.
- Read-only preparation actual exit0; only approved AddrGen3736b64136ebbf5629dadb0037457279f9bb91307356c468c9677d321c8c51c5 differs from M8 source set.
- Build script SHA256 bdc08f7cba51ef3cfaf0ad23aa2407bc71b2275ac70972f90ab06bb6ac1434cc.
- Same NrLanes4/VLEN1024/L2=2MiB/QBS+AKV, FpgaEn0/IDEALoff, no coverage/waveform dumping. Vendor waveform library support flags are inherited; ARA_NO_FSDB disables dumping.
- After one startup observation, wait is bounded pidfd on actual worker, not a build polling loop. Startup is not BUILD_ACCEPTED.
