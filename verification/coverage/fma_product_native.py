"""Single reviewed FP32 vector native-format capture; no processor simulation."""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

import run_admitted_741_dve as inherited
import prepare_raw715_dve as common

life, require, tools = inherited.life, inherited.require, inherited.tools
HERE = Path(__file__).resolve().parent
REVIEW = life.OUT / 'fp32-fp64-fma-scoped-review-741-agent-20261007-01.json'
REVIEW_SHA = '3225bfd410ae64453f10b45a7e0d81532ba6c1f5bc2c012206a9fb66065be323'


def el(text, scope):
    checksum, instance, signals = None, None, []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith(('//', 'ANNOTATION:')):
            continue
        if line.startswith('CHECKSUM:'):
            require(checksum is None, 'Multiple checksum records')
            checksum = line.split(':', 1)[1].strip().strip('"').split()
        elif line.startswith('INSTANCE:'):
            require(instance is None, 'Multiple instance records')
            instance = line.split(':', 1)[1].strip()
        else:
            require(re.fullmatch(r'Toggle product(?:\[47:0\])?(?:\s+"[^"]*")?', line), 'Other signal/direction/metric exclusion: ' + line)
            signals.append(line)
    require(instance == scope and len(signals) == 1 and checksum in
            (['2431620414'], ['248862639'], ['2431620414', '248862639']), 'Whole signal/checksum binding differs')
    return dict(scope=scope, signal='product', bounds=[47, 0], directions=['0to1', '1to0'], native_lines=text.splitlines())


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh output required')
    review = life.read_bound(REVIEW, REVIEW_SHA)
    instance, case = review['instances'][0], review['evidence'][0]
    require(instance['format'] == case['format'] == 'FP32' and instance['toggle_checksum'] == '248862639', 'Wrong representative')
    pins = {str(REVIEW): REVIEW_SHA}
    for item in [*review['source_pins'], *review['compiled_pins'], *case['pins']]:
        pins[str((life.ROOT / item['path']).resolve())] = item['sha256']
    for item in review['baseline']:
        pins[str((life.ROOT / item['path']).resolve())] = item['sha256']
    raw = life.read_bound(inherited.admission.RAW, inherited.admission.RAW_SHA)
    identity = raw['tool_identity']
    tools.revalidate(identity)
    vdb = Path(case['vdb'])
    directories = list((vdb / 'snps/coverage/db/testdata').iterdir())
    require(len(directories) == 1 and vdb in map(Path, (inherited.BASE / 'combined-inputs.txt').read_text().splitlines()), 'Not one admitted historical PASS VDB')
    require(case['scalar_skipped'] == 0 and case['scalar_status'] == 'TERMINAL_MATCH' and
            all(x['status'] == 'PASS' and x['skipped_unknown_bytes'] == x['mismatch_count'] == 0 for x in case['selected_exact_requests']), 'Unqualified exact golden request')
    for path in directories[0].glob('*.data.xml'):
        pins[str(path)] = life.digest(path)
    for path in (Path(__file__).resolve(), HERE / 'fma_product_native.tcl', Path(inherited.admission.RAW)):
        pins[str(path)] = life.digest(path)
    life.check(pins)
    out.mkdir()
    test = str(vdb.with_suffix('') / directories[0].name)
    values = dict(fma_scope=instance['scope'], fma_design=str(life.IMAGE) + '.vdb', fma_vdb=str(vdb),
                  fma_test=test, fma_python=shutil.which('python3'), fma_helper=str(Path(__file__).resolve()))
    require(all(not any(x in v for x in '{}\\\n\r') for v in values.values()), 'Unsafe Tcl value')
    common.save(out / 'selection.tcl', ''.join('set ' + k + ' {' + v + '}\n' for k, v in values.items()))
    pins[str(out / 'selection.tcl')] = life.digest(out / 'selection.tcl')
    c = dict(output=str(out), pins=pins, identity=identity, scope=instance['scope'], test=test,
        shape_checksum='248862639', module_checksum='2431620414', declline=323, width=48,
        signal='product', timeout_seconds=600, input_VDB_count=1, population_application=False,
        observer_report_rerun=False, automatic_retry=False)
    life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), pins=len(pins), scope=c['scope'])))


def check_el(out, name):
    c = json.loads((out / 'config.json').read_bytes())
    print(json.dumps(el((out / name).read_text(), c['scope'])))


def run(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    tools.revalidate(c['identity'])
    env = tools.controlled_environment(c['identity'], os.environ)
    env.pop('DVE', None)
    env['DVE_COVERAGE_OUTPUT'] = str(out)
    command = [shutil.which('xvfb-run'), '-a', '-e', str(out / 'xvfb.log'), '-s', '-screen 0 1280x1024x24',
               c['identity']['roles']['launcher'], '-full64', '-cov', '-script', str(HERE / 'fma_product_native.tcl')]
    life.save(out / 'execution.json', dict(command=command, cwd=str(out), timeout_seconds=600, automatic_retry=False))
    with (out / 'launcher.log').open('x') as log:
        process = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        time.sleep(10)
        candidates = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():
                continue
            try:
                if (p / 'exe').resolve() == Path(c['identity']['executable']) and (p / 'cwd').resolve() == out:
                    candidates.append(dict(pid=int(p.name), exe=str((p / 'exe').resolve()), cwd=str(out)))
            except OSError:
                continue
        life.save(out / 'live-identity.json', candidates)
        print(json.dumps(dict(actual_dve=candidates)), flush=True)
        try:
            rc = process.wait(timeout=600)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            life.save(out / 'terminal.json', dict(timeout=True, returncode=process.returncode, qualification=False))
            raise
    life.save(out / 'terminal.json', dict(returncode=rc, timeout=False, actual_dve=candidates))
    require(rc == 0 and len(candidates) == 1, 'DVE terminal/identity failure')
    for name in ('initial-empty.el', 'reset-empty.el', 'final-empty.el'):
        require((out / name).read_bytes() == b'', 'Nonempty reset/global EL')
    first, second = el((out / 'first.el').read_text(), c['scope']), el((out / 'second.el').read_text(), c['scope'])
    require({k: v for k, v in first.items() if k != 'native_lines'} ==
            {k: v for k, v in second.items() if k != 'native_lines'}, 'Signal semantic reload mismatch')
    gui = (out / 'DVEfiles/dve_gui.log').read_text()
    require(gui.splitlines().count('FMA_PRODUCT_NATIVE_CAPTURE_DONE') == 1 and
            'FMA_PRODUCT_NATIVE_CAPTURE_FAILED' not in gui, 'Native capture not completed')
    life.check(c['pins'])
    life.save(out / 'capture-result.json', dict(status='ONE_FP32_PRODUCT_NATIVE_FORMAT_ROUNDTRIP_PASS',
        config_seal=seal, target=first, reload=second, exact_exclusive_signal_EL=True,
        non_target_signal_exclusions=0, reset_global_empty=True, population_application=False,
        pins={**c['pins'], **{str(p): life.digest(p) for p in out.rglob('*') if p.is_file()}}))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run', 'el'))
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--seal')
    p.add_argument('--file')
    a = p.parse_args()
    if a.mode == 'prepare':
        prepare(a.output.absolute())
    elif a.mode == 'el':
        require(a.file in ('first.el', 'second.el'), 'Unknown capture file')
        check_el(a.output.absolute(), a.file)
    else:
        require(a.seal, 'Exact launch seal required')
        run(a.output.absolute(), a.seal)
