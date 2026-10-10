"""Bounded point-only application of a parent-supplied EL to exact raw740.

prepare/verify are offline; run starts one DVE session only on explicit invocation.
Branch and Condition native point formats are supported; other directives HOLD.
"""
import argparse
from collections import Counter
import csv
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import dve_tool_identity as tools

HERE = Path(__file__).resolve().parent
HOOK = HERE / 'apply_points740.tcl'
EXPORT = HERE / 'export_dve_coverage.tcl'
SCRIPT = Path(__file__).resolve()
TEST = HERE / 'test_apply_points740.py'
# Only these two inputs have parent confirmation for this wave. Never discover
# candidate ELs from directories or automatically reuse earlier eight-group ELs.
APPROVED = {
    '3e2345b2bc906413c1baf65dd912a15faa70d55276e7c0cd772585a591bbca7f': 5808,
    'c11b89f8ae115a50c83bd409d57d003c768991ae589656c021c5209cdb9f44a8': 24,
}
QUOTED = r'"((?:\\[ -~]|[^"\\\n])*)"'
SCOPE = r'[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[[0-9]+\])?)*'


def require(value, message):
    if not value:
        raise ValueError(message)


def sha(path):
    return tools.seal_file(path)['sha256']


def write(path, value):
    with path.open('x', encoding='utf-8') as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')


def merge(*ledgers):
    result = {}
    for ledger in ledgers:
        for path, digest in ledger.items():
            require(re.fullmatch(r'[0-9a-f]{64}', digest), 'Invalid pin digest')
            require(path not in result or result[path] == digest, 'Conflicting input pin: ' + path)
            result[path] = digest
    return result


def check_pins(pins):
    for path, digest in pins.items():
        require(sha(path) == digest, 'Pin drift: ' + path)


def records(raw):
    """Exact native semantic multiset, ignoring annotations and serialization order.

    No scope-only directives, unsupported records, partial blocks or duplicate
    native identities are accepted. Checksums and signatures stay exact.
    """
    if raw == b'':
        return Counter()
    text = raw.decode('ascii')
    require(text.endswith('\n') and not re.search(r'[^\x0a\x20-\x7e]', text), 'Invalid native bytes')
    header = owner = kind = None
    count = 0
    result = []
    native_keys = set()
    for line in text.splitlines():
        if line == '':
            continue
        match = re.fullmatch(r'CHECKSUM: "([0-9]+) ([0-9]+)"', line)
        if match:
            require(header is None and (owner is None or count > 0), 'Incomplete/whole scope block')
            header, owner, count, kind = match.groups(), None, 0, None
            continue
        match = re.fullmatch(r'INSTANCE: ?(' + SCOPE + ')', line)
        if match:
            require(header is not None and owner is None, 'Instance without unique checksum')
            owner, header = (match[1], *header), None
            continue
        if re.fullmatch(r'ANNOTATION: ' + QUOTED, line):
            require(owner is not None, 'Annotation outside point block')
            continue
        branch = re.fullmatch(r'Branch ([0-9]+) "([0-9]+)" ' + QUOTED + r' \(([0-9]+)\) ' + QUOTED, line)
        condition = re.fullmatch(r'Condition ([0-9]+) "([0-9]+)" ' + QUOTED + r' \(([0-9]+) "([01]+)"\)', line)
        match = branch or condition
        require(match is not None and owner is not None, 'Unsupported/non-point native directive')
        metric = 'Branch' if branch else 'Condition'
        native, checksum, expression, selector, signature = match.groups()
        require(kind in (None, metric), 'Mixed metric block')
        kind = metric
        if condition:
            require(re.fullmatch(r'.+ [1-9][0-9]* -?[0-9]+', expression), 'Missing condition width/bit')
        key = (owner[0], metric, native, selector)
        require(key not in native_keys, 'Duplicate native point')
        native_keys.add(key)
        result.append((*owner, metric, native, checksum, expression, selector, signature))
        count += 1
    require(header is None and owner is not None and count > 0, 'Incomplete/whole scope tail')
    return Counter(result)


