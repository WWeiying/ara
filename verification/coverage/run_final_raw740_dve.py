"""One parent-authorized historical740 raw export,600s,waiversoff; no simulation."""
import argparse
from decimal import Decimal
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import prepare_raw715_dve as common

life, tools, require = common.life, common.tools, common.require
OUT, ROOT = common.OUT, common.ROOT
BASE = OUT / 'queue-mask-offline-admitted-740-agent-20261007-01'
BASE_SEAL = '752d493c5fa8179ddd414d7810da479b1a56341a1600dff56c5b5afa0a3304b5'
PRIOR = OUT / 'csr-frozen-counter-offline-admitted-739-parent-20261007-01'
PRIOR_SEAL = '0ad9267a071b8019f758e8fe312c7b696bf977a1136f48474f65a39c2b81ffea'
REF = OUT / 'raw-dve-737-parent-20261006-01'
TIMEOUT = 600


def check_pins(pins):
    for path, expected in pins.items():
        require(tools.seal_file(path)['sha256'] == expected, 'Input/tool drift: ' + path)


def member_files(inputs):
    require(len(inputs) == len(set(inputs)) == 741 and inputs[0] == str(life.IMAGE) + '.vdb',
            'Exact740 plus old design required')
    selected, files = [], []
    for name in inputs:
        path = Path(name)
        require(path.resolve(strict=True) == path and path.suffix == '.vdb', 'Aliased/noncanonical VDB')
    db = Path(inputs[0]) / 'snps/coverage/db'
    require(not list((db / 'testdata').glob('*')), 'Design includes test data')
    files = [db / 'design/verilog.design.xml', *[db / ('shape/' + m + '.verilog.shape.xml') for m in common.METRICS]]
    for name in inputs[1:]:
        vdb = Path(name)
        tests = list((vdb / 'snps/coverage/db/testdata').iterdir())
        require(len(tests) == 1 and tests[0].is_dir() and not tests[0].is_symlink(), 'Ambiguous native test identity')
        selected.append(str(vdb.with_suffix('') / tests[0].name))
        for metric in common.METRICS:
            path = tests[0] / (metric + '.verilog.data.xml')
            require(path.is_file() and not path.is_symlink() and path.stat().st_size > 0, 'Missing/aliased metric')
            files.append(path)
    require(len(selected) == len(set(selected)) == 740, 'Duplicate native identity')
    return selected, files


