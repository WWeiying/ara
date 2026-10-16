"""Serial context-length campaign on an already booted Qwen3 board."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

PASSAGE = ('The archive describes a village beside a river. Farmers grow rice and wheat. '
           'A bridge connects the market to a school. The library opens every morning.')
CASES = [
    ('arithmetic', 'Complete the equation: 12 + 7 =', 1, '', 16),
    ('context_medium', PASSAGE, 4, 'Which two crops do the farmers grow? Answer:', 8),
    ('context_long', PASSAGE, 16, 'Which two crops do the farmers grow? Answer:', 8),
]


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--start-index', type=int, default=0, choices=range(len(CASES)))
    p.add_argument('--output-name', default='context_campaign')
    a = p.parse_args()
    out = a.root / a.output_name
    out.mkdir(exist_ok=False)
    summary = {'state': 'running', 'cases': [], 'scope': 'completion and native coverage; semantic answers require review'}
    def save():
        (out / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    save()
    for name, prompt, repeat, suffix, tokens in CASES[a.start_index:]:
        summary['active_case'] = name
        save()
        args = [sys.executable, '-X', 'utf8', str(a.root / 'run_qwen3_context.py'),
                '--out', str(out / name), '--software', str(a.root / 'tools/software'),
                '--manifest', str(a.root / 'payloads/manifest.json'),
                '--skip-board-hash', '--qbs-akv', '--prompt', prompt,
                '--prompt-repeat', str(repeat), '--suffix', suffix, '--tokens', str(tokens)]
        print('START', name, flush=True)
        with (out / (name + '.log')).open('w', encoding='utf-8') as log:
            rc = subprocess.call(args, stdout=log, stderr=subprocess.STDOUT)
        report_path = out / name / 'report.json'
        report = json.loads(report_path.read_text()) if report_path.exists() else {'state': 'missing_report'}
        summary['cases'].append({'name': name, 'host_exit_code': rc, 'report': report})
        print('END', name, report['state'], flush=True)
        # Do not send another command if the previous guest may still be running.
        if report['state'] not in ('completed', 'failed') or 'exit_code' not in report:
            summary['state'] = 'stopped_guest_state_unknown'
            save()
            return 1
        save()
    summary['state'] = 'completed'
    summary['all_passed'] = all(c['report'].get('passed', False) for c in summary['cases'])
    summary.pop('active_case', None)
    save()
    return 0 if summary['all_passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
