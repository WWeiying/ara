#!/usr/bin/env python3
"""Read-only acceptance of the terminal six-partition alias campaign."""
import argparse
import hashlib
import json
from pathlib import Path
import re

PROGRAMS_SHA256 = 'daf65942945329b9d2ee3a846ed9f4674de05c32feead6c3257e894ccb43a397'
IMAGE_SHA256 = '384515b7365200942d08fc7b34275d10eee676cf6ce0574935043020e87c7810'
COMPLETE = 'PASS_3_TUPLES_3_PREFIXES_NOT_FULL_MATRICES'
SHAPES = (('e8_m4', 8, 98), ('e8_m8', 8, 66), ('e16_m8', 16, 98))
FAIL = re.compile(
    r'RVV_MASK_(?:FAIL|CAPACITY_FAIL)|BOARD_CASE_FAIL|'
    r'BOARD_REPLAY_[A-Z_]*(?:FAIL|TRAP|MISMATCH)|'
    r'Core Test \*\*\* FAILED \*\*\*|'
    r'\bUVM_FATAL\b(?![ \t]*:[ \t]*0\b)|\$fatal\b|\bFatal\s*:|'
    r'(?:Error|Fatal)[^\n]*(?:assertion|assert)[^\n]*fail|'
    r'^\s*(?:Index\s+\d+\s+)?(?:FAIL(?:ED|URE)?|FATAL)(?:\b|:)',
    re.IGNORECASE | re.MULTILINE,
)


class Rejected(ValueError):
    pass


class Incomplete(Rejected):
    pass


def require(condition, message):
    if not condition:
        raise Rejected(message)


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def console_check(text, name, sew, count):
    require(not FAIL.search(text), name + ': failure marker veto')
    lines = text.splitlines()
    expected = f'RVV_MASK_PASS sew={sew} cases={count} errors=0'
    require([s for s in lines if s.startswith('RVV_MASK_PASS')] == [expected],
            name + ': incorrect or ambiguous oracle count/result')
    for prefix, marker in (('BOARD_CASE_BEGIN', 'BOARD_CASE_BEGIN ' + name),
                           ('BOARD_CASE_PASS', 'BOARD_CASE_PASS ' + name),
                           ('BOARD_REPLAY_PASS', 'BOARD_REPLAY_PASS')):
        require([s for s in lines if s.startswith(prefix)] == [marker],
                name + ': missing/ambiguous ' + prefix)
    require(lines.count('RVV_MASK_TRIAL vl=512 vstart=256') == 1,
            name + ': historical tuple marker missing or duplicated')
    core = [s for s in lines if s.startswith('Core Test *** SUCCESS ***')]
    require(core == ['Core Test *** SUCCESS *** (tohost = 0)'],
            name + ': missing successful firmware exit')


