"""Frozen715 raw DVE preparation; launch is an explicit later command only."""
import argparse
import csv
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import dve_tool_identity as tools
import report_scope_ancestors as hierarchy
import run_gap95_simulation as life

HERE = Path(__file__).resolve().parent
OUT, ROOT = life.OUT, HERE.parent.parent
BASE = OUT / 'gap100-offline-admitted-715-20261006-01'
BASE_SEAL = '069e9e7717e915c18ce921f583fa33bf18e7670a3f13ec12073e8bba1998a283'
REFERENCE = OUT / 'raw707-dve-20261006-01'
WRAPPER = HERE / 'run_dve_coverage.sh'
EXPORT = HERE / 'export_dve_coverage.tcl'
VERIFIER = HERE / 'verify_historical_raw_report.py'
SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_prepare_raw715_dve.py')
TIMEOUT = 3600
METRICS = ('line', 'cond', 'branch', 'fsm', 'tgl')


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def save(path, value):
    with path.open('x') as stream:
        stream.write(value if isinstance(value, str) else json.dumps(value, indent=2) + '\n')


def member_files(inputs):
    require(len(inputs) == len(set(inputs)) == 716 and inputs[0] == str(life.IMAGE) + '.vdb',
            'Exact715 plus old design required')
    selected, files = [], []
    for path in inputs:
        require(str(Path(path).resolve(strict=True)) == path and path.endswith('.vdb'),
                'Noncanonical database')
    design = Path(inputs[0]) / 'snps/coverage/db'
    files += [design / 'design/verilog.design.xml']
    files += [design / ('shape/%s.verilog.shape.xml' % m) for m in METRICS]
    require(not list((design / 'testdata').glob('*')), 'Design unexpectedly contains test samples')
    for name in inputs[1:]:
        vdb = Path(name)
        directories = list((vdb / 'snps/coverage/db/testdata').iterdir())
        require(len(directories) == 1 and directories[0].is_dir(), 'Ambiguous/missing test sample')
        selected.append(str(vdb.with_suffix('') / directories[0].name))
        for metric in METRICS:
            path = directories[0] / (metric + '.verilog.data.xml')
            require(path.is_file() and path.stat().st_size > 0, 'Missing/empty metric: ' + str(path))
            files.append(path)
    require(len(selected) == len(set(selected)) == 715, 'Duplicate native test identity')
    return selected, files


def command(report, inputs):
    return ['/bin/bash', str(WRAPPER), str(report), '--inputs-file', str(inputs)]


def environment(identity, inherited):
    env = tools.controlled_environment(identity, inherited)
    # The vendor launcher itself derives DVE; caller-set DVE produces a warning.
    env.pop('DVE', None)
    env['PATH'] = str(Path(identity['roles']['launcher']).parent) + ':/usr/bin:/bin'
    env.update(DVE_WAIVERS='off', DVE_COVERAGE_TIMEOUT=str(TIMEOUT), PYTHONDONTWRITEBYTECODE='1')
    return env


