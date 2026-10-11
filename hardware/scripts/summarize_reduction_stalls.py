#!/usr/bin/env python3
"""Summarize completed, frozen audit runs; do not infer speedup from stall sums."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from run_reduction_audit import classify

EVENTS = {
    'parallel_retire': ['word_and_sldu'],
    'word_credit': ['reserve','retire','admission_wait','extra_reserved',
                    'word_admitted_with_sldu_full'],
    'shared_credit': ['full','credit_held','word_held','slide_held',
                      'reservations','sole_queue_limit'],
    'shared_completion': ['completion_collision','commit_owner_wait','vrf_wait',
                          'receive_full','exact_wins_word'],
    'seed_lookahead': ['background_cycles','background_completions','prepared_promotions'],
    'mfpu_restart': ['nonempty_restart','older_normal_drain','older_normal_retire','local_compute_overlap'],
    'fp_feedback': ['forward_fire','forward_backpressure'],
    'seed_dispatch': ['late_candidate','ordinary_candidate','ordinary_same_vfu_candidate','external_candidate'],
    'hetero_compute': ['different_vl','different_sew','different_mask'],
    'completion_wait': ['head_seed_wait','ready_source_behind_seed_wait',
                        'ready_source_behind_output_wait','ready_source_behind_partial_wait',
                        'ready_source_and_seed_behind_wait','final_fp_lane_return'],
    'queue_valu': ['recycles','full_recycles','full_recycle_compute','full_recycle_narrow'],
    'queue_vmfpu': ['recycles','full_recycles','full_recycle_compute','full_recycle_narrow'],
    'exact_egress': ['pending','handoffs','egress_releases','next_frame_beats_before_retire'],
    'word_turnaround': ['pop_push','full_pop_push','last_partial_start','ready_successor_start'],
    'word': ['commands','idle_occupied','merge','fold','seed','hold','fp_wait',
             'completions','startup_ready','partial_wait','seed_wait','output_wait',
             'empty_compute','inactive_merge_lane','fp_feedback_boundary','full_pop'],
    'valu': ['pending','local_compute','mixed_normal_fire','rce_head_queue_full',
             'ready_normal_blocked_by_queue','full_pop','handoff','handoff_wait'],
    'vmfpu': ['rce_commit_head','younger_normal_at_issue','handoff','rce_vrf_wait',
              'rce_head_queue_full','result_cannot_enqueue','full_pop','next_reduction_queue_wait'],
    'sldu': ['exact_receive','exact_wait_result','header_wait','limb_fire',
             'seed_wait','seed_bind','local_complete','exact_retire_wait'],
}


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_suite(directory):
    manifest = directory/'manifest.json'
    data = json.loads(manifest.read_text())
    if sha(Path(data['simulator'])) != data['simulator_sha256']:
        raise ValueError(f'simulator changed: {directory}')
    tests = {}
    for test in data['tests']:
        folder = directory/test['app']
        log = folder/'stdout.log'
        text = log.read_text(errors='replace')
        if sha(directory/'inputs'/test['app']) != test['elf_sha256']:
            raise ValueError(f'frozen ELF changed: {folder}')
        checked = dict(test)
        classify(checked, text)
        if checked['pass'] != test['pass']:
            raise ValueError(f'log no longer agrees with manifest: {folder}')
        item = {'pass': checked['pass'], 'elf_sha256': test['elf_sha256'],
                'log_sha256': sha(log), 'observer': {}}
        for kind,lane,event,count in re.findall(
                r'\[RCE_STALL\] kind=(\w+) lane=(\d+) event=(\d+) cycles=(\d+)',text):
            key = EVENTS[kind][int(event)]
            counters = item['observer'].setdefault(kind,{}).setdefault(lane,{})
            if key in counters:
                raise ValueError(f'duplicate observer {test["app"]} {kind} {lane} {key}')
            counters[key] = int(count)
        # These are measured windows from the existing TB, not the observer's
        # whole-program counters. Keep every window, in order.
        item['measured_window_cycles'] = [int(x) for x in re.findall(
            r'\[PERF\]\s+total_cycles\s*:\s*(\d+)',text)]
        item['software_cycles'] = [int(x) for x in re.findall(
            r'RCE .*? PASS:.*?\bcycles=(\d+)',text)]
        # Keep labels: a program can contain several differently scoped windows.
        item['labelled_software_cycles'] = [
            {'label': label.strip(), 'cycles': int(cycles)}
            for label, cycles in re.findall(
                r'^((?:EMPTY|FP_LATE|ORDINARY_SEED)\b.*?)\s+cycles=(\d+)',text,re.M)]
        reports = list(folder.glob('perf_report_*.log'))
        if len(reports)>1:
            raise ValueError(f'ambiguous report {folder}')
        if reports:
            report = reports[0]
            item['last_window_report_sha256'] = sha(report)
            item['last_window_metrics'] = dict(re.findall(
                r'^\[PERF\]\s+([^:]+?)\s*:\s*(.*?)\s*$',report.read_text(),re.M))
        tests[test['app']] = item
    return {'manifest_sha256':sha(manifest),'simulator_sha256':data['simulator_sha256'],
            'tests':tests}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--full',required=True,type=Path)
    p.add_argument('--control',required=True,type=Path)
    p.add_argument('--out',required=True,type=Path)
    p.add_argument('--expected-full',type=Path,
                   help='JSON list of every required full-suite application')
    p.add_argument('--expected-control',type=Path,
                   help='JSON list of every required control-suite application')
    p.add_argument('--require-pass',action='store_true',
                   help='reject failed tests rather than only reporting them')
    a=p.parse_args()
    if a.out.exists():
        p.error('choose a new output file to preserve evidence')
    full,control=read_suite(a.full),read_suite(a.control)
    for name,suite,expected_path in [('full',full,a.expected_full),
                                     ('control',control,a.expected_control)]:
        if expected_path is not None:
            expected = set(json.loads(expected_path.read_text()))
            actual = set(suite['tests'])
            if actual != expected:
                raise ValueError(f'{name} suite incomplete or unexpected: '
                                 f'missing={sorted(expected-actual)} '
                                 f'extra={sorted(actual-expected)}')
        if a.require_pass:
            failed = [app for app,test in suite['tests'].items() if not test['pass']]
            if failed:
                raise ValueError(f'{name} failed tests: {failed}')
    pairs={}
    for app in sorted(full['tests'].keys() & control['tests'].keys()):
        f,c=full['tests'][app],control['tests'][app]
        if f['elf_sha256']!=c['elf_sha256']:
            raise ValueError(f'ELF mismatch: {app}')
        if f['pass'] and c['pass'] and [x['label'] for x in f['labelled_software_cycles']] != [x['label'] for x in c['labelled_software_cycles']]:
            raise ValueError(f'measurement window mismatch: {app}')
        pairs[app]={'both_pass':f['pass'] and c['pass'],'elf_sha256':f['elf_sha256'],
                    'full_windows':f['measured_window_cycles'],
                    'control_windows':c['measured_window_cycles'],
                    'full_software_cycles':f['software_cycles'],
                    'control_software_cycles':c['software_cycles'],
                    'full_labelled_cycles':f['labelled_software_cycles'],
                    'control_labelled_cycles':c['labelled_software_cycles']}
    result={'full_directory':str(a.full),'control_directory':str(a.control),
            'full':full,'control':control,'paired_tests':pairs,
            'method':'Read-only observer counters span the whole ELF and overlap. Do not add them or equate them to cycles saved. Existing TB measured windows and software cycles retain separate scopes. Only passing same-ELF pairs may support performance claims; build provenance must also be checked.'}
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(f'{len(pairs)} same-ELF pairs, {sum(x["both_pass"] for x in pairs.values())} both passed')


if __name__=='__main__':
    main()
