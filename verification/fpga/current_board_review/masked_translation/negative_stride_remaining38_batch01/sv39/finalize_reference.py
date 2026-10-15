#!/usr/bin/env python3
"""Package terminal reference receipts without replaying or reparsing references."""
import argparse
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import prepare_sv39 as p
import checker02 as oracle


def main():
    args = argparse.ArgumentParser()
    args.add_argument('--outer-receipt',type=Path,required=True)
    a = args.parse_args()
    r = p.HERE/'reference02'
    outer = p.read(a.outer_receipt)
    p.require(type(outer['actual_exit_code']) is int and outer['actual_exit_code']==0 and
              outer['tool_session_id']==78962,'Actual observed outer tool completion required')
    result = p.read(r/'complete.json')
    p.require(result['status']=='REFERENCE_38_PASS_NOT_DUT' and result['pins_unchanged'] and result['no_dut'],
              'All references must be terminal accepted')
    built = p.read(p.OUT/'built.json')
    pins = {**p.read(r/'input_pins.json'),**p.read(r/'artifact_pins.json')}
    p.verify(pins)
    for f in (a.outer_receipt,r/'artifact_pins.json',p.HERE/'finalize_reference.py'):
        pins[str(f.resolve())] = p.sha(f)
    names, groups, ref_steps = [], [], 0
    for i,(b,q) in enumerate(zip(built['groups'],result['groups'])):
        label = f'group{i:02d}'
        p.require(b['group']==q['group']==label,'Group order')
        d,o = p.OUT/label,r/label
        cases = p.read(d/'cases.json')
        status,done,proof = p.read(o/'status.json'),p.read(o/'complete.json'),p.read(d/'source_proof.json')
        for k in ('spike_actual_wait','parser_actual_wait'):
            p.require(type(done[k]) is int and done[k]==0,'Numeric actual wait')
        p.require(done['status']=='REFERENCE_ACCEPTED_NOT_DUT' and done['pins_unchanged'] and
                  done['result_sha256']==p.sha(o/'status.json'),'Per-group terminal receipt')
        p.require(status['status']=='REFERENCE_PASS_NOT_DUT' and
                  status['case_count']==len(cases)==q['cases']==(4 if i<9 else 2) and
                  status['htif']==[1] and status['boot_records']==5 and
                  status['firmware_records_through_htif']==q['firmware_records']<8000000,'Reference scope/HTIF/bound')
        points,checks = oracle.check_counts([c['parameters'] for c in cases])
        p.require(checks==status['scalar_checks']==q['scalar_checks'],'Independent scalar count')
        for j,(case,e) in enumerate(zip(cases,status['cases'])):
            t = case['parameters']
            p.require(e['actions']==oracle.expected_actions(t) and
                      [x['checks'] for x in e['checkpoints']]==[points[j,k] for k in range(4)],'All ordered checkpoints')
        current = [c['name'] for c in cases]
        p.require(proof['cases']==current and b['source_proof_sha256']==p.sha(d/'source_proof.json'),'Original source ledger')
        for backend in ('soc','spike'):
            p.require(proof['backends'][backend]['sha256']==p.sha(d/(backend+'.elf')),'Unchanged ELF')
        names += current
        ref_steps += q['firmware_records']
        groups.append(dict(q,original_names=current,soc_elf=str(d/'soc.elf'),soc_elf_sha256=p.sha(d/'soc.elf'),
                           spike_elf_sha256=p.sha(d/'spike.elf'),reference_result=str(o/'status.json'),
                           reference_result_sha256=p.sha(o/'status.json'),source_proof_sha256=p.sha(d/'source_proof.json')))
    original = p.read(p.HERE.parent/'prepared01/manifest.json')
    expected = [n for batch in original['groups'] for n in batch['cases']]
    p.require(names==expected and len(names)==len(set(names))==38 and len(groups)==10,'Exact38 original order')
    for host in (p.OUT/'host_negatives.log.wait.json',r/'host.log.wait.json'):
        x = p.read(host)
        p.require(type(x['actual_wait_returncode']) is int and x['actual_wait_returncode']==0 and not x['timeout'],'Host numeric receipt')
    ready = dict(status='READY_38_SOURCE_SV39_REFERENCE_NOT_DUT',cases=38,groups=groups,pins=pins,
        actual_isa=p.ISA,firmware_records_total=ref_steps,scalar_checks_total=sum(x['scalar_checks'] for x in groups),
        full_memory_bytes_per_case=8192,full_result_halfwords_per_case=64,guards_per_case=2,
        scope='38 source-derived archived singles; excludes two already accepted M6 pilots',
        archived_full_Linux_ELF_identity=False,original_per_trial_failure_equivalence_proven=False,
        linux_signalframe_equivalence=False,DUT_started=False,M6_DUT_accepted=False,M7_DUT_accepted=False,
        original_full_parent96_closed=False,outer_tool_receipt=str(a.outer_receipt.resolve()),
        uncertainty='Partial active suffix in saved fault snapshots is unconstrained, including when retained at final checkpoint',
        budget=dict(model='firmware records / (858371 / 1111.6245557051152) * 1.2',
                    basis='Actual accepted M6 store pilot; not measured M7 throughput',
                    all_estimates_under_10800=all(x['conservative_m6_estimate_s']<=10800 for x in groups),
                    no_completion_guarantee=True,no_automatic_extension=True))
    p.save(p.HERE/'READY.json',ready)
    rows = '\n'.join(f'| {g["group"]} | {g["cases"]} | {g["firmware_records"]:,} | {g["scalar_checks"]:,} | '
                     f'{g["spike_elapsed_s"]:.2f} | {g["parser_elapsed_s"]:.2f} | {g["conservative_m6_estimate_s"]/60:.2f} |' for g in groups)
    report = f'''# Remaining38 Sv39 Software Reference

Status: **38/38 reference PASS, 10 groups (9x4 + 1x2); NOT DUT acceptance**.
All 20 original prepared SoC/Spike ELFs remain unchanged in `software01/group00..09`.
Manifest and source proofs preserve exact original group/member order and each original
10-instruction load/store helper plus 3-instruction capacity helper. Runtime/ELF identity
is source-derived, not byte identity with archived Linux executables or Linux signal frames.
The original single source linkage does not prove equivalence to every lost parent failing trial.

| Group | Cases | Firmware records to HTIF | Checks | Spike seconds | Parser seconds | M6 estimated minutes |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
{rows}

Totals: {ref_steps:,} firmware records, {ready['scalar_checks_total']:,} actual scalar checks;
{sum(g['spike_elapsed_s'] for g in groups):.2f}s summed actual Spike time and
{sum(g['parser_elapsed_s'] for g in groups):.2f}s summed successful parser time.
These are child durations, not total wall-clock (hashing/Host/first failed parser excluded).
Firmware commit records may include a partial fault record and are not exact architectural minstret.
Every group separately proves five boot records, HTIF1, exact original park, restored CSR,
all four checkpoints, actual target addresses, same-PC nonzero restart, and full final data.
Actual Spike/parser waits are numeric zero in every `reference02/groupNN/complete.json`;
original group00 Spike receipt/raw is reused from `reference01`, not rerun.
The outer invocation receipt is `{a.outer_receipt.name}`. No systemd exit is inferred.

## Oracle Boundaries

14 fault cases restart at element2 or5; 24 all-off cases have no target memory fault,
retry or prefix poison. All preserve CAP64, VL8, original input/offset/mask setup,
two output guards, neighbor registers, full8KiB memory and PTE/physical guards.
u0 repairs data permissions without refill; u1 remaps/refills; all-off performs original
post-completion cleanup only. Completed prefix is checked and poisoned exactly once.
Unfinished active load suffix in the fault snapshot and permitted pending store suffix
are observed but not forced to an invented value. Final results and final memory are exact;
the retained **old fault snapshot** remains legitimately partially unconstrained.

## Preserved History

`reference01` remains NOT_ACCEPTED: the original parser rejected its static ownership set
before raw parsing because it omitted the real wrapper retry VSET (0082f2d7).
`checker02.py` adds only that instruction with exact owner/window/count checks; Host6
passed and the same group00 raw was parsed offline. Original Host fixture-negative
adjustments and CSV Host draft failure have separate receipts; no original record overwritten.
Original fixture/checker Host9 passed. Current software/reference SHA inventory is in
`READY.json`, SHA `{p.sha(p.HERE/'READY.json')}`.

## M6 Execution Boundary

Cost estimates use the measured accepted M6 store pilot throughput plus20%, not M7.
Highest estimate: {max(g['conservative_m6_estimate_s'] for g in groups):.2f}s;
all groups under10800s estimate: {ready['budget']['all_estimates_under_10800']}.
No software optimization/rebuild has been performed. The sealed M6 image alone may be used
for the authorized two-lane background replay; M7 fixes/acceptance remain separate.
The draft grouped CSV checker is in `vcs_m6_plan01`; its launch integration is not yet
accepted. Reference READY does not authorize bypassing that terminal oracle or numeric exits.
No DUT has been started by this preparation. Do not reuse the earlier7200s rough estimate.
'''
    with (p.HERE/'REPORT.md').open('x') as f:
        f.write(report)
    print(json.dumps(dict(status=ready['status'],ready_sha256=p.sha(p.HERE/'READY.json'),
                          report_sha256=p.sha(p.HERE/'REPORT.md'),firmware_records=ref_steps,
                          checks=ready['scalar_checks_total'],max_estimate_s=max(g['conservative_m6_estimate_s'] for g in groups))))


if __name__=='__main__':
    main()