def prepare(output, report):
    output, report = Path(output).absolute(), Path(report).absolute()
    require(output.parent == report.parent == OUT and output != report and
            output.resolve() == output and report.resolve() == report and
            not output.exists() and not report.exists(), 'Fresh independent prepared/report directories required')
    seals = life.read_bound(BASE / 'seals.json', BASE_SEAL)
    require(seals['status'] == 'SEALED_FORMAL_715_HISTORICAL_ONLY', 'Not formal715')
    pins = life.merge_pins(seals['pins'], {str(BASE / 'seals.json'): BASE_SEAL})
    status = json.loads((BASE / 'status.json').read_bytes())
    union = json.loads((BASE / 'combined-bits.json').read_bytes())
    inputs = (BASE / 'combined-inputs.txt').read_text().splitlines()
    require(status['status'] == 'PASS_RAW_UNION_HISTORICAL_ONLY' and status['aggregate_passed'] == 715 and
            inputs[1:] == union['tests'], 'Unadmitted/different715 input ledger')
    selected, files = member_files(inputs)
    for relative, expected in union['design'].items():
        path = Path(inputs[0]) / 'snps/coverage/db' / relative
        pins = life.merge_pins(pins, {str(path): expected})
    plan = life.read_bound(life.PLAN, life.PLAN_SEAL)
    require(plan['simv'] == str(life.IMAGE) and len(plan['image']) == 66, 'Not frozen old image66')
    pins = life.merge_pins(pins, plan['image'])
    pins = life.merge_pins(pins, {str(life.PLAN): life.PLAN_SEAL})
    reference = json.loads((REFERENCE / 'population-verification.json').read_bytes())
    require(reference['status'] == 'VERIFIED_HISTORICAL_RAW_REPORT' and reference['admitted_tests'] == 707,
            'Unqualified raw707 reference')
    pins = life.merge_pins(pins, reference['pins'])
    files += [REFERENCE / 'population-verification.json', SCRIPT, TEST, WRAPPER, EXPORT, VERIFIER,
              HERE / 'prepare_dve_waivers.py', HERE / 'dve_waivers.tcl', Path(life.__file__).resolve(),
              Path(tools.__file__).resolve(), Path(hierarchy.__file__).resolve()]
    for path in files:
        if str(path) not in pins:
            pins = life.merge_pins(pins, {str(path): life.digest(path)})
    wrapper, xvfb = shutil.which('dve'), shutil.which('xvfb-run')
    require(wrapper and xvfb, 'DVE/Xvfb missing')
    identity = tools.prepare(wrapper, xvfb)
    for item in identity['files']:
        pins = life.merge_pins(pins, {item['path']: item['sha256']})
    life.check(pins)
    output.mkdir()
    save(output / 'inputs.txt', '\n'.join(inputs) + '\n')
    save(output / 'expected-selected-tests.txt', '\n'.join(selected) + '\n')
    pins = life.merge_pins(pins, {str(output / n): life.digest(output / n)
                                for n in ('inputs.txt', 'expected-selected-tests.txt')})
    config = dict(schema='historical715-raw-dve-prepared-v1', baseline=str(BASE), baseline_seal=BASE_SEAL,
        population=715, output=str(output), report=str(report), command=command(report, output / 'inputs.txt'),
        input_ledger=inputs, selected_tests=selected, tool_identity=identity, pins=pins,
        timeout_seconds=TIMEOUT, waiver_mode='off', metric_files=list(METRICS),
        reference_summary=str(REFERENCE / 'summary.csv'), simulations_started=False,
        new_RTL_signoff=False, launched=False)
    save(output / 'config.json', config)
    save(output / 'status.json', dict(status='PREPARED_NO_DVE', config_sha256=life.digest(output / 'config.json'),
                                    tests=715, waived=False, simulations_started=False))
    print(json.dumps(dict(status='PREPARED_NO_DVE', config_seal=life.digest(output / 'config.json'),
                          output=str(output), report=str(report), pins=len(pins))))


def read_config(output, seal):
    c = life.read_bound(output / 'config.json', seal)
    require(c['schema'] == 'historical715-raw-dve-prepared-v1' and c['baseline'] == str(BASE) and
            c['baseline_seal'] == BASE_SEAL and c['output'] == str(output) and c['population'] == 715 and
            c['waiver_mode'] == 'off' and c['metric_files'] == list(METRICS) and
            c['timeout_seconds'] == TIMEOUT and c['launched'] is False and
            c['simulations_started'] is False and c['new_RTL_signoff'] is False, 'Prepared contract differs')
    report = Path(c['report'])
    require(report.parent == OUT and report.resolve() == report and report != output and
            c['command'] == command(report, output / 'inputs.txt'), 'Prepared command/report differs')
    life.check(c['pins'])
    require((output / 'inputs.txt').read_text().splitlines() == c['input_ledger'] and
            c['input_ledger'] == (BASE / 'combined-inputs.txt').read_text().splitlines(), '715 ledger drift')
    selected, _ = member_files(c['input_ledger'])
    require(selected == c['selected_tests'], 'Native member identities drift')
    tools.revalidate(c['tool_identity'])
    return c


def summary_rows(path):
    with path.open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames == ['Name', 'Depth', 'Score', 'Line', 'Toggle', 'FSM', 'Condition', 'Branch'],
                'Incomplete/different raw metric columns')
        rows = list(reader)
    for row in rows:
        require(set(row) == set(reader.fieldnames) and all(v is not None for v in row.values()), 'Incomplete CSV row')
        for key in reader.fieldnames[2:]:
            value = row[key]
            require(value == 'NA' or (value.endswith('%') and 0 <= float(value[:-1]) <= 100), 'Invalid metric value')
    hierarchy.report_ancestors(rows, {'ara_tb.dut.i_ara_soc.i_system'})
    return rows


