#!/usr/bin/env python3
"""Summarize completed, frozen audit runs; do not infer speedup from stall sums."""
import argparse
import hashlib
import json
from pathlib import Path
import re

EVENTS = {
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
    tests = {}
    for test in data['tests']:
        folder = directory/test['app']
        log = folder/'stdout.log'
        text = log.read_text(errors='replace')
        item = {'pass': test['pass'], 'elf_sha256': test['elf_sha256'],
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
    a=p.parse_args()
    if a.out.exists():
        p.error('choose a new output file to preserve evidence')
    full,control=read_suite(a.full),read_suite(a.control)
    pairs={}
    for app in sorted(full['tests'].keys() & control['tests'].keys()):
        f,c=full['tests'][app],control['tests'][app]
        if f['elf_sha256']!=c['elf_sha256']:
            raise ValueError(f'ELF mismatch: {app}')
        pairs[app]={'both_pass':f['pass'] and c['pass'],'elf_sha256':f['elf_sha256'],
                    'full_windows':f['measured_window_cycles'],
                    'control_windows':c['measured_window_cycles'],
                    'full_software_cycles':f['software_cycles'],
                    'control_software_cycles':c['software_cycles']}
    result={'full_directory':str(a.full),'control_directory':str(a.control),
            'full':full,'control':control,'paired_tests':pairs,
            'method':'Read-only observer counters span the whole ELF and overlap. Do not add them or equate them to cycles saved. Existing TB measured windows and software cycles retain separate scopes. Only passing same-ELF pairs may support performance claims; build provenance must also be checked.'}
    a.out.write_text(json.dumps(result,indent=2)+'\n')
    print(f'{len(pairs)} same-ELF pairs, {sum(x["both_pass"] for x in pairs.values())} both passed')


if __name__=='__main__':
    main()