def prepare(output, report):
    require(output.parent == report.parent == OUT and output != report and output.resolve() == output and
            report.resolve() == report and not output.exists() and not report.exists(), 'Fresh independent directories required')
    base = life.read_bound(BASE / 'admission-manifest.json', BASE_SEAL)
    prior = life.read_bound(PRIOR / 'admission-manifest.json', PRIOR_SEAL)
    require(base['schema'] == 'QUEUE_MASK_HISTORICAL740_ADMISSION_V1' and base['output'] == str(BASE) and
            base['baseline'] == str(PRIOR) and base['baseline_seal'] == PRIOR_SEAL and
            prior['schema'] == 'CSR_COUNTER_HISTORICAL739_ADMISSION_V1', 'Exact approved population chain required')
    pins = life.merge_pins(life.merge_pins(base['input_pins'], base['output_pins']),
                           life.merge_pins(prior['input_pins'], prior['output_pins']))
    pins = life.merge_pins(pins, {str(BASE / 'admission-manifest.json'): BASE_SEAL,
                                 str(PRIOR / 'admission-manifest.json'): PRIOR_SEAL})
    check_pins(pins)
    state = json.loads((BASE / 'status.json').read_bytes())
    bits = json.loads((BASE / 'combined-bits.json').read_bytes())
    old = json.loads((PRIOR / 'combined-bits.json').read_bytes())
    inputs = (BASE / 'combined-inputs.txt').read_text().splitlines()
    require(state['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and state['aggregate_passed'] == 740 and
            state['coverage_admitted'] is True and inputs[1:] == bits['tests'] and
            bits['tests'][:739] == old['tests'] and len(old['tests']) == len(set(old['tests'])) == 739 and
            sum(len(x) for x in bits['metrics'].values()) == 6162 and bits['design'] == old['design'],
            'Formal membership/shape differs')
    selected, files = member_files(inputs)
    for rel, digest in bits['design'].items():
        pins = life.merge_pins(pins, {str(Path(inputs[0]) / 'snps/coverage/db' / rel): digest})
    pins = life.merge_pins(pins, bits['input_hashes'])
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66, 'Old image66 differs')
    pins = life.merge_pins(pins, plan['image'])
    pins = life.merge_pins(pins, {str(life.PLAN): life.PLAN_SEAL})
    receipt = json.loads((REF / 'raw737-verification-receipt.json').read_bytes())
    require(receipt['status'] == 'RAW737_REVERIFIED_NOT_AGGREGATE_SIGNOFF' and
            receipt['summary']['rows'] == 2989 and receipt['selection']['count'] == 737,
            'Unqualified737 reference')
    pins = life.merge_pins(pins, receipt['output_artifact_pins'])
    files += [REF / 'raw737-verification-receipt.json', Path(__file__).resolve(),
              Path(__file__).with_name('test_run_final_raw740_dve.py'), Path(common.__file__).resolve(),
              common.WRAPPER, common.EXPORT, common.VERIFIER, common.HERE / 'prepare_dve_waivers.py',
              common.HERE / 'dve_waivers.tcl', Path(life.__file__).resolve(), Path(tools.__file__).resolve(),
              Path(common.hierarchy.__file__).resolve()]
    for name in ('Xvfb', 'xauth', 'timeout', 'python3', 'bash', 'grep'):
        path = shutil.which(name)
        require(path, 'Missing host tool: ' + name)
        files.append(Path(path))
    wrapper, xvfb = shutil.which('dve'), shutil.which('xvfb-run')
    require(wrapper and xvfb, 'Missing DVE/Xvfb')
    identity = tools.prepare(wrapper, xvfb)
    for item in identity['files']:
        pins = life.merge_pins(pins, {item['path']: item['sha256']})
    for path in files:
        if str(path) not in pins:
            pins = life.merge_pins(pins, {str(path): tools.seal_file(path)['sha256']})
    check_pins(pins)
    output.mkdir()
    common.save(output / 'inputs.txt', '\n'.join(inputs) + '\n')
    common.save(output / 'expected-selected-tests.txt', '\n'.join(selected) + '\n')
    pins = life.merge_pins(pins, {str(output / n): life.digest(output / n)
                                for n in ('inputs.txt', 'expected-selected-tests.txt')})
    config = dict(schema='FINAL_RAW740_DVE_PREPARED_V1', population=740, baseline=str(BASE), baseline_seal=BASE_SEAL,
        output=str(output), report=str(report), input_ledger=inputs, selected_tests=selected,
        pins=pins, tool_identity=identity, timeout_seconds=600, waiver_mode='off',
        command=common.command(report, output / 'inputs.txt'), automatic_retry=False,
        simulations_started=False, new_RTL_signoff=False)
    common.save(output / 'config.json', config)
    common.save(output / 'status.json', dict(status='PREPARED_NO_DVE', tests=740))
    print(json.dumps(dict(output=str(output), seal=life.digest(output / 'config.json'), pins=len(pins), tests=740)))


def read_config(output, seal):
    c = life.read_bound(output / 'config.json', seal)
    require(c['schema'] == 'FINAL_RAW740_DVE_PREPARED_V1' and c['population'] == 740 and
            c['baseline_seal'] == BASE_SEAL and c['baseline'] == str(BASE) and c['output'] == str(output) and
            c['timeout_seconds'] == 600 and c['waiver_mode'] == 'off' and c['automatic_retry'] is False and
            c['simulations_started'] is False and c['new_RTL_signoff'] is False, 'Frozen run contract differs')
    report = Path(c['report'])
    require(report.parent == OUT and report.resolve() == report and report != output and
            c['command'] == common.command(report, output / 'inputs.txt'), 'Command/report differs')
    check_pins(c['pins'])
    require(c['input_ledger'] == (output / 'inputs.txt').read_text().splitlines() ==
            (BASE / 'combined-inputs.txt').read_text().splitlines(), 'Final740 ledger changed')
    require(member_files(c['input_ledger'])[0] == c['selected_tests'], '740 native identities changed')
    tools.revalidate(c['tool_identity'])
    return c