def check(root, *, programs_sha256=PROGRAMS_SHA256, image_sha256=IMAGE_SHA256):
    root = Path(root).resolve()
    if not (root / 'complete.json').is_file():
        raise Incomplete('Top-level terminal report absent; do not poll')
    terminal = read(root / 'complete.json')
    require(terminal['status'] == COMPLETE, 'Top-level campaign did not pass all six')
    require(terminal['finished'] > 0, 'Missing terminal time')
    # Check terminality before inspecting any test console or private input.
    runs = {}
    for stage in ('tuple', 'prefix'):
        path = root / stage / 'run.json'
        if not path.is_file():
            raise Incomplete(stage + ': runner metadata absent')
        runs[stage] = read(path)
        if runs[stage].get('status') != 'COMPLETE' or not runs[stage].get('completed_at'):
            raise Incomplete(stage + ': runner not COMPLETE')

    plan_path = root / 'plan.json'
    plan = read(plan_path)
    require(terminal['plan_sha256'] == sha(plan_path), 'Terminal/plan identity mismatch')
    launch = read(root / 'launch.json')
    require(launch['returncode'] == 0 and launch['plan_sha256'] == sha(plan_path), 'Launch/plan mismatch')
    require(plan['jobs'] == 1 and plan['phases'] == ['tuple', 'prefix'], 'Unexpected stage configuration')
    require(plan['prefix_requires_all_three_tuples_PASS'] is True, 'Missing tuple success gate')
    for path, digest in plan['pins'].items():
        require(sha(path) == digest, 'Pinned input drift: ' + path)
    programs_path = Path(plan['programs']) / 'programs.json'
    require(sha(programs_path) == programs_sha256, 'Unreviewed programs manifest')
    programs = read(programs_path)
    require(programs['backend'] == 'vcs-soc', 'Wrong backend')
    prepared = Path(programs['prepared'])
    require(sha(prepared / 'provenance.json') == programs['provenance_sha256'], 'Prepared provenance drift')
    for relative, digest in read(prepared / 'provenance.json')['files'].items():
        require(sha(prepared / relative) == digest, 'Prepared source drift: ' + relative)
    image_path = Path(plan['image']) / 'image.json'
    require(sha(image_path) == image_sha256, 'Unreviewed image ledger')
    image = read(image_path)
    require(plan['simv'] == image['simv'], 'Plan/image simv mismatch')
    for path, digest in image['files'].items():
        require(sha(path) == digest, 'Simulator image drift: ' + path)
    snapshot = Path(image['snapshot'])
    require(sha(snapshot / 'snapshot.json') == image['snapshot_sha256'], 'Snapshot identity drift')

    expected_all = {f'rvv_masks_alias_restart_{shape}_{stage}'
                    for stage in ('tuple', 'prefix') for shape, _, _ in SHAPES}
    require(set(programs['programs']) == expected_all, 'ELF manifest membership differs')
    require([s['stage'] for s in terminal['stages']] == ['tuple', 'prefix'], 'Terminal stage membership differs')
    accepted = []
    for stage, recorded in zip(('tuple', 'prefix'), terminal['stages']):
        expected = [f'rvv_masks_alias_restart_{shape}_{stage}' for shape, _, _ in SHAPES]
        run = runs[stage]
        require(run['tests'] == expected and run['status_counts'] == {'PASS': 3}, stage + ': runner membership/status differs')
        require(run['simv'] == image['simv'], stage + ': wrong actual runner image')
        summary = read(root / stage / 'summary.json')
        require(len(summary) == 3 and [r['name'] for r in summary] == expected, stage + ': duplicate/missing/extra results')
        require(recorded['passed'] is True and recorded['returncode'] == 0 and recorded['results'] == summary,
                stage + ': terminal/summary disagreement')
        for result, (_, sew, prefix_count) in zip(summary, SHAPES):
            name = result['name']
            count = 1 if stage == 'tuple' else prefix_count
            require(result['status'] == 'PASS' and result['returncode'] == 0 and not result['reason'],
                    name + ': unsuccessful runner exit/result')
            artifact = root / stage / 'tests' / name
            require(result['artifact_dir'] == str(artifact), name + ': result from wrong output')
            entry = programs['programs'][name]
            require(entry['configurations'] == count and entry['cases'] == [name], name + ': wrong manifest case count')
            require(sha(entry['path']) == entry['sha256'], name + ': source ELF drift')
            private = artifact / 'input.elf'
            require(sha(private) == entry['sha256'], name + ': private ELF differs from reviewed program')
            inputs = read(artifact / 'inputs.json')
            require(inputs['binary'] == dict(source=entry['path'], path=str(private), sha256=entry['sha256']),
                    name + ': input provenance differs')
            require(inputs['simv'] == dict(path=image['simv'], image_sha256=image['files']), name + ': input image differs')
            command = read(artifact / 'command.json')
            args = command['command']
            require(args[0] == image['simv'] and command['cwd'] == str(artifact / 'work'), name + ': command identity differs')
            for key, value in (('+PRELOAD=', str(private)), ('+TESTCASE=', name)):
                require([a for a in args if a.startswith(key)] == [key + value], name + ': wrong command ' + key)
            console_check((artifact / 'console.log').read_text(errors='strict'), name, sew, count)
            accepted.append(dict(name=name, configurations=count, input_sha256=entry['sha256'],
                                 console_sha256=sha(artifact / 'console.log')))
    return dict(status='ACCEPTED_6_BOUNDED_PARTITIONS_NOT_FULL_MATRICES', results=accepted,
                plan_sha256=sha(plan_path), read_only=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    try:
        report, code = check(args.output), 0
    except Incomplete as error:
        report, code = dict(status='INCOMPLETE_NOT_ACCEPTED', reason=str(error)), 2
    except (Rejected, OSError, KeyError, TypeError, ValueError, IndexError) as error:
        report, code = dict(status='REJECTED', reason=str(error)), 1
    print(json.dumps(report, indent=2))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
