# NF2 Remaining34 Plus J4 Entry Review

2026-10-12. READY FOR PARENT CONDITIONAL LAUNCH; no blocking finding.
Read-only static/schema/hash audit. No Host rerun, raw reference/CSV reparse,
compile, simulation, live process query or resource admission performed.

## Actual Prerequisites

Plan SHA `b2fb0d810d7004769a18c7b0527e14b013979791ace008edb4155240126bb586`;
all1240 pinned files rehashed with zero mismatches.

The real reference audit has schema
nf2_remaining34_independent_reference_audit_v1 and status
ACCEPTED_REFERENCE34_NOT_DUT. All9 group IDs, SoC ELF hashes, record counts and
check counts match READY. The complete independent pins_pre set equals READY
pins plus READY itself. Source34 membership/order, group reports, source audit,
audit script and REVIEW hashes are bound, not a placeholder acceptance.

Pilot audit SHA
`79037611e05a12289eb6734b836f8cbcb5c28658bd0a88f3002fc895d5bb51ee`
and real completion SHA
`39c697f34c0db5b827cdebb428e7e5181ce0631715cfe8cc71f2d63bf554fcbe`
match the gate. The real audit accepts the exact4 cases on M6, records strict
NF2_CSV_ORACLE_PASS, unchanged pins, raw-log veto and persisted numeric child0
(elapsed1759.4446330131032s). Launch rechecks actual COMPLETE/PASS, noabort,
summary, durable child/command, private ELF and raw evidence pins before any
dispatch. Null/ERROR or console-only recovery does not satisfy this gate.

## Scope And Dispatch

Nine new ELFs cover34 exact standalone source cases, dimensions4x8+2.
Group09 contains only u1_s1_b5_m3_f0 and u1_s1_b5_m3_f1; its observer runs in
a separate process with N=2. Other groups likewise configure independent
observer subprocesses, avoiding shared mutable group state across threads.

J4 retains old ELF SHA
`2ddce29de6d035fb02616f7924235b03e8863a74dfad161c3b2a4219ced61a67`
and old b3/b5 observer contract; no recompilation. Its2 historical failures
plus2 positive controls are distinct from34 new failures and accepted pilot4.
Thus40 source failures, not42. Runtime IDs are distinct from historical names;
all10 dryrun commands match their actual ELF, TESTCASE, seed1 and private cwd.
Real runs require private ELF copies and exact frozen M6 metadata.

Per-ELF seconds, group01..09 then J4:
5700,5400,6000,5700,6000,5700,6300,6000,3000,5400.
Runner options.timeout_s=None preserves these TestCase budgets. Maximum3
workers; each dispatch must retain its full budget plus600s validation reserve.
Worker bound25200s, service27000s/control-group/Restart=no; no build/retry/FSDB.
These are limits and planning proxies, not guaranteed completion times.

## Failure And Evidence Gates

Consumed29 passing Host tests and10 actual DRY_RUN results without rerunning.
Durable child outcome is exclusively written/fsynced before strict checking;
numeric rc0, name, elapsed, command body/SHA and non-acceptance status are
checked. Checker exceptions fail the result and set shared sticky abort;
queued work and active runner monitoring share that cancellation event.
Both raw logs have failure vetoes. Exact all10 COMPLETE results, individual
budgets, summary, observers, final fresh plan/source/image/approval pins and
evidence hashes are required. Deadline timer is cancelled/joined before
terminal publication, with an elapsed-deadline check and sticky signal abort.

Direct-owning service identity and resource admission remain mandatory at
authorized run. No current capacity or historical service-exit claim is made
by this review. All10 new results must PASS before batch acceptance; this is
source-derived Sv39 coverage, not Linux signal-frame/full-parent closure.

Reviewed worker SHA: `1c9e98f595c691da52f5d814148b46e444356fa9e7b075f2d444dc435d406661`.
Checker SHA: `eb609c834d716a917ad635b4182ff3a7a4f40a6a647ac7835b78fdd51834311f`.
Gates SHA: `332078e34d872de5f5d29db793b0afd70b5b89d32aac29f39e1f4804b9aba4b7`.
