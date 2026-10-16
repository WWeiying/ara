"""Generate a guest-local runner and parse its bounded, identified protocol.

This does not upload files, own a serial port, or restart the board. The board
adapter must still preserve a scene and diagnose lack of retirement on a stall.
"""
import argparse
import copy
import json
from pathlib import Path
import re
import secrets


def configuration_count(case, line):
    match = re.search(r'\bcases=(\d+)\b', line)
    if match is not None:
        return int(match[1])
    # The fixed single-scenario reproducers predate the matrix count protocol.
    if (case['name'].startswith('rvv_repro_') and
            case['pass_marker'] == 'RVV_REPRO_PASS' and
            line == 'RVV_REPRO_PASS errors=0'):
        return 1
    return None


def validate(manifest, run_id):
    if not re.fullmatch(r'[a-f0-9]{16,64}', run_id):
        raise ValueError('Invalid run ID')
    if not re.fullmatch(r'[a-f0-9]{64}', manifest['archive_sha256']):
        raise ValueError('Invalid archive hash')
    names = set()
    for case in manifest['cases']:
        name = case['name']
        if not re.fullmatch(r'[A-Za-z0-9_][A-Za-z0-9_.-]*', name) or name in names:
            raise ValueError('Unsafe or repeated case name')
        if not re.fullmatch(r'[a-f0-9]{64}', case['sha256']):
            raise ValueError('Invalid ELF hash')
        if not re.fullmatch(r'[A-Za-z0-9_]+', case['pass_marker']):
            raise ValueError('Invalid pass marker')
        names.add(name)


def script(manifest, run_id):
    validate(manifest, run_id)
    prefix = 'RVVB:' + run_id + ':'
    lines = ['#!/bin/sh', 'cd "$(dirname "$0")" || exit 2']
    for index, case in enumerate(manifest['cases']):
        name = case['name']
        key = f'{index}:{name}'
        lines += [
            f"printf '\\n{prefix}PREP:{key}\\n'",
            f'actual=$(sha256sum "./{name}") || {{',
            f"  printf '{prefix}ABORT:{key}:hash_read\\n'; exit 2; }}",
            'actual=${actual%% *}',
            f'[ "$actual" = "{case["sha256"]}" ] || {{',
            f"  printf '{prefix}ABORT:{key}:hash_mismatch\\n'; exit 2; }}",
            f'chmod +x "./{name}" || {{',
            f"  printf '{prefix}ABORT:{key}:chmod\\n'; exit 2; }}",
            f"printf '{prefix}START:{key}\\n'",
            f'"./{name}"', 'rc=$?',
            f"printf '\\n{prefix}END:{key}:%s\\n' \"$rc\"",
        ]
    lines += [f"printf '{prefix}DONE:{len(manifest['cases'])}\\n'", 'exit 0']
    return '\n'.join(lines) + '\n'


class Parser:
    """Incremental text parser; EOF never implies that a test completed."""

    def __init__(self, manifest, run_id):
        validate(manifest, run_id)
        self.manifest = copy.deepcopy(manifest)
        self.prefix = 'RVVB:' + run_id + ':'
        self.pending = ''
        self.phase = 'idle'
        self.index = 0
        self.report = dict(inputs=copy.deepcopy(manifest), results=[],
                           rtl_modified=False, board_reset=False,
                           state='awaiting_guest_batch', run_id=run_id)

    def feed(self, text):
        self.pending += text
        while '\n' in self.pending:
            line, self.pending = self.pending.split('\n', 1)
            self.line(line.rstrip('\r'))

    def line(self, line):
        if not line.startswith(self.prefix):
            if self.phase == 'running':
                self.report['results'][-1]['output'] += line + '\n'
            return
        parts = line[len(self.prefix):].split(':')
        kind = parts[0]
        if kind == 'DONE':
            if (parts != ['DONE', str(len(self.manifest['cases']))] or
                    self.phase != 'idle' or self.index != len(self.manifest['cases'])):
                raise ValueError('Premature or malformed DONE')
            self.phase = 'done'
            self.report['state'] = 'all_cases_finished_review_results'
            return
        if self.index >= len(self.manifest['cases']):
            raise ValueError('Unexpected protocol after final case')
        case = self.manifest['cases'][self.index]
        if len(parts) < 3 or parts[1:3] != [str(self.index), case['name']]:
            raise ValueError('Case identity or order mismatch')
        if kind == 'PREP' and len(parts) == 3 and self.phase == 'idle':
            self.phase = 'preparing'
            self.report['state'] = 'preparing_guest_case'
        elif kind == 'ABORT' and len(parts) == 4 and self.phase == 'preparing':
            if parts[3] not in ('hash_read', 'hash_mismatch', 'chmod'):
                raise ValueError('Unknown preparation failure')
            self.phase = 'aborted'
            self.report['state'] = 'preparation_failed'
            self.report['error'] = dict(name=case['name'], reason=parts[3])
        elif kind == 'START' and len(parts) == 3 and self.phase == 'preparing':
            self.phase = 'running'
            self.report['state'] = 'running_guest_case'
            self.report['results'].append(dict(name=case['name'], status='running',
                                               output=''))
        elif kind == 'END' and len(parts) == 4 and self.phase == 'running':
            if not re.fullmatch(r'\d{1,3}', parts[3]) or int(parts[3]) > 255:
                raise ValueError('Invalid shell exit status')
            result = self.report['results'][-1]
            result['exit_code'] = int(parts[3])
            markers = [s for s in result['output'].splitlines()
                       if s.startswith(case['pass_marker'])]
            passed = (result['exit_code'] == 0 and len(markers) == 1 and
                      configuration_count(case, markers[0]) is not None)
            result['status'] = 'passed' if passed else 'failed'
            self.index += 1
            self.phase = 'idle'
            self.report['state'] = 'between_guest_cases'
        else:
            raise ValueError('Unexpected protocol transition')


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('manifest', type=Path)
    cli.add_argument('output', type=Path)
    cli.add_argument('--run-id', default=None)
    args = cli.parse_args()
    manifest = json.loads(args.manifest.read_text())
    run_id = args.run_id or secrets.token_hex(16)
    content = script(manifest, run_id)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output/'batch.sh').write_text(content)
    (args.output/'protocol.json').write_text(json.dumps(dict(
        run_id=run_id, inputs=manifest, board_task_started=False,
        rtl_modified=False), indent=2) + '\n')


if __name__ == '__main__':
    main()
