# NF8 Original192: Candidate04 Jobs8 Successor

Preparation only. This successor does not change the running reference plan,
ELFs, fixture, oracle, candidate04 image, or production RTL. No full192 DUT run
is authorized by this document. A ready preflight requires all gates below;
the existence of this document is not a PASS or launch approval.

## Scope and Gates

- Preserve all original trial IDs 0..191 in 48 fixed groups. Group g contains
  exactly trials 4g..4g+3. No representative substitution or reordering.
- Require `reference_campaign01/complete.json` to be terminal
  `HOST_SPIKE_ALL192_PASS_NOT_DUT`, with exact membership, comparison counts,
  source provenance, ELF hashes, partition pins, and per-trial negatives.
- Require `vcs_jobs8.py host-validate` to accept all48 Spike-derived CSVs and
  independent comparison ledgers, including permitted partial-field states,
  forbidden memory/CSR/guard changes, firsterror, restoration and final magic.
  Group0's existing host CSV acceptance is reused only with unchanged pins.
- Require selected4 independent acceptance and candidate04's immutable image,
  all539 source inputs, configuration, source manifest, and runtime libraries.
- `preflight` performs ELF/interface checks, host scheduler/gate negatives,
  and integration runner dry-run only. It creates a pinned ready plan and an
  unauthorized review template; it never starts VCS.
- Parent review must bind the ready plan hash, image hash, jobs8, and exact
  service units for parent38, gather and whole-register reservations.

## Execution and Bounds

The reviewed worker uses the existing `integration/run.py` with no rebuild.
It first runs group0 alone. All four cases, complete comparison ledger,
trap/retry state, whole memory, physical tails/guards, CSR restoration,
completion magic, input ELF and image identities must pass before admitting
groups1..47 with at most eight workers. The own8 reservation remains held
during the pilot. A first failure cancels this worker's queued/active work;
it never cancels another campaign. No automatic retry is permitted.

Each group has a fixed 2400s simulator budget and a 2520s runner/checker bound.
The future service has a fixed 18000s outer limit, local append stdout/stderr,
and control-group teardown. One pilot plus six remaining waves gives
`7 * 2520 + 360 = 18000` seconds. The final360s is shared startup, admission,
pin verification and aggregate headroom, not extra simulator time. If this
bound is exhausted, preserve a non-PASS interruption; do not extend or retry.

The selected4 timing calibration projects about83171 CPU-worker seconds,
or2.9h at ideal eight-way packing before serial-pilot overhead. Allow roughly
3.3h including the pilot under comparable load; this is an estimate, not an
acceptance timeout or a promised completion time. Alloff groups are cheaper,
so actual packing and host contention affect the wall time.

## One-Shot Admission

Latest reservations are NF7=2, parent38=4, gather=4, whole-register=6, ownNF8=8.
The NF7 unit is `ara-indexed-nf7-candidate02-06.service`; the other exact unit
names must be supplied by reviewed configuration, not inferred from argv.

The worker takes one read-only process/memory snapshot and requires:

```
other_simv
  + max(NF7_actual, 2)
  + max(parent38_actual, 4)
  + max(gather_actual, 4)
  + max(whole_actual, 6)
  + 8 <= 24
MemAvailable >= 32 GiB
```

Ownership uses exact cgroup service components. Missing/GC'd services still
retain their reservation. Other legitimate processes are recorded and
counted, not killed or relabeled. With all24 slots reserved, an additional
unreserved simulator causes refusal. Capacity refusal does not wait, poll,
retry, or alter other work. Parent coordination must keep these reservations
consistent with other launchers; this read-only gate is not a global lock.

## Preparation Commands

Run these only after the corresponding prerequisite is terminal and accepted,
using fresh owned output paths. Neither command launches VCS:

```
python3 -B vcs_jobs8.py host-validate --out dut_host_all192_01
python3 -B vcs_jobs8.py preflight --out vcs_jobs8_plan01 --host-root dut_host_all192_01
```

After preparation, report the ready plan/code/image pins to the parent. A
future launch requires explicit reviewed `review.json` and `--authorize-run`;
do not launch merely because the reference or preflight passed. Confirm real
simulator startup once after an authorized launch, then inspect on terminal
notification without frequent polling.

## Coverage Boundary

This is the source-derived original192 geometry with genuine Sv39 page tables,
precise fault/retry, prefix poison and full oracle. It retains original source
and archived assembly identities and the allowed partial-segment semantics.
It is not execution of the original Linux ELF, a Linux SIG-context replay,
or localization/closure of the original169/128 aggregate error counts.