def verify_report(c):
    report = Path(c['report'])
    require((report / 'inputs.txt').read_text().splitlines() == c['input_ledger'] and
            (report / 'selected_tests.txt').read_text().splitlines() == c['selected_tests'], 'Actual740 selection differs')
    waiver = json.loads((report / 'waiver_status.json').read_bytes())
    require(waiver['mode'] == 'off' and waiver['status'] == 'DISABLED' and waiver['waived_report'] is None and
            not list(report.glob('*.el')) and not list(report.glob('summary_waived*')), 'Unexpected exclusions')
    require((report / 'diagnostics.txt').read_bytes() == b'', 'DVE warnings/diagnostics')
    gui = (report / 'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('DVE_COVERAGE_EXPORT_DONE') == 1, 'Missing/duplicate completion marker')
    logged = [l[len('DVE_SELECTED_TESTS: '):].split() for l in gui.splitlines() if l.startswith('DVE_SELECTED_TESTS: ')]
    require(logged == [c['selected_tests']], 'Actual GUI740 identities differ')
    rows, old = common.summary_rows(report / 'summary.csv'), common.summary_rows(REF / 'summary.csv')
    require(len(rows) == len(old) == 2989 and [(r['Name'], r['Depth']) for r in rows] ==
            [(r['Name'], r['Depth']) for r in old], 'Incomplete/changed2989 hierarchy')
    new_system, old_system = ([r for r in data if r['Name'] == 'i_system'] for data in (rows, old))
    require(len(new_system) == len(old_system) == 1, 'Ambiguous system summary')
    current, prior = new_system[0], old_system[0]
    change = {k: str(Decimal(current[k][:-1]) - Decimal(prior[k][:-1]))
              for k in ('Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch')}
    return dict(summary=current, reference737=prior, percentage_point_delta_vs737=change, rows=2989)


def run(output, seal):
    c = read_config(output, seal)
    report = Path(c['report'])
    require(not report.exists() and not (output / 'execution.json').exists() and
            json.loads((output / 'status.json').read_bytes())['status'] == 'PREPARED_NO_DVE', 'No duplicate launch')
    env = tools.controlled_environment(c['tool_identity'], os.environ)
    env.pop('DVE', None)
    env['PATH'] = str(Path(c['tool_identity']['roles']['launcher']).parent) + ':/usr/bin:/bin'
    env.update(DVE_WAIVERS='off', DVE_COVERAGE_TIMEOUT='600', PYTHONDONTWRITEBYTECODE='1')
    (output / 'status.json').write_text(json.dumps(dict(status='RUNNING', tests=740)) + '\n')
    process = None
    try:
        with (output / 'run.log').open('x') as log:
            process = subprocess.Popen(c['command'], cwd=ROOT, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            start = tools.process_info(process.pid)['starttime']
            common.save(output / 'execution.json', dict(command=c['command'], cwd=str(ROOT), launch_pid=process.pid,
                        launch_starttime=start, waiver_mode='off', timeout_seconds=600, entry_DVE_unset=True))
            deadline, live = time.monotonic() + 660, None
            while process.poll() is None:
                if live is None:
                    for path in Path('/proc').iterdir():
                        if not path.name.isdigit():
                            continue
                        try:
                            if (path / 'exe').resolve(strict=True) == Path(c['tool_identity']['executable']):
                                live = tools.verify_live_executable(int(path.name), c['tool_identity'], process.pid, start)
                                common.save(output / 'live-identity.json', live)
                                break
                        except (OSError, ValueError):
                            continue
                require(time.monotonic() < deadline, 'DVE600s timeout')
                time.sleep(0.5)
            require(process.returncode == 0 and live is not None, 'DVE failed/live executable unproven')
        tools.revalidate(c['tool_identity'])
        summary = verify_report(c)
        subprocess.run(['/usr/bin/python3', str(common.VERIFIER), '--base', str(BASE), '--report', str(report)],
                       cwd=ROOT, check=True, timeout=120)
        check_pins(c['pins'])
        pins = life.merge_pins(c['pins'], {str(output / 'config.json'): seal})
        files = [output / 'execution.json', output / 'live-identity.json', output / 'run.log']
        files += [p for p in report.rglob('*') if p.is_file()]
        pins = life.merge_pins(pins, {str(p): tools.seal_file(p)['sha256'] for p in files})
        result = dict(status='VERIFIED_RAW740_HISTORICAL_ONLY', tests=740, report=str(report),
                      pins=pins, waived=False, simulations_started=False, new_RTL_signoff=False, **summary)
        common.save(output / 'result.json', result)
        (output / 'status.json').write_text(json.dumps(dict(status='COMPLETE_RAW740_HISTORICAL_ONLY',
            result_sha256=life.digest(output / 'result.json'), tests=740, report=str(report))) + '\n')
        print(json.dumps(dict(seal=life.digest(output / 'result.json'), **summary)))
    except Exception as error:
        (output / 'status.json').write_text(json.dumps(dict(status='FAILED', reason=str(error), tests=740)) + '\n')
        raise
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'run'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--report', type=Path)
    p.add_argument('--seal')
    a = p.parse_args()
    output = a.output.absolute()
    require(output.parent == OUT and output.resolve() == output, 'Direct output required')
    if a.mode == 'prepare':
        require(a.report and not a.seal, 'Prepare report only')
        prepare(output, a.report.absolute())
    else:
        require(a.seal and not a.report, 'Check/run exact seal only')
        if a.mode == 'check':
            read_config(output, a.seal)
            print('PREPARED_FINAL_RAW740_CHECK_PASS_NO_DVE')
        else:
            run(output, a.seal)


if __name__ == '__main__':
    main()
