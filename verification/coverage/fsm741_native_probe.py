"""One bounded read-only FSM token/API probe, one frozen historical PASS test."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import run_admitted_741_dve as report
import dve_tool_identity as tool

life, require = report.life, report.require
HERE = Path(__file__).resolve().parent
OUT = life.OUT / 'fsm741-native-token-probe-20261007-01'
HOOK = HERE / 'fsm741_native_probe.tcl'


def run():
    require(not OUT.exists(), 'No repeat probe')
    c = life.read_bound(report.admission.RAW, report.admission.RAW_SHA)
    design, sample = map(Path, c['input_ledger'][:2])
    db = design / 'snps/coverage/db'
    paths = [db / 'design/verilog.design.xml', db / 'auxiliary/verilog.sourceinfo.xml',
             db / 'shape/fsm.verilog.shape.xml']
    dirs = list((sample / 'snps/coverage/db/testdata').iterdir())
    require(len(dirs) == 1, 'Ambiguous historical sample')
    selected = str(sample.with_suffix('') / dirs[0].name)
    require(selected == c['selected_tests'][0], 'Sample identity differs')
    paths += [dirs[0] / (m + '.verilog.data.xml') for m in ('line', 'cond', 'branch', 'fsm', 'tgl')]
    pins = {str(report.admission.RAW): report.admission.RAW_SHA}
    for p in paths:
        require(str(p) in c['pins'], 'Unbound historical input')
        pins[str(p)] = c['pins'][str(p)]
    for p in (Path(__file__).resolve(), HOOK, HERE / 'test_fsm741_native_probe.py', HERE / 'discover_ptw_pmp0_fsm_v2.tcl',
              Path(tool.__file__).resolve()):
        pins[str(p)] = life.digest(p)
    life.check(pins)
    tool.revalidate(c['tool_identity'])
    OUT.mkdir()
    plan = dict(design=str(design), sample=str(sample), selected=selected,
                source_config=str(report.admission.RAW), source_seal=report.admission.RAW_SHA,
                pins=pins, no_exclusions=True, historical_single_test_not_population741=True)
    life.save(OUT / 'plan.json', plan)
    env = tool.controlled_environment(c['tool_identity'], os.environ)
    env.pop('DVE', None)
    env.update(FSM_PROBE_OUTPUT=str(OUT), FSM_PROBE_DESIGN=str(design),
               FSM_PROBE_SAMPLE=str(sample), FSM_PROBE_SELECTED=selected)
    process = None
    status = dict(status='RUNNING_READONLY', no_exclusions=True)
    try:
        with (OUT / 'launcher.log').open('x') as stream:
            process = subprocess.Popen(tool.launch_command(c['tool_identity'], HOOK), cwd=OUT,
                env=env, stdout=stream, stderr=subprocess.STDOUT, start_new_session=True)
            start = tool.process_info(process.pid)['starttime']
            deadline = time.monotonic() + 60
            live = None
            while process.poll() is None and time.monotonic() < deadline:
                for p in Path('/proc').iterdir():
                    if not p.name.isdigit():
                        continue
                    try:
                        if (p / 'exe').resolve() == Path(c['tool_identity']['executable']):
                            live = tool.verify_live_executable(int(p.name), c['tool_identity'], process.pid, start)
                            break
                    except (OSError, ValueError):
                        pass
                if live:
                    break
                time.sleep(.2)
            require(live is not None, 'No launch-bound DVE child')
            life.save(OUT / 'live-identity.json', live)
            (OUT / 'live-ready').touch()
            print('FSM_PROBE_LIVE pid=%s launch=%s' % (live['pid'], process.pid), flush=True)
            code = process.wait(timeout=300)
        life.check(pins)
        tool.revalidate(c['tool_identity'])
        log = (OUT / 'DVEfiles/dve_gui.log').read_text()
        require(code == 0 and log.splitlines().count('FSM741_READONLY_PROBE_DONE') == 1 and
                'FSM741_READONLY_PROBE_FAILED' not in log, 'Probe failed; preserve logs')
        require(not list(OUT.glob('*.el')), 'Unexpected exclusion file')
        status.update(status='READONLY_FSM_TOKENS_NOT_NATIVE_EXCLUSION_QUALIFICATION', returncode=code)
    except Exception as exc:
        status.update(status='FAILED', reason=str(exc))
        raise
    finally:
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        life.save(OUT / 'status.json', status)


if __name__ == '__main__':
    run()
