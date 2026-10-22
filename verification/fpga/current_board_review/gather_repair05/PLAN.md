# Candidate05 Gather Repair: Preparation Only

No snapshot, build, simulator, software rebuild or RTL change is authorized
by this document. `/home/wangwy/fpga_runs/current_board_memory_candidate05`
does not exist at preparation. All current artifacts are only in this owned
review directory. `preparation01.json` records the exact38 source cases,
16 normal/performance controls,142 reference pins and read-only host evidence.
This is a reviewable plan, not a sealed launch approval or executable campaign.

## Required Gates

1. Confucius supplies measured cycle evidence tying the actual failing Gather
   ELF and original oracle to the index-source origin mismatch. Pin the exact
   ELF, raw log/trace/probe profile, first target PC and finding; do not invent
   a substitute VL2 test or silently shorten a historical prefix.
2. Parent applies and reviews the minimal fix. The provisional expected source
   delta is only `hardware/src/lane/lane_sequencer.sv`; the exact before/after
   hash and allowed hunk must be supplied. Architectural vstart, destination
   preservation, source EEW/VL and hazards are not implicitly approved changes.
3. Pin the evidence, patch, current integration helper, this plan and exact
   parent resource roster in a NEW approval. No pending field is a wildcard.
4. Recheck all live compiled inputs against M4, allowing only the explicitly
   approved patch. At this preparation, all M4 live input hashes match and
   none are missing. Reject unrelated helper/RTL changes or concurrent edits.
5. Freeze into a fresh M5 path; verify the frozen delta again before building.
   Relocated filelist and generated Bender adapter naturally have path-only
   changes. Exclude only these known generated files from the semantic source
   comparison, not arbitrary differing files. Do not modify or replace M4.

## Existing VCS Path

Reuse `verification/fpga/current_board_review/integration/run.py`:

- `snapshot --authorize-freeze` captures the actual Bender filelist, hashes
  source files before/after copy, rejects concurrent changes, dereferences
  source-file links, creates a fixed filelist adapter and makes sources read-only.
- `build-image --authorize-build` checks the sealed snapshot, uses the frozen
  verification runner, bypasses software compilation with `/usr/bin/true`,
  and invokes `make -C hardware compile ... CXX=/usr/bin/g++` into a private
  build directory. It never uses the apps default compiler.
- Preserve all M4 settings: default,4 lanes,VLEN1024,QBS/AKV/AKVv2 enabled,
  L2=2MiB,mc=0,coverage=0,fail_on_assert=1,no_fsdb=1,AXI-delay verification=1,
  store_B baseline=0,UVM-CVXIF=0,source-manifest verification=1,
  no extra sources,ideal_dispatcher=0. No ZCC or Verilator executable/build.
- Bender's existing `script verilator` spelling is only filelist formatting.
  Existing Verilator include files supply DPI headers; no Verilator process
  is invoked. This is the unchanged M4 host-VCS route, not another simulator.
- Environment is sanitized by the existing helper: VCS/Verdi2023.12-SP1,
  host `/usr/bin/g++`, fixed license server27000@t7920; no inherited compiler
  overrides, MAKEFLAGS or simulator flags. License availability was NOT tested.

M4 image ledger SHA256:
`e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673`.
M4 snapshot SHA256:
`b8dcc5d0efc55af13b1e194866135ac2d7370bbcc75276e37d402c5235ea545d`.
M4 captured539 snapshot files and453 manifest records. Verify membership/delta,
not just those counts. Recheck every M4 image pin before/after M5 work.

## Dependencies and Resource Evidence

Read-only observation at1791736693.142547: zero simv (comm OR argv0 scan),
200529838080 bytes available memory and10963865776128 bytes free disk. This
does not release queued/reserved work. A separate compiler observation at
1791736861.0677469 found no matching compiler processes,64 online CPUs and
load averages39.08/37.07/35.52: the host must not be described as idle.

The existing Makefile uses VCS `-j64` code generation even though the image
runner has jobs1. Keep that setting for equivalence; parent must allocate one
build window and prohibit another concurrent VCS image build. Do not confuse
compiler workers with the24-simv execution cap. Before freeze/build and each
replay admission, freshly check >=32GiB available memory, adequate disk,
all actual simv plus unused parent reservations, and pending Whole59/other
services. For replay, total actual-plus-reserved including M5 must be <=24;
no automatic waiting, polling, retry, reservation guessing or peer cancellation.

Measured input links are intact:

| Input | Existing resolved target |
| --- | --- |
| `install` | `/home/wangwy/openproject/ara/install` |
| `hardware/tb/dpi/elfloader.cc` | this worktree's `hardware/deps/cva6/corev_apu/tb/dpi/elfloader.cc` |
| `/usr/lib64/libnuma.so.1` | `/usr/lib64/libnuma.so.1.0.0` |
| Verdi `share/PLI/VCS/LINUX64/pli.a` | same installation's `share/PLI/VCS/linux64/pli.a` |

Existing host make/g++, VCS entrypoint and PLI archive are present. Bender is
the existing `hardware/bender` executable; dependencies are the existing
`hardware/deps` trees. Do not run dependency updates, fetch replacements,
repair links, or create a dependency cache. Freeze copies the actually used
headers/RTL/DPI files by content so the M5 source tree does not retain live
install/DPI input links. Runtime vendor libraries remain the same external
VCS/Verdi installation as M4.

