"""Scope-repair successor; sealed 01 inputs and exact qualification reused read-only."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import fma_expanded_native as frozen

life, require, tools = frozen.life, frozen.require, frozen.tools
HERE = Path(__file__).resolve().parent
OLD = life.OUT / 'fma_expanded_native_612-agent-20261007-01'
OLD_SEAL = '62e5ea8f9f052a5b7d7841913e6c4fc56f16c410d3572fb2647b416527a8f282'


def selection_text():
    lines = (OLD / 'selection.tcl').read_text().splitlines(keepends=True)
    require(lines[-1] == 'set fma_helper {' + str(HERE / 'fma_expanded_native.py') + '}\n',
            'Unexpected predecessor helper binding')
    return ''.join(lines[:-1]) + 'set fma_helper {' + str(Path(__file__).resolve()) + '}\n'


def prepare(out):
    require(out.parent == life.OUT and out.resolve() == out and not out.exists(), 'Fresh independent output required')
    c = life.read_bound(OLD / 'config.json', OLD_SEAL)
    life.check(c['pins'])
    require(life.digest(life.IMAGE) == frozen.IMAGE_SHA, 'Frozen simv differs')
    frozen.validate_review(life.read_bound(frozen.REVIEW, frozen.REVIEW_SHA))
    tools.revalidate(c['identity'])
    require(json.loads((OLD / 'qualification-reject.json').read_bytes())['status'] == 'REJECTED_NOT_QUALIFIED',
            'Predecessor outcome differs')
    pins = {**c['pins'], **{str(p): life.digest(p) for p in OLD.rglob('*') if p.is_file()}}
    for p in (Path(__file__).resolve(), HERE / 'fma_expanded_native_02.tcl', HERE / 'test_fma_expanded_native_02.py'):
        pins[str(p)] = life.digest(p)
    life.check(pins)
    tests = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'test_fma_expanded_native',
                            'test_review_fma_arithmetic_scope', 'test_fma_datapath_native',
                            'test_fma_expanded_native_02', '-v'], cwd=HERE, text=True, capture_output=True)
    require(tests.returncode == 0 and 'Ran 23 tests' in tests.stderr and tests.stderr.rstrip().endswith('OK'),
            'Original plus eval-scope regression did not pass: ' + tests.stderr)
    out.mkdir()
    life.save(out / 'test-regression.json', dict(returncode=tests.returncode, tests=23,
                                               stdout=tests.stdout, stderr=tests.stderr))
    pins[str(out / 'test-regression.json')] = life.digest(out / 'test-regression.json')
    life.save(out / 'selection.tcl', selection_text())
    pins[str(out / 'selection.tcl')] = life.digest(out / 'selection.tcl')
    c.update(output=str(out), pins=pins, predecessor_config_seal=OLD_SEAL,
             repair='Only Tcl session global bindings; exact 612 targets and full complement unchanged')
    life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), pins=len(pins))))


def run(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    tools.revalidate(c['identity'])
    env = tools.controlled_environment(c['identity'], os.environ)
    env.pop('DVE', None)
    env.update(DVE_COVERAGE_OUTPUT=str(out), FMA_EXPANDED_CONFIG_SEAL=seal)
    command = [c['identity']['roles']['xvfb_run'], '-a', '-e', str(out / 'xvfb.log'),
               '-s', '-screen 0 1280x1024x24', c['identity']['roles']['launcher'],
               '-full64', '-cov', '-script', str(HERE / 'fma_expanded_native_02.tcl')]
    with (out / 'execution.json').open('x') as receipt:
        json.dump(dict(command=command, cwd=str(out), timeout_seconds=c['timeout_seconds'],
                       automatic_retry=False, systemd_service=os.environ.get('INVOCATION_ID')), receipt)
    with (out / 'launcher.log').open('x') as log:
        process = subprocess.Popen(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                                   start_new_session=True)
        time.sleep(10)
        candidates = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():
                continue
            try:
                if (p / 'exe').resolve() == Path(c['identity']['executable']) and (p / 'cwd').resolve() == out:
                    candidates.append(dict(pid=int(p.name), exe=str((p / 'exe').resolve()), cwd=str(out),
                                           cgroup=(p / 'cgroup').read_text()))
            except OSError:
                continue
        life.save(out / 'live-identity.json', candidates)
        print(json.dumps(dict(actual_dve=candidates)), flush=True)
        timed_out = False
        try:
            process.wait(timeout=c['timeout_seconds'])
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    life.save(out / 'terminal.json', dict(returncode=process.returncode, timeout=timed_out, actual_dve=candidates))
    try:
        frozen.verify(out, seal)
    except Exception as error:
        life.save(out / 'qualification-reject.json', dict(status='REJECTED_NOT_QUALIFIED', reason=str(error),
                  config_seal=seal, captures_preserved=True, automatic_retry=False))
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'run', 'verify', 'stage'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--stage', choices=frozen.STAGES)
    args = parser.parse_args()
    out = args.output.absolute()
    if args.mode == 'prepare':
        prepare(out)
    else:
        require(args.seal, 'Sealed config required')
        if args.mode == 'stage':
            c = life.read_bound(out / 'config.json', args.seal)
            life.check(c['pins'])
            print(json.dumps(frozen.check_stage(out, args.stage, c)))
        else:
            (run if args.mode == 'run' else frozen.verify)(out, args.seal)
