# Full E32 MF2 M6 Entry Review01

Decision: APPROVE_FULL_E32_MF2_M6_ENTRY. No blockers in the exact frozen plan.
Conditional on new pinned parent authorization, budget-risk acceptance and
runtime owner/resource admission. This is not DUT acceptance or a launch.

Plan SHA `b75d801b6533b73bfa9127ff695b60642a421535f9528202b07248fc3f368c93`.
Ready SHA `feb3ba36408f4ab68d725a75cc1c515e3a65932c90e828e381419699a2ddde09`.
873 plan entries checked:871 current nonraw hashes match; the two reference
commits.log entries retain original accepted digests without being read/hashed
again. All860 old plan entries are inherited unchanged. No tests, raw CSV or
reference parsing, build, live-service/resource query or DUT execution occurred.

## Source And Reset

Unchanged e32 SoC ELF
`54931771b1ba6ade43ae776af14f52163323670ec8881dc2fc1f70fe1c6c994f`;
full5985 original ordered calls,35 operations,3 seeds/global RNG, cap16. Model
SHA `53ecb785957eae31062c3d0ce05df289a78f6af286ca68537a33965011425c9e`
matches the original plan; e32 spec equals its original frozen specification.
No partition, software change, order reduction or replacement oracle.

Reference scope is reused from the accepted fullSmall2 independent ENTRY
SHA88c9d814d713c0095fba0d2bd4e3f5c104795a70605bc8ec739f76eda091b8e3,
its pinned review/process/evidence and source READYdb878aa2... . Those existing
records accept the approved original two-shape reference recovery, including
this5985-call e32 scope. This is not another raw audit. The original C bytes
were not recovered: provenance is byte-equivalent original reconstruction with
archived ELF/helper proof, not a newly recovered original C or Linux replay.

New profile SHA
`b0c5f3860c09ae2e63c661432f29ac0b31ced24e3a071656a8df8077178d6418`
is exactly the approved e8 M6 reset proof with allowed_shape changed to e32,
source_profile_sha256 retained and exact e32 ELF identity added. M6 image,
snapshot, compiled manifest/configuration, FpgaEn0 and FF-regfile reset pins
are unchanged. Initial zeros are hardware/profile-specific, not ISA defaults.

Checker imports the hash-pinned reviewed proof/legacy modules, checks both
profiles, exact e32 spec/model/ELF, then initializes32 reset GPR values. Static
AST inspection confirms Strict overrides only __init__; original consume/finish
remain inherited. Scalar address/BE/unshifted-data/source equality, every setup/
RNG/FP table transition, original13 helper instructions, full16 results+2 guards,
prestart/inactive/tail/vstart, vlenb128/capacity16, counters, CTRL0 and original
park remain. Required totals:95760 results,11970 guards,5985 vstart checks,
77805 helper instructions. No unknown-source learning or invented fflags oracle.

## Host And Runtime Gates

Host15 PASS has actual child wait0, timeoutfalse,51.186998214 seconds within300s.
Test source includes one full5985 constructed stream and actual e32 executable
_start/BSS/main ABI instructions, explicitly not captured DUT rows. It reproduces
the old s0-state failure and rejects wrong value/address/read/write masks,
unknown source, profile/spec/model mismatch, missing start, final result/guard,
incomplete completion, postcheck error, late abort, owner and late-plan drift.
Existing Host was read, not rerun; real ABI and full-oracle coverage are distinct.

Monitor wrapper hooks the frozen runner's actual _run_monitored call. It requires
an integer wait result and fsyncs unvalidated outcome, timeout/failure/cancellation,
command/CWD/hash before generic or strict postchecks. A generic exception cannot
erase that durable simulator outcome. Wrapper preserves numeric result on strict
postcheck error; timeout/failure/non-PASS sets the local abort and cannot pass.

One independent threading.Event and private simulator process group/cgroup are
used, not the old whole2 cancellation event. No retry branch exists. Worker
requires runner COMPLETE/PASS1, exact test/jobs/timeout/image/trace metadata,
summary equality, full strict/log/ELF/command checks, late disk-plan validation,
image/review pins and sticky-abort terminal publication. Timer is canceled/joined
before final elapsed/deadline check. Old complete.json is pinned and still
NOT_PASS with original e32 CANCELLED; no old raw or helper is reused for mutation.

## Command And Budgets

Fresh unit `ara-arithmetic-full-e32-mf2-m6-01.service`; direct python worker
MainPID, matching own cgroup, RuntimeMaxSec13200 (3h40m), KillMode=control-group,
Restart=no and trusted user bus are runtime-gated. Jobs1/case10800/worker12000/
service13200 are exact. Case admission retains the full case plus900s observer
allowance within the worker deadline; insufficient remaining time rejects
without running, shortening, extending or retrying the case.

Dryrun SHA97e72107... emits exactly one private input.elf/CWD command for
runtime id arithmetic_full_e32_mf2, source label rvv_matrix_e32_mf2, seed1,
NO_FSDB and new-output COMMIT_TRACE. Source/runtime labels remain distinct.
The reviewed service command matches ready.json; only its entry/parent path+SHA
placeholders are to be replaced. Existing prepared output has no launch/replay
or complete result. No live process was queried to establish that fact.

Runtime admission checks live simulators+jobs1+unused reserve0 <=24 and
MemAvailable>=32GiB; unreadable potential processes fail closed except exit races.
Parent must coordinate external reservations. No live capacity claim is made.

The old slow proxy plus20% is11477s, exceeding fixed simulator10800 by677s.
Completion is not guaranteed. Parent reviews() must explicitly bind new plan,
entry hash, unit and budget_risk_accepted=true. No timeout extension or oracle
reduction is approved by this review.

## Bound Files

- checker.py: `380aaa3f1672e9480bc0b7a85b6744029f4db3fc0bddf78121e7835dacd35c7d`.
- replay.py: `60a7d34aeb10931ec708479285ec80087cbebed61058380d9ebe4bf94e011dec`.
- host01.json: `35429b85ebcabeb679b2252b5ef708e55da26bda2595b4f6a0adc7971aeb3f48`.
- host_process_exit.json: `390feb293e6425ed306cd1d50c370452032693b633f5778f620ac28f437e36cc`.
- dryrun.json: `97e72107fed752d469c07df2501a13428e32b6f4a5d3125233f31c39a8d834bb`.

ENTRY.json supplies the worker-compatible review schema and actual evidence
pins. Main must separately authorize this one new standalone run. Prior e8
acceptance and old full2/e32 cancellation history remain separate; no DUT PASS,
Linux, all22-shape or service-exit acceptance is claimed here.
