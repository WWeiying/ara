#!/usr/bin/env python3
"""Collect per-lane packet/RCE-writeback overlap from completed simulation logs."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('regression', type=Path)
    parser.add_argument('--apps', nargs='+', help='Explicit partial scope of completed tests')
    parser.add_argument('--require-bypass-field', action='store_true', help='Require the new header-bypass observer counter on every lane')
    parser.add_argument('--require-normal-fields', action='store_true', help='Require ordinary result-drain overlap counters on every lane')
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    directory = args.regression.resolve()
    manifest = json.loads((directory/'manifest.json').read_text())
    if not args.apps:
        assert manifest['state'] == 'COMPLETE'
        assert len(manifest['tests']) == 50
    by_app = {test['app']:test for test in manifest['tests']}
    apps = args.apps or list(by_app)
    assert len(apps) == len(set(apps)) and set(apps) <= set(by_app)
    assert sha(Path(manifest['simulator'])) == manifest['simulator_sha256']
    expected = {(kind,lane) for kind in ('alu','mfpu_exact') for lane in range(4)}
    required = ('profile_cycles','packet_valid','packet_fire','headers','packet_stall','wb','wb_fire',
                'overlap','overlap_packet_fire','overlap_both_fire','different_owner','distinct_data','stall_wb_overlap')
    normal_fields = ('normal_drain_fire','normal_packet_both_fire','normal_packet_overlap','normal_distinct_data')
    counters = (*required, 'bypass_fire', *normal_fields)
    reports, problems, totals, by_kind = [], [], {key:0 for key in counters}, {}
    for app in apps:
        assert by_app[app]['pass'], app
        assert sha(directory/'inputs'/app) == by_app[app]['elf_sha256'], app
        log = directory/app/'stdout.log'
        text = log.read_text()
        assert 'Core Test *** SUCCESS *** (tohost = 0)' in text and '$finish at simulation time' in text, app
        assert 'PACKET_WB_PROFILE_FAIL' not in text, app
        summaries = []
        for line in text.splitlines():
            if not line.startswith('PACKET_WB_PROFILE_SUMMARY '):
                continue
            fields = dict(re.findall(r'(\w+)=([^\s]+)',line))
            required_fields = ('kind','lane',*required,*(('bypass_fire',) if args.require_bypass_field else ()),
                               *(normal_fields if args.require_normal_fields else ()))
            missing = sorted(set(required_fields)-set(fields))
            if missing:
                problems.append({'app':app,'missing_summary_fields':missing,'line':line})
                continue
            entry = {'kind':fields['kind'],'lane':int(fields['lane']),
                     **{key:int(fields[key]) for key in required},
                     'bypass_fire':int(fields.get('bypass_fire','0')),
                     'bypass_fire_reported':'bypass_fire' in fields,
                     **{key:int(fields.get(key,'0')) for key in normal_fields},
                     'normal_fields_reported':set(normal_fields)<=set(fields),'line':line}
            if not (entry['overlap_both_fire'] <= entry['overlap_packet_fire'] <= entry['overlap'] and
                    entry['overlap_both_fire'] <= entry['wb_fire'] and
                    entry['overlap_packet_fire'] <= entry['packet_fire'] and
                    entry['different_owner'] == entry['overlap'] and
                    entry['distinct_data'] <= entry['overlap'] and
                    entry['stall_wb_overlap'] <= entry['overlap'] and
                    entry['bypass_fire'] <= entry['headers'] <= entry['packet_fire'] and
                    entry['normal_packet_both_fire'] <= entry['normal_packet_overlap'] <= entry['packet_valid'] and
                    entry['normal_packet_both_fire'] <= min(entry['normal_drain_fire'],entry['packet_fire']) and
                    entry['normal_distinct_data'] <= entry['normal_packet_overlap']):
                problems.append({'app':app,'invalid_counter_relationships':entry})
            summaries.append(entry)
            kind_totals = by_kind.setdefault(entry['kind'],{key:0 for key in counters})
            for key in counters:
                totals[key] += entry[key]
                kind_totals[key] += entry[key]
        actual = {(entry['kind'],entry['lane']) for entry in summaries}
        if len(summaries)!=8 or actual!=expected:
            problems.append({'app':app,'summary_count':len(summaries),
                             'missing_kind_lanes':sorted(expected-actual),
                             'additional_kind_lanes':sorted(actual-expected)})
        reports.append({'app':app,'elf_sha256':by_app[app]['elf_sha256'],
                        'stdout_sha256':sha(log),'summaries':summaries})
    coverage = {key:totals[key]>0 for key in ('overlap_packet_fire','overlap_both_fire',
                                               'different_owner','distinct_data','packet_stall','stall_wb_overlap','bypass_fire',
                                               *normal_fields)}
    report = {'scope':'selected completed tests only' if args.apps else 'complete50-test suite',
        'test_count':len(apps),'simulator':manifest['simulator'],'simulator_sha256':manifest['simulator_sha256'],
        'valid':not problems,'problems':problems,'coverage_observed':coverage,
        'bypass_counter_required':args.require_bypass_field,
        'normal_counter_fields_required':args.require_normal_fields,
        'summaries_with_bypass_field':sum(entry['bypass_fire_reported'] for test in reports for entry in test['summaries']),
        'summaries_with_normal_fields':sum(entry['normal_fields_reported'] for test in reports for entry in test['summaries']),
        'optional_coverage_available':{
            'bypass_fire':all(entry['bypass_fire_reported'] for test in reports for entry in test['summaries']),
            'normal_fields':all(entry['normal_fields_reported'] for test in reports for entry in test['summaries'])},
        'totals':totals,
        'totals_by_kind':by_kind,'tests':reports,
        'interpretation':'Counter cycles are instrumentation only, excluded from benchmark cycles. Zero coverage is reported without claiming the mechanism was exercised. Optional fields absent from older observers are explicitly unavailable.'}
    assert not args.out.exists(), 'Preserve existing profile evidence'
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({key:report[key] for key in ('scope','test_count','valid','problems','coverage_observed','totals_by_kind')},indent=2))
    raise SystemExit(0 if not problems else 1)


if __name__ == '__main__':
    main()
