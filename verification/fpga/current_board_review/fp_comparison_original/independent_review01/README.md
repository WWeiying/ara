# Independent review 01 — sealed restart plan05

**Conclusion: BLOCKER for exact sealed-source signoff (one medium-severity finding).**
The two-case execution and acceptance logic is otherwise consistent with the
requested 260-call scope. This review does not authorize launch. No RTL/shared/
sealed files were edited; no prepare/work entry points, builds, DUT runs,
services, or active-job polling were invoked. Only this directory and isolated
temporary host-test directories were written.

Reviewed plan SHA256:
`f0edb7011fdd4a69e0b633f03fa94405c072b7874367b69e3ab864e570069667`.
Predecessor plan03 SHA256:
`f503af9bfac573987090e3ac1eea08f10f8e7768e390c757ea4e5095769caed6`.
Both match the request; all 2,731 listed pins matched independently computed
SHA256 values. See [identity.json](identity.json).

## Finding F1 — medium, source-sealing blocker

**The executed pin-verification helper imports an unpinned live dependency.**

Locations relative to `verification/fpga/current_board_review/`:

- `fp_comparison_original/prepare_m4_plan.py:160–164`: explicit helper pins
  include this script, `integration/run.py`, and `comparison_alias_original/replay19.py`,
  but do not close over `integration/prepare.py`.
- `fp_comparison_original/replay_restart_successor.py:185` and `:193`:
  before/after verification invokes `prior.shared_adapter.verify(data['pins'])`.
- `comparison_alias_original/replay19.py:61–63`: that verification executes
  `p.prepare.sha(...)`.
- `comparison_alias_original/prepare19.py:15` imports the live integration
  `prepare` module; `integration/run.py:13` also imports its `sha` function.
- `integration/prepare.py:52–53`: this unpinned function implements SHA256;
  `integration/run.py:115–118` uses it to check frozen-source identity.

An isolated import confirmed the actual module is
`/home/wangwy/openproject/ara_dsa_signoff_integration/verification/fpga/current_board_review/integration/prepare.py`,
SHA256 `c8852599c65e0a0812a7dc77dc365eb40398252867a29b226f34d758e5c56cf8`.
Its absolute path is absent from plan05's pin mapping. Thus this live code can
change while the approved plan hash and every listed pin still match; source
identity does not cover all executed project code, including code used to
establish that identity. The currently inspected helper is correct; this is
an identity-closure defect, not evidence of an existing false DUT PASS.

Evidence: [host_evidence.json](host_evidence.json), `imported_modules`.
Resolve with an explicitly reviewed successor seal or supplementary enforced
before/after dependency pin, preserving plan05. Review the loaded project
module closure when doing so. This reviewer made no fix.

## Execution and oracle review

`replay_restart_successor.py:47–54` checks jobs2, stop-on-failure intent,
no-build, exact two names, 130 calls and 3600 seconds each, and complete equality
with the selected plan03 case entries. The complete held682 entry must equal
the predecessor's other entry and is never included in the test list.
The accepted result at `:197–207` requires both exact names, PASS, returncode0,
and post-run identity checks; it explicitly reports 260 calls, held682 and
`full942_dut_pass=false`. Host/Spike evidence cannot satisfy this branch.

Both source sequences were reconstructed independently from the loop nesting:
130 op0 calls, including 32 VL0 calls and 88 total calls with vstart >= VL per
case. Every target PC/opcode is present in the pinned SoC disassembly. The
prefix transformation removes exactly the after-oracle stop and label to
recover the original C; the runtime wrapper changes are exactly entry/I/O/
exit adaptation. Per-call data, flags, prestart, vstart and guard checks remain.
All three original rebuilt parent ELFs equal their archived original ELF
hashes, and all three assembly files equal archived originals. See
[source_audit.json](source_audit.json) and `original_sources` in
[host_evidence.json](host_evidence.json).

Actual call path:
`work(:181)` -> `execute(:121)` -> `identity(:29)` -> frozen `RunOptions` and
`RegressionRunner` -> admitted/checked `_run_test` -> frozen `_run_monitored`
-> trace/raw check -> suite reports -> successor `complete.json`.
`RunOptions` positional fields were checked against frozen `runner.py:41–56`:
jobs2, seed1, build_only false, skip_build true, explicit pinned simv,
commit_trace true, timeout override None. The frozen `build()` at `:370–384`
returns the reused simv without rebuilding software or hardware. The case
timeout therefore comes from each case's 3600 seconds (`:478–481`).
Frozen runner path for references below:
`/home/wangwy/fpga_runs/current_board_memory_candidate04/frozen/sources/verification/ara_verify/runner.py`.

The outer limit is operationally supplied, not enforced by Python:
`candidate04_restart_plan05/README.md:51–55` documents a direct systemd worker
with RuntimeMaxSec=4500, TimeoutStopSec=120, KillMode=control-group and Restart=no.
The extra stop grace means 4500 is the runtime limit, not a guaranteed final
cgroup disappearance deadline. The pinned dry-run metadata has only the two
DRY_RUN entries, jobs2 and commit trace enabled.

## Failure, trace and cancellation review

`prepare_m4_plan.py:25–36` requires one exact original sew/count/errors summary,
one of each case/pass marker, tohost0 success and `$finish`, and vetoes raw
failure/detail markers. The frozen combined FAIL_RE preserves case-insensitive
assertion/fatal handling (`runner.py:33–38`; successor `:125`). It scans during
execution (`runner.py:193–215`) and scans full console plus available VCS log
before success classification (`:508–547`). Earlier recognized failures cannot
be overridden by later success. Returncode0 is independently required.