def table(path):
    with path.open(encoding='utf-8', newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == ['Name', 'Depth', 'Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch'],
                'Full raw CSV schema differs')
        rows = list(reader)
    stack, result = [], {}
    for row in rows:
        require(None not in row and all(isinstance(x, str) for x in row.values()), 'Malformed CSV row')
        require(re.fullmatch(r'0|[1-9][0-9]*', row['Depth']), 'Invalid hierarchy depth')
        depth = int(row['Depth'])
        require(depth <= len(stack) and row['Name'], 'Broken hierarchy')
        stack = stack[:depth] + [row['Name']]
        key = tuple(stack)
        require(key not in result, 'Duplicate hierarchy path')
        for field in ('Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch'):
            value = row[field]
            require(value == 'NA' or (re.fullmatch(r'[0-9]+\.[0-9]+%', value) and
                    0 <= float(value[:-1]) <= 100), 'Invalid coverage percentage')
        result[key] = row
    require(result, 'Empty full hierarchy')
    return result


def reviewed_inputs(els, reviews, review_seals):
    require(len(els) == len(set(els)) == len(APPROVED) and
            len(reviews) == len(set(reviews)) == len(review_seals) == len(APPROVED),
            'Exactly the two parent-confirmed groups and reviews required')
    digests = {str(el): sha(el) for el in els}
    require(set(digests.values()) == set(APPROVED), 'EL is not one of the two parent-confirmed inputs')
    ledgers = []; reviewed = set()
    for path, seal in zip(reviews, review_seals):
        require(sha(path) == seal, 'Review external seal differs')
        audit = json.loads(path.read_bytes())
        if audit.get('schema') == 'SIX_POLICY_FORMAL740_ELIGIBILITY_AUDIT_V1':
            require(audit['status'] == 'EXACT_SIX_POLICY_740_ELIGIBLE_NOT_APPLIED' and
                    audit['review']['tests'] == 740 and audit['review']['unique_targets'] == 5808 and
                    audit['review']['cross_target_protection_conflicts'] == 0, 'Six review is not740 eligible')
            pins = audit['evidence_pins']
        else:
            require(audit.get('schema') == 'MASK_STORE_SNAPSHOT_COND24_FORMAL740_READONLY_AUDIT_V1' and
                    audit['population'] == 740 and
                    audit['status'] == 'READONLY_MASK_STORE_COND24_REBIND740_PASS_NOT_APPLICATION',
                    'Snapshot review is not740 PASS')
            pins = audit['pins']
        matches = {digest for el, digest in digests.items() if pins.get(el) == digest}
        require(matches, 'Review does not bind a supplied approved EL')
        reviewed.update(matches)
        ledgers.append(merge(pins, {str(path): seal}))
    require(reviewed == set(APPROVED), 'Missing approved group review')
    payloads = []
    for el in els:
        payload = el.read_bytes()
        require(len(records(payload)) == APPROVED[digests[str(el)]], 'Approved group exact point count differs')
        payloads.append(payload)
    combined = b''.join(payloads)
    require(len(records(combined)) == sum(APPROVED.values()), 'Combined overlap/point count differs')
    return combined, merge(*ledgers, digests)


def prepare(output, raw_result, raw_seal, els, reviews, review_seals, timeout):
    require(not output.exists() and output.resolve() == output, 'Fresh canonical output required')
    require(timeout in (600, 900), 'Only 600/900 second budget')
    require(sha(raw_result) == raw_seal, 'Parent-provided raw seal differs')
    raw = json.loads(raw_result.read_bytes())
    require(raw['status'] == 'VERIFIED_RAW740_HISTORICAL_ONLY' and raw['tests'] == 740 and raw['waived'] is False,
            'Exact verified raw740 required')
    payload, review_pins = reviewed_inputs(els, reviews, review_seals)
    expected = records(payload)
    report = Path(raw['report'])
    names = ('inputs.txt', 'selected_tests.txt', 'summary.csv')
    require(all(str(report / n) in raw['pins'] for n in names), 'Raw identity/report lacks pins')
    inputs = (report / 'inputs.txt').read_text().splitlines()
    selected = (report / 'selected_tests.txt').read_text().splitlines()
    require(len(inputs) == len(set(inputs)) == 741 and len(selected) == len(set(selected)) == 740,
            'Exact740 population identity required')
    require(len(table(report / 'summary.csv')) == raw['rows'], 'Raw hierarchy incomplete')
    identity = tools.prepare(shutil.which('dve'), shutil.which('xvfb-run'))
    files = [raw_result, SCRIPT, TEST, HOOK, EXPORT, Path(tools.__file__).resolve(),
             Path('/usr/bin/timeout')]
    pins = merge(raw['pins'], review_pins, {str(p): sha(p) for p in files},
                 {x['path']: x['sha256'] for x in identity['files']})
    check_pins(pins)
    output.mkdir(parents=True)
    for name, value in (('inputs.txt', '\n'.join(inputs) + '\n'), ('points.el', payload.decode('ascii'))):
        write(output / name, value)
    pins = merge(pins, {str(output / n): sha(output / n) for n in ('inputs.txt', 'points.el')})
    config = dict(schema='POINT_ONLY_RAW740_V1', output=str(output), raw_result=str(raw_result),
        raw_seal=raw_seal, report=str(report), reviews=[str(p) for p in reviews], review_seals=review_seals,
        els=[str(p) for p in els], records=len(expected), selected_tests=selected, inputs=inputs,
        authorization_source='PARENT_AGENT_AUTHORIZATION_WITHIN_USER_GOAL',
        timeout=timeout, pins=pins, tool_identity=identity, automatic_retry=False,
        command=['/usr/bin/timeout', '--kill-after=10s', str(timeout) + 's'] + tools.launch_command(identity, EXPORT))
    write(output / 'config.json', config)
    print(json.dumps(dict(status='PREPARED_NO_DVE', output=str(output), seal=sha(output / 'config.json'),
                          records=len(expected), timeout=timeout)))


