"""Text-selection successor with actual on-disk Tcl entry qualification before EDA."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import fma_expanded_native_02 as prior

frozen = prior.frozen
life, require, tools = prior.life, prior.require, prior.tools
HERE = Path(__file__).resolve().parent
OLD = life.OUT / 'fma_expanded_native_612-agent-20261007-02'
OLD_SEAL = 'bb7c08ef2d46cbff241751095a77e965c97c6d1a7e7d430de6f9d4ece52669df'
ENTRY = HERE / 'fma_expanded_native_03.tcl'


def selection_text():
    lines = (prior.OLD / 'selection.tcl').read_text().splitlines(keepends=True)
    require(lines[-1] == 'set fma_helper {' + str(HERE / 'fma_expanded_native.py') + '}\n',
            'Unexpected original helper binding')
    return ''.join(lines[:-1]) + 'set fma_helper {' + str(Path(__file__).resolve()) + '}\n'


def write_selection(out):
    text = selection_text()
    frozen.predecessor.one.common.save(out / 'selection.tcl', text)
    require((out / 'selection.tcl').read_bytes() == text.encode('ascii'), 'Selection bytes differ')


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
    for p in (Path(__file__).resolve(), ENTRY, HERE / 'test_fma_expanded_native_03.py',
              HERE / 'fma_expanded_session_mock_03.py'):
        pins[str(p)] = life.digest(p)
    life.check(pins)
    out.mkdir()
    write_selection(out)
    pins[str(out / 'selection.tcl')] = life.digest(out / 'selection.tcl')
    from fma_expanded_session_mock_03 import qualify_disk_entry
    evidence = qualify_disk_entry(out / 'selection.tcl')
    life.save(out / 'plain-tcl-entry-regression.json', evidence)
    pins[str(out / 'plain-tcl-entry-regression.json')] = life.digest(out / 'plain-tcl-entry-regression.json')
    tests = subprocess.run([sys.executable, '-B', '-m', 'unittest', 'test_fma_expanded_native',
                            'test_review_fma_arithmetic_scope', 'test_fma_datapath_native',
                            'test_fma_expanded_native_02', 'test_fma_expanded_native_03', '-v'],
                           cwd=HERE, text=True, capture_output=True)
    require(tests.returncode == 0 and tests.stderr.rstrip().endswith('OK'),
            'Original and actual entry regressions failed: ' + tests.stderr)
    life.save(out / 'test-regression.json', dict(returncode=tests.returncode, stdout=tests.stdout, stderr=tests.stderr))
    pins[str(out / 'test-regression.json')] = life.digest(out / 'test-regression.json')
    c.update(output=str(out), pins=pins, predecessor_config_seal=OLD_SEAL, entry_script=str(ENTRY),
             repair='Plain-text selection writer; complete source/session/eval on actual disk bytes tested',
             actual_disk_Tcl_entry_mock_qualified=True, mock_is_not_native_qualification=True)
    life.check(pins)
    life.save(out / 'config.json', c)
    print(json.dumps(dict(output=str(out), seal=life.digest(out / 'config.json'), pins=len(pins))))


def run(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    tools.revalidate(c['identity'])
    require(c['entry_script'] == str(ENTRY) and c['actual_disk_Tcl_entry_mock_qualified'], 'Wrong entry')
    env = tools.controlled_environment(c['identity'], os.environ)
    env.pop('DVE', None)
    env.update(DVE_COVERAGE_OUTPUT=str(out), FMA_EXPANDED_CONFIG_SEAL=seal)
    command = [c['identity']['roles']['xvfb_run'], '-a', '-e', str(out / 'xvfb.log'),
               '-s', '-screen 0 1280x1024x24', c['identity']['roles']['launcher'],
               '-full64', '-cov', '-script', c['entry_script']]
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
