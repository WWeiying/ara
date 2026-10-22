#!/usr/bin/env python3
"""Host-only GC admission positives and fail-closed negatives; no simulator."""
import copy
from pathlib import Path
import sys
import tempfile
from unittest import mock

sys.dont_write_bytecode = True
import successor_gate02 as s


def main():
    rejected = []
    def reject(name, call):
        try:
            call()
        except (ValueError, FileNotFoundError, KeyError):
            rejected.append(name)
        else:
            raise AssertionError('Accepted invalid input: ' + name)

    missing = dict(LoadState='not-found', ActiveState='inactive', MainPID='0', ControlGroup='')
    live = dict(LoadState='loaded', ActiveState='active', MainPID='10',
                ControlGroup='/user.slice/' + s.ARITH_UNIT)
    image = dict(simv='/image/simv', files={'/image/simv': 'imagehash'})
    main_process = dict(pid=10, exe='/usr/bin/python3', argv=['python3', str(s.ARITH)],
        cwd='/tmp', cgroups=[live['ControlGroup']])
    simvs = [dict(pid=20+i, exe=image['simv'], argv=['simv'], cwd=str(s.ARITH / 'replay/tests/case/work'),
                  cgroups=[live['ControlGroup']]) for i in range(4)]
    def gate(n=missing, a=missing, processes=None, nfpass=True, apass=True, jobs=4):
        return s.decide(n, a, processes or [], jobs, nfpass, apass, image)
    assert gate()['total_reserved_max_jobs'] == 4
    assert gate(a=live, processes=[main_process, *simvs])['total_reserved_max_jobs'] == 8
    reject('GC_missing_NF2_evidence', lambda: gate(nfpass=False))
    reject('GC_missing_arithmetic_evidence', lambda: gate(apass=False))
    reject('unknown_active_NF2', lambda: gate(n={**missing, 'ActiveState': 'active', 'MainPID': '42'}))
    reject('unknown_active_arithmetic', lambda: gate(a={**missing, 'ActiveState': 'active', 'MainPID': '42'}))
    reject('live_NF2', lambda: gate(n={**live, 'ControlGroup': '/nf2'}))
    reject('failed_NF2_unit', lambda: gate(n={**missing, 'LoadState': 'loaded', 'ActiveState': 'failed'}))
    nf_owned = dict(pid=90, exe='/usr/bin/python3', argv=[str(s.NF2.parent / 'vcs_adapter.py')],
                    cwd='/tmp', cgroups=['/unrelated'])
    reject('GC_NF2_owned_non_simv', lambda: gate(processes=[nf_owned]))
    nf_owned2 = {**nf_owned, 'argv': [], 'cgroups': ['/user.slice/' + s.NF2_UNIT]}
    reject('GC_NF2_cgroup_owner', lambda: gate(processes=[nf_owned2]))
    reject('GC_arithmetic_owner', lambda: gate(processes=[main_process]))
    reject('GC_alien_simv', lambda: gate(processes=simvs[:1]))
    reject('live_alien_simv', lambda: gate(a=live, processes=[main_process, {**simvs[0], 'cgroups': ['/alien']}]))
    reject('cgroup_substring_spoof', lambda: gate(a=live, processes=[main_process,
           {**simvs[0], 'cgroups': [live['ControlGroup'] + '-spoof']}]))
    reject('wrong_simv_identity', lambda: gate(a=live, processes=[main_process, {**simvs[0], 'exe': '/other/simv'}]))
    reject('wrong_simv_run_owner', lambda: gate(a=live, processes=[main_process, {**simvs[0], 'cwd': '/alien'}]))
    reject('wrong_arithmetic_main', lambda: gate(a=live, processes=[{**main_process, 'argv': ['alien']}, *simvs]))
    reject('missing_arithmetic_main', lambda: gate(a=live, processes=simvs))
    reject('five_actual_simv', lambda: gate(a=live, processes=[main_process, *simvs, {**simvs[0], 'pid': 99}]))
    reject('five_reserved_NF7', lambda: gate(jobs=5))
    reject('no_authorization', lambda: s.worker(False, None, 4))
    reject('unknown_unit_name', lambda: s.unit_state('ara-unreviewed.service'))
    output = 'LoadState=not-found\nActiveState=inactive\nMainPID=0\nControlGroup=\nResult=success\n'
    with mock.patch.object(s.subprocess, 'check_output', return_value=output):
        assert s.unit_state(s.NF2_UNIT)['LoadState'] == 'not-found'
    with mock.patch.object(s.subprocess, 'check_output', return_value=output.replace('inactive', 'active')):
        reject('systemctl_unknown_active', lambda: s.unit_state(s.NF2_UNIT))

    # Real temporary JSON/hash files exercise terminal semantics, not just booleans.
    with tempfile.TemporaryDirectory(prefix='gc02-host-', dir=s.HERE) as tmp:
        root = Path(tmp)
        nf = root / 'nf2'
        d = nf / 'run/tests/nf2_segment4'
        d.mkdir(parents=True)
        s.save(d / 'input.elf', {'host_dummy_not_executable': True})
        elf = s.sha(d / 'input.elf')
        s.save(d / 'inputs.json', dict(binary={'sha256': elf},
                                     simv={'path': image['simv'], 'image_sha256': image['files']}))
        s.save(d / 'commit_trace.csv', {'host_dummy_csv': 'x' * 200})
        s.save(d / 'console.log', {})
        s.save(d / 'command.json', [])
        s.save(nf / 'run/run.json', dict(status='COMPLETE', completed_at='terminal',
            simv=image['simv'], tests=['nf2_segment4'], status_counts={'PASS': 1}))
        summary = [dict(name='nf2_segment4', status='PASS', returncode=0)]
        s.save(nf / 'run/summary.json', summary)
        analysis = dict(status='NF2_CSV_ORACLE_PASS', cases=list(range(4)), checks=4133, checkpoints=[{}]*8)
        s.save(nf / 'csv_analysis.json', analysis)
        complete = dict(status='CANDIDATE02_NF2_FOUR_PASS', returncode=0,
            image_json_sha256=s.old.IMAGE_SHA, soc_elf_sha256=elf,
            analysis_sha256=s.sha(nf / 'csv_analysis.json'), summary=summary)
        s.save(nf / 'complete.json', complete)
        s.save(nf / 'preflight.json', {'pins': {}})
        s.save(nf / 'worker.json', {})
        def replace(path, data):
            path.unlink()
            s.save(path, data)
        with mock.patch.object(s, 'NF2', nf), mock.patch.object(s, 'NF2_ELF', elf):
            evidence = s.nf2_evidence(image)
            s.old.verify(evidence)
            for key, value in [('status', 'FAIL'), ('returncode', 1), ('image_json_sha256', 'changed'),
                               ('soc_elf_sha256', 'changed'), ('analysis_sha256', 'changed')]:
                replace(nf / 'complete.json', {**complete, key: value})
                reject('GC_terminal_' + key, lambda: s.nf2_evidence(image))
            replace(nf / 'complete.json', complete)
            (nf / 'complete.json').unlink()
            reject('GC_no_complete_file', lambda: s.nf2_evidence(image))
            s.save(nf / 'complete.json', complete)
            replace(d / 'inputs.json', dict(binary={'sha256': elf}, simv={'path': image['simv'], 'image_sha256': {}}))
            reject('GC_input_image_changed', lambda: s.nf2_evidence(image))
            reject('GC_pinned_artifact_changed', lambda: s.old.verify(evidence))
            (d / 'commit_trace.csv').unlink()
            reject('GC_missing_pinned_CSV', lambda: s.old.verify(evidence))
        ar = root / 'arithmetic'
        ar.mkdir()
        cases = [dict(id=f'case{i}', sha256='elf') for i in range(38)]
        s.save(ar / 'plan.json', dict(cases=cases, pins={}, image_sha256=s.old.IMAGE_SHA,
                                     simv=image['simv'], jobs=4, stop_first_fail=True))
        ac = dict(status='PASS_38_CANDIDATE02', plan_sha256=s.sha(ar / 'plan.json'),
            image_sha256=s.old.IMAGE_SHA, results=[dict(name=x['id'], status='PASS') for x in cases])
        s.save(ar / 'complete.json', ac)
        with mock.patch.object(s, 'ARITH', ar), mock.patch.object(s, 'arithmetic_identity', return_value={}), \
             mock.patch.object(s, 'run_evidence', return_value={'mock_terminal_csv': 'hash'}):
            assert s.arithmetic_evidence(image)['mock_terminal_csv'] == 'hash'
            for key, value in [('status', 'NOT_PASS'), ('image_sha256', 'changed'),
                               ('plan_sha256', 'changed'), ('results', ac['results'][:37])]:
                replace(ar / 'complete.json', {**ac, key: value})
                reject('GC_arithmetic_' + key, lambda: s.arithmetic_evidence(image))
            (ar / 'complete.json').unlink()
            reject('GC_arithmetic_missing_complete', lambda: s.arithmetic_evidence(image))

    files = [Path(__file__), Path(s.__file__), Path(s.old.__file__)]
    s.save(s.HERE / 'gate02_host_tests.json', dict(status='HOST_GC_GATE_PASS_NOT_DUT',
        negative_rejections=rejected, positive=['GC_NF2_and_arithmetic_terminal_PASS',
        'GC_NF2_live_arithmetic_four_simv', 'full_NF2_terminal_identity_evidence',
        'full_arithmetic_terminal_membership'], VCS_started=False, pins=s.pins(files)))
    print('HOST_GC_GATE_PASS_NOT_DUT', len(rejected))


if __name__ == '__main__':
    main()