## Future Service Commands (NOT Executed)

Only after the gates above and explicit parent freeze approval, from the
integration worktree with a trusted current-UID user-manager bus environment:

```sh
systemd-run --user --unit=ara-memory-candidate05-freeze01.service \
  --property=RuntimeMaxSec=300 --property=TimeoutStopSec=120 \
  --property=KillMode=control-group --property=Restart=no \
  --property=WorkingDirectory=/home/wangwy/openproject/ara_dsa_signoff_integration \
  /usr/bin/python3 -B verification/fpga/current_board_review/integration/run.py \
  snapshot --out /home/wangwy/fpga_runs/current_board_memory_candidate05/frozen \
  --authorize-freeze
```

Parent retains the freeze service exit/logs, verifies SEALED and exact approved
source delta, then separately authorizes the build. No command chaining or
automatic freeze-to-build transition. Use the existing trusted-user-bus helper
when querying a sanitized environment; do not repeat the prior missing-bus
mistake or treat a collected unit's default success as its historical exit.

```sh
systemd-run --user --unit=ara-memory-candidate05-build01.service \
  --property=RuntimeMaxSec=1800 --property=TimeoutStopSec=120 \
  --property=KillMode=control-group --property=Restart=no \
  --property=WorkingDirectory=/home/wangwy/openproject/ara_dsa_signoff_integration \
  --property=StandardOutput=append:/home/wangwy/fpga_runs/current_board_memory_candidate05/build01.service.log \
  --property=StandardError=append:/home/wangwy/fpga_runs/current_board_memory_candidate05/build01.service.log \
  /usr/bin/python3 -B verification/fpga/current_board_review/integration/run.py \
  build-image \
  --snapshot /home/wangwy/fpga_runs/current_board_memory_candidate05/frozen \
  --out /home/wangwy/fpga_runs/current_board_memory_candidate05/campaign/image \
  --authorize-build
```

The Python worker directly belongs to its service cgroup. Proposed build cap
1800s is conservative headroom over M4's measured118.097207s, not a new runtime
measurement. Freeze cap300s is a bound, not measured duration. Neither timeout
permits automatic retry or budget increase. Keep failed attempts and use new
successor names if later authorized. No expected-long-job polling; parent may
confirm ownership/progress once and inspect after terminal completion.

Build acceptance requires service success, successful compile/elaboration/link,
an existing executable simv, image.json, frozen manifest validation and unchanged
snapshot pins. Do not infer build success from an empty test summary. Pin M5
image/snapshot/configuration/source-manifest hashes and all image files, and
compare simulator.conf with M4. Build success alone authorizes no DUT replay.

## Regression Plan After Separate Review

1. First replay the exact Confucius failing source ELF and retained full oracle
   with its reviewed bounded capture. Probe the index-source request origin,
   accepted operands and architectural result/vstart; preserve M4 before evidence.
   Its identity and budget are pending measured evidence, not guessed here.
2. Reuse all38 exact ELF/hash/oracle/budget entries from
   `integration/candidate04_regression38_03/plan.json`, SHA256
   `6a4b74d7bea9025771fcfb4e48204b58b5bfc80f40450eeec7e0e4f900cc93b9`.
   Groups: original extension1,large-offset6,singles6,combined1,extended5,
   gather2,comparison5,flags1,epoch1,comparison-matrix4,extension-matrix6.
   Jobs4; unchanged per-case bounds180..1200s, sum16200s; service7200s.
   M4 measured runner wall2485.10s, summed case time7703.86s,max1029.67s.
   These support retaining the reviewed budgets, not blindly enlarging them.
3. Reuse the10 exact M4 RVV/QBS/AKV smoke ELFs, jobs2,180s each,service1800s.
   Their stable private M4 ELF paths/hashes are in preparation01.json; do not
   rely on a future rebuilt binary or mutable `/tmp` source wrapper.
4. Compare complete cycle CSVs for16 controls: those10 smokes plus maskslide,
   restart_compare,reduction_fflags,m8widen,wholemove,slide1up_prestart. The
   latter6 are hash-identical to38 entries and need no duplicate execution.
   Thus38+10 =48 distinct unchanged controls, excluding the new discriminator.
   Require equal noncycle events/results and report every cycle difference;
   any normal-control divergence needs explanation, not just a PASS marker.

A new small M5 replay adapter is needed only after image/evidence approval:
parameterize image identity, reuse `integration.run_programs` or its frozen
runner construction, preserve each38-case timeout, stop first failure and retain
private ELF snapshots. Existing M4-specific sealed launchers hardcode M4: do NOT
edit them or call them while claiming an M5 run. Do not flatten all budgets to
one timeout just to use a uniform CLI.

Final acceptance requires exact membership, original full oracle, raw failure
veto even after PASS, private ELF and command/image identity, complete frozen
CSV validation, runner COMPLETE, no sticky abort including late validation,
and unchanged pins. Bind all output evidence and explicitly separate new M5
results from M4's existing PASS. No Whole59,full1134,held682 or unrelated parent
campaign is silently added to this scope. M4 remains immutable throughout.