def verify_report(config):
    report = Path(config['report'])
    require((report / 'inputs.txt').read_text().splitlines() == config['input_ledger'] and
            (report / 'selected_tests.txt').read_text().splitlines() == config['selected_tests'], 'Report population differs')
    require(json.loads((report / 'waiver_status.json').read_bytes())['status'] == 'DISABLED' and
            not any((report / n).exists() for n in ('exclusions.el', 'summary_waived.csv', 'summary_waived.csv.partial')),
            'Unexpected waiver application')
    require((report / 'diagnostics.txt').read_bytes() == b'', 'DVE diagnostics present')
    rows, reference = summary_rows(report / 'summary.csv'), summary_rows(Path(config['reference_summary']))
    require([(r['Name'], r['Depth']) for r in rows] == [(r['Name'], r['Depth']) for r in reference],
            'Raw hierarchy incomplete/different; do not silently allow missing vendor roots')
    return rows


def run(output, seal):
    c = read_config(output, seal)
    report = Path(c['report'])
    require(json.loads((output / 'status.json').read_bytes())['status'] == 'PREPARED_NO_DVE' and
            not report.exists() and not (output / 'execution.json').exists(), 'No repeated launch')
    identity = c['tool_identity']
    # Mutable run status is separate from the sealed config and input ledger.
    (output / 'status.json').write_text(json.dumps(dict(status='RUNNING', tests=715, config_sha256=seal)) + '\n')
    process = None
    try:
        with (output / 'run.log').open('x') as log:
            process = subprocess.Popen(c['command'], cwd=ROOT, env=environment(identity, os.environ),
                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
            start = tools.process_info(process.pid)['starttime']
            save(output / 'execution.json', dict(command=c['command'], cwd=str(ROOT), launch_pid=process.pid,
                launch_starttime=start, waiver_mode='off', entry_DVE_unset=True, timeout_seconds=TIMEOUT))
            deadline, live = time.monotonic() + TIMEOUT + 60, None
            while process.poll() is None:
                if live is None:
                    for path in Path('/proc').iterdir():
                        if not path.name.isdigit():
                            continue
                        try:
                            if (path / 'exe').resolve(strict=True) == Path(identity['executable']):
                                live = tools.verify_live_executable(int(path.name), identity, process.pid, start)
                                save(output / 'live-identity.json', live)
                                break
                        except (OSError, ValueError):
                            continue
                require(time.monotonic() < deadline, 'DVE report timeout')
                time.sleep(0.5)
            require(process.returncode == 0 and live is not None, 'DVE failure or unproven executable')
        tools.revalidate(identity)
        verify_report(c)
        subprocess.run(['/usr/bin/python3', str(VERIFIER), '--base', str(BASE), '--report', str(report)],
                       cwd=ROOT, check=True, timeout=120)
        life.check(c['pins'])
        pins = life.merge_pins(c['pins'], {str(output / 'config.json'): seal})
        for path in [output / 'execution.json', output / 'live-identity.json', output / 'run.log',
                     *[report / n for n in ('summary.csv', 'selected_tests.txt', 'diagnostics.txt', 'waiver_status.json',
                                           'inputs.txt', 'population-verification.json', 'launcher.log', 'DVEfiles/dve_gui.log')]]:
            pins = life.merge_pins(pins, {str(path): life.digest(path)})
        save(output / 'result.json', dict(status='VERIFIED_RAW715_HISTORICAL_ONLY', tests=715, report=str(report),
            pins=pins, official_raw_DVE_report=True, waived=False, simulations_started=False, new_RTL_signoff=False))
        (output / 'status.json').write_text(json.dumps(dict(status='COMPLETE_RAW715_HISTORICAL_ONLY',
            result_sha256=life.digest(output / 'result.json'), report=str(report), tests=715, waived=False)) + '\n')
    except Exception as error:
        (output / 'status.json').write_text(json.dumps(dict(status='FAILED', reason=str(error),
            tests=715, report=str(report), simulations_started=False)) + '\n')
        raise
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check', 'run'))
    parser.add_argument('--output', required=True, type=Path)
    parser.add_argument('--report', type=Path)
    parser.add_argument('--seal')
    args = parser.parse_args()
    if args.mode == 'prepare':
        require(args.report is not None and args.seal is None, 'prepare requires --report only')
        prepare(args.output, args.report)
    else:
        require(args.seal is not None and args.report is None, 'check/run requires exact --seal')
        output = args.output.absolute()
        require(output.parent == OUT and output.resolve() == output, 'Direct prepared output required')
        if args.mode == 'check':
            read_config(output, args.seal)
            print('PREPARED_RAW715_CHECK_PASS_NO_LAUNCH')
        else:
            run(output, args.seal)
