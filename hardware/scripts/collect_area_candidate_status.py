#!/usr/bin/env python3
"""Index current candidate evidence, retaining failures and cycle regressions.

This does not approve a candidate or replace the strict per-run collectors.
Pending manifests are observations, not proof that their processes are live.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
from run_reduction_audit import classify


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def suite(directory):
    result={'directory':str(directory),'state':'pending','sides':{}}
    reports=[]
    for mode in ['baseline','scalar']:
        path=directory/mode/'regression/manifest.json'
        if not path.exists():
            result['sides'][mode]={'state':'manifest_not_written'}
            continue
        report=json.loads(path.read_text());reports.append(report)
        result['sides'][mode]={'state':report['state'],'recorded_tests':len(report['tests']),
                              'failures':[t['app'] for t in report['tests'] if not t['pass']],
                              'manifest_sha256':sha(path)}
    if len(reports)!=2 or any(r['state']!='COMPLETE' for r in reports):
        return result
    for mode,report in zip(['baseline','scalar'],reports):
        assert sha(Path(report['simulator']))==report['simulator_sha256']
        expected=set(report['expected_apps'])
        assert len(expected)==len(report['tests']) and expected=={t['app'] for t in report['tests']}
        for test in report['tests']:
            assert sha(directory/mode/'regression/inputs'/test['app'])==test['elf_sha256']
            checked=dict(test)
            classify(checked,(directory/mode/'regression'/test['app']/'stdout.log').read_text())
            assert checked['pass']==test['pass'],'Recorded status differs from actual log'
    assert set(reports[0]['expected_apps'])==set(reports[1]['expected_apps'])
    left={t['app']:t for t in reports[0]['tests']}
    assert all(t['elf_sha256']==left[t['app']]['elf_sha256'] for t in reports[1]['tests'])
    result['state']='functional_pass' if all(t['pass'] for r in reports for t in r['tests']) else 'functional_failure'
    comparison=directory/'comparison.json'
    if not comparison.exists():
        result['performance']='strict_comparison_missing'
        return result
    data=json.loads(comparison.read_text())
    assert data['complete_suite'] and data['expected_test_count']==len(left)
    assert {t['app'] for t in data['tests']}==set(left)
    changes=[];windows=0
    for test in data['tests']:
        before,after=test['baseline_cycles'],test['scalar_cycles']
        assert len(before)==len(after)
        windows+=len(before)
        for index,(a,b) in enumerate(zip(before,after)):
            assert a>0 and b>0
            if a!=b:
                changes.append({'app':test['app'],'window':index,'baseline':a,'candidate':b,
                                'cycle_change_percent':100*(b/a-1)})
    result.update(comparison_sha256=sha(comparison),performance_windows=windows,
                  strict_no_regression=data['all_pass'],changed_windows=changes,
                  worst_window_slowdown_percent=max([0]+[c['cycle_change_percent'] for c in changes]),
                  all_finish_times_equal=all(t['finish_time_ticks'][0]==t['finish_time_ticks'][1] for t in data['tests']))
    return result


def area(directory):
    result={'directory':str(directory),'state':'pending'}
    manifest=directory/'manifest.json'
    if manifest.exists():
        result['completed_modes']=json.loads(manifest.read_text()).get('results',{})
        if any(not item.get('complete') for item in result['completed_modes'].values()):
            result['state']='tool_failure'
    partial=directory/'root_pair_evidence.json'
    if partial.exists():
        result['partial_evidence']=json.loads(partial.read_text())
    comparison=directory/'comparison.json'
    if comparison.exists():
        result.update(state='collected',comparison_sha256=sha(comparison),
                      evidence=json.loads(comparison.read_text()))
    return result


def main():
    root=Path(__file__).resolve().parents[2]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=root/'hardware/docs/reduction_area_candidate_status.json')
    args=parser.parse_args()
    definitions=[
      ('root_cache','root_only_cache_full_v1','requester_root_cache_ppa_v1'),
      ('legacy_fp_stream_prune','prune_fp_stream_full_v1','vmfpu_stream_ppa_v1'),
      ('compact_exact_segments','exact_compact_segments_soc_v1','exact_compact_segments_ppa_v1'),
      ('shared_completion','shared_completion_soc_v1','shared_completion_ppa_v1'),
      ('independent_ordered_mask','ordered_mask_decouple_soc_v1',None),
      ('arithmetic_forward_only','arithmetic_forward_soc_v2','requester_arithmetic_ppa_v1'),
      ('context_issue_cut','context_issue_cut_soc_v1',None)]
    result={'updated_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'scope':'Evidence index; local area differences are not additive integrated savings',
            'integrated_paired_area':'unverified','integrated_timing_closure':'unverified',
            'candidates':{}}
    for name,tests,ppa in definitions:
        record={'simulation':suite(root/'hardware/build'/tests)}
        if ppa:record['local_area']=area(root/'hardware/build'/ppa)
        result['candidates'][name]=record
    result['candidates']['arithmetic_forward_only']['expanded_simulation']=suite(root/'hardware/build/arithmetic_forward_full_v1')
    result['combined_suite']=suite(root/'hardware/build/shared_completion_full_v1')
    result['retained_failures']={
      'arithmetic_forward_soc_v1':suite(root/'hardware/build/arithmetic_forward_soc_v1')}
    exact=root/'hardware/build/exact_backend_tradeoff_v3/comparison.json'
    if exact.exists():
        data=json.loads(exact.read_text())
        assert data['complete'] and len(data['tests'])==72
        result['exact_family']={'comparison':str(exact),'sha256':sha(exact),
          'representation_cycles_equal':all(t['cycles']['full']==t['cycles']['banked'] for t in data['tests']),
          'limits':data['limits']}
    args.out.write_text(json.dumps(result,indent=2)+'\n')
    for name,record in result['candidates'].items():
        s=record['simulation']
        print(name,s['state'],'windows='+str(s.get('performance_windows','pending')),
              'max_slowdown_percent='+str(s.get('worst_window_slowdown_percent','pending')),
              'local_area='+record.get('local_area',{}).get('state','not_measured'))


if __name__=='__main__':
    main()