Missing console, invalid/unreadable console, missing trace, malformed CSV,
bad order/opcode/count and checker exceptions fail closed. The VCS duplicate
log is optional; the console and commit CSV are compulsory. Exceptions in either
admission or strict checking set the shared cancellation event. The frozen
monitor stops a private process group with TERM/KILL in `finally`
(`runner.py:155–171,193–219`); peers observe cancellation, and queued tests check
the event before starting (`:423–425`). With two cases/jobs2 there are no later
planned queue entries. A scheduling race can briefly start a peer already past
its entry check, but `_run_monitored` observes cancellation and kills it; this
cannot yield a two-case PASS. Future exceptions become ERROR results at
`:627–632`, and the successor cannot publish acceptance from them.

The CSV producer is frozen
`hardware/tb/ara_commit_monitor.sv:88–89,117–118,144–145,247–286`: decimal cycle
and contiguous zero-based retirement order, hexadecimal PC/instruction,
decimal trap, and multiple retirement ports may share a cycle. The strict
checker correctly allows equal cycles. RVFI retirement is independent of Ara
backend allocation. In frozen `hardware/src/ara_dispatcher.sv:5966–5997`,
VL0/prestart no-ops acknowledge and respond without backend allocation and
clear vstart; the original assembly still executes its compare instruction.
Therefore all 130 compare retirements are required, including the 88 calls
with vstart >= VL.

The runner first applies frozen `trace.py:107–253` to the full CSV, including
request/response and backend-uop consistency and unknown-event rejection;
the added checker then requires no trapped retirement, contiguous retirement
order, exact PC/opcode identity and all ten counts (130 for op0, zero for each
other op). Ten closed, pinned M2/M4 traces from the sealed budget were scanned
independently: all retirement order/cycle/trap assumptions match, with counts
and last cycles equal to the recorded values. No active trace was read.

Limitations: target counts do not themselves prove target tuple order; the
pinned original program and complete per-call oracle provide that binding.
Neither checker requires an exact scalar instruction count or a trace footer;
this is not a proof against deliberate CSV fabrication or truncation after
the final target. Fresh output, input snapshots, raw completion markers and
frozen production are part of the evidence chain. A reset within a trace would
be rejected. None of these limitations creates a demonstrated false PASS in
the intended execution path.

## Authorization and resource review

`work:181–190` requires explicit authorize-run, exact approved plan SHA,
review file SHA, a fresh fixed output path, source pins, evidence gates and
admission before creating the run. `RUN.mkdir()` also refuses an existing
directory. Post-run checks at `:193–196` bind pins, plan, review and all gate
evidence. Changes or missing evidence cannot produce accepted completion.

`gates:87–118` requires parent authorization/image/jobs/accounting confirmation;
the exact final38 terminal path, matching plan hash, 38 exact names and PASS/
returncode0/pins/image; Gather terminal and worker-exit records with matching
plan hashes and positive finish timestamps; NF8 initial jobs/reservation8,
cap24, memory admission and shared-unit identities; and inactive/failed Gather
and final38 services. A failed Gather terminal releases scheduling only.
This review did not reread current terminal records or query systemd; parent
reports final38 independently accepted, and actual launch readiness remains
unestablished here.

`resource_math:57–71` requires seven distinct valid unit names, rejects live
Gather/38 simv workers, reserves whole6/NF7two/NF8eight/prefix5two/FPtwo (20
total), charges max(actual,reserved) for each and every unknown simv process,
and enforces cap24/MemAvailable32GiB. Actual above-quota workers increase the
charge. Checks run before startup and both dispatches, without retry.

Residual operational assumptions: the parent must supply true service
identities, bind the FP unit to the documented service, and use the real NF8
admission record (its path is parent-selected; NF8's own unit is not derived
from that record). Resource snapshots are not an atomic global reservation;
other campaigns must honor the coordinated quotas. The script counts `simv`
processes, not arbitrary EDA names or all descendant processes. These are
parent coordination requirements, not evidence of current gate satisfaction.

## Host-test audit and evidence

The inherited 27 checks and successor 15 checks were independently rerun with
Python `-B`, without prepare/work. The former cover selected raw markers,
missing success evidence, count/duplicate summary, returncode, exception
cancellation, empty38 rejection and basic trace mutations. The latter cover
membership/held682/budget/jobs plus quota/memory/unit math. They do not exercise
the real gates, process-group teardown or whole frozen-runner execution.

An additional 21 isolated host checks cover earlier failure markers, every
duplicate PASS marker, 130 targets with shared cycles, missing/extra targets,
unexpected zero-count operators, backward cycles, wrong PCs, malformed CSV,
and missing/unreadable log/trace exception cancellation. All passed. No test
result here is DUT acceptance.

Evidence:

- [host_review.py](host_review.py): reproducible host-only checks.
- [host_evidence.json](host_evidence.json): results, loaded-module pin closure,
  original identities and historical trace audits.
- [successor_rerun.log](successor_rerun.log): 15 successor tests PASS.
- [identity.json](identity.json): requested hashes and all 2,731 pins.
- [image_identity.json](image_identity.json): read-only frozen image/source/
  manifest/configuration validation and actual runner module origin.
- [source_audit.json](source_audit.json): exact wrapper, sequence and target
  disassembly checks for both scheduled prefixes.

Additional nonblocking cautions: strict trace assertions depend on normal
Python mode; the documented command uses no `-O` and sanitizes inherited
Python environment overrides. The extended raw regex treats even
`UVM_FATAL : 0` as a veto, so it could falsely reject a future UVM summary;
this frozen image disables that UVM mode. Neither issue justifies weakening
the current acceptance checks. No current DUT timing guarantee was established.