def verify(output, seal):
    require(sha(output / 'config.json') == seal, 'Config seal differs')
    c = json.loads((output / 'config.json').read_bytes())
    require(c['schema'] == 'POINT_ONLY_RAW740_V1' and c['output'] == str(output) and
            c['timeout'] in (600, 900) and c['automatic_retry'] is False, 'Run contract differs')
    check_pins(c['pins']); tools.revalidate(c['tool_identity'])
    payload, _ = reviewed_inputs([Path(x) for x in c['els']], [Path(x) for x in c['reviews']], c['review_seals'])
    require((output / 'points.el').read_bytes() == payload, 'Combined points differ from reviewed inputs')
    require(c['command'] == ['/usr/bin/timeout', '--kill-after=10s', str(c['timeout']) + 's'] +
            tools.launch_command(c['tool_identity'], EXPORT), 'Command differs')
    require(len(records((output / 'points.el').read_bytes())) == c['records'], 'Point population differs')
    return c


def inspect(c, output):
    terminal = json.loads((output / 'terminal.json').read_bytes())
    live = json.loads((output / 'live-identity.json').read_bytes())
    require(terminal['returncode'] == 0 and terminal['live_identity'] == live and
            live['executable_verified'] is True and live['executable'] == c['tool_identity']['executable'],
            'Actual terminal/executable identity unproven')
    expected = records((output / 'points.el').read_bytes())
    require(expected and len(expected) == c['records'], 'Approved points differ')
    for name in ('applied.el', 'reloaded.el'):
        require(records((output / name).read_bytes()) == expected, 'Exact EL semantics differ: ' + name)
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el', 'cleanup-empty.el'):
        require((output / name).read_bytes() == b'', 'Not global empty: ' + name)
    require((output / 'inputs.txt').read_text().splitlines() == c['inputs'] and
            (output / 'selected_tests.txt').read_text().splitlines() == c['selected_tests'], 'Actual740 membership differs')
    require(not (output / 'rejected_tests.txt').exists(), 'Rejected native tests')
    raw = table(Path(c['report']) / 'summary.csv')
    for name in ('raw.csv', 'reset.csv'):
        require(table(output / name) == raw, 'Full raw740/reset differs: ' + name)
    applied, reloaded = table(output / 'applied.csv'), table(output / 'reloaded.csv')
    require(applied == reloaded and set(applied) == set(raw), 'Applied/reloaded full hierarchy differs')
    logs = [output / 'run.log', output / 'DVEfiles/dve_gui.log']
    for path in (output / 'DVEfiles/dve_qtwarnings.log', output / 'diagnostics.txt'):
        require(not path.exists() or path.read_bytes().strip() == b'', 'Nonempty diagnostics: ' + str(path))
    for path in logs:
        text = path.read_text(encoding='utf-8')
        require(not re.search(r'(?i)warning|rejected|\berror\b|failed|fatal', text), 'DVE diagnostics: ' + str(path))
    gui = logs[1].read_text(encoding='utf-8').splitlines()
    require(gui.count('POINT740_APPLIED_RELOADED_RESET_DONE') == gui.count('DVE_COVERAGE_EXPORT_DONE') == 1,
            'Missing/duplicate terminal markers')
    require([x[len('DVE_SELECTED_TESTS: '):].split() for x in gui if x.startswith('DVE_SELECTED_TESTS: ')] ==
            [c['selected_tests']], 'Logged740 identity differs')
    check_pins(c['pins']); tools.revalidate(c['tool_identity'])
    return dict(status='POINT_ONLY_740_APPLIED_SAVE_RELOAD_RESET_PASS', population=740,
                records=len(expected), hierarchy_rows=len(raw), semantic_order_annotation_ignored=True,
                scope_exclusions=False, simulations_started=False)


def run(output, seal):
    c = verify(output, seal)
    write(output / 'execution.json', dict(command=c['command'], timeout=c['timeout'], launches=1))
    env = tools.controlled_environment(c['tool_identity'], os.environ)
    env.update(DVE_COVERAGE_OUTPUT=str(output), DVE_REVIEWED_WAIVERS=str(HOOK))
    process = None
    try:
        write(output / 'integrity-before.json', dict(status='PIN_PASS', pins=c['pins']))
        with (output / 'run.log').open('x') as log:
            process = subprocess.Popen(c['command'], cwd=output, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            start = tools.process_info(process.pid)['starttime']
            deadline, live = time.monotonic() + c['timeout'] + 20, None
            while process.poll() is None:
                if live is None:
                    for p in Path('/proc').iterdir():
                        if not p.name.isdigit():
                            continue
                        try:
                            if (p / 'exe').resolve(strict=True) == Path(c['tool_identity']['executable']):
                                live = tools.verify_live_executable(int(p.name), c['tool_identity'], process.pid, start)
                                write(output / 'live-identity.json', live)
                                break
                        except (OSError, ValueError):
                            continue
                require(time.monotonic() < deadline, 'Bounded DVE timeout')
                time.sleep(1)
            require(process.returncode == 0 and live is not None, 'DVE return/live identity failed')
        write(output / 'terminal.json', dict(returncode=process.returncode, live_identity=live))
        result = inspect(c, output)
        write(output / 'integrity-after.json', dict(status='PIN_PASS', pins=c['pins']))
        result['config_seal'] = seal
        result['output_pins'] = {str(p): sha(p) for p in output.rglob('*') if p.is_file()}
        write(output / 'result.json', result)
        write(output / 'status.json', dict(status=result['status'], result_seal=sha(output / 'result.json')))
        print(json.dumps(dict(status=result['status'], seal=sha(output / 'result.json'))))
    except Exception as exc:
        write(output / 'status.json', dict(status='HOLD', reason=str(exc), approval=False, automatic_retry=False))
        raise
    finally:
        if process is not None:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL); process.wait()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=('prepare', 'verify', 'run', 'inspect'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--raw-result', type=Path)
    parser.add_argument('--raw-seal')
    parser.add_argument('--el', type=Path, action='append', default=[])
    parser.add_argument('--review', type=Path, action='append', default=[])
    parser.add_argument('--review-seal', action='append', default=[])
    parser.add_argument('--timeout', type=int, default=900)
    args = parser.parse_args(); output = args.output.absolute()
    if args.command == 'prepare':
        require(all((args.raw_result, args.raw_seal, args.el, args.review, args.review_seal)),
                'Parent raw/EL/review paths and external review seals required')
        prepare(output, args.raw_result.absolute(), args.raw_seal, [x.absolute() for x in args.el],
                [x.absolute() for x in args.review], args.review_seal, args.timeout)
    else:
        require(args.seal, 'External config seal required')
        if args.review or args.review_seal or args.el:
            c = verify(output, args.seal)
            require([str(x.absolute()) for x in args.review] == c['reviews'] and
                    (not args.review_seal or args.review_seal == c['review_seals']) and
                    (not args.el or [str(x.absolute()) for x in args.el] == c['els']),
                    'Run reviews/ELs must be exactly the prepared inputs')
        if args.command == 'run':
            run(output, args.seal)
        else:
            c = verify(output, args.seal)
            print(json.dumps(inspect(c, output) if args.command == 'inspect' else dict(status='VERIFY_PASS_NO_DVE')))


if __name__ == '__main__':
    main()
