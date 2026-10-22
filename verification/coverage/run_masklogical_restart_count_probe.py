"""One bounded read-only diagnostic; never admit its partial run as a PASS."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'verification/out/failed-repair-image-20261008-03'
ELF = ROOT / 'verification/out/masklogical-same-source-preflight-20261008-01/input.elf'
OUT = ROOT / 'verification/out/masklogical-restart-count-probe-agent-20261008-01'
PROBE = Path(__file__).with_name('masklogical_restart_count_probe.tcl')
ELF_SHA = 'b303202028b57c63ad29a9e3268fdbbd24f409cc2de4567c0757906380ac9930'


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def save(name, value):
    (OUT / name).write_text(json.dumps(value, indent=2) + '\n')


def check(pins):
    for path, sha in pins.items():
        if digest(path) != sha:
            raise ValueError('Pin mismatch: ' + path)


def main():
    status = json.loads((BUILD / 'build-status.json').read_text())
    if status['status'] != 'PASS':
        raise ValueError('Build03 is not PASS')
    terminal = subprocess.check_output(['systemctl', '--user', 'show', status['unit'],
        '-p', 'MainPID', '-p', 'ActiveState', '-p', 'Result', '-p', 'ExecMainStatus'], text=True)
    if not {'MainPID=0', 'ActiveState=inactive', 'Result=success', 'ExecMainStatus=0'} <= set(terminal.splitlines()):
        raise ValueError('Build service not successfully terminal')
    pins = json.loads((BUILD / 'build-image.json').read_text())
    pins.update(json.loads((BUILD / 'build-source-pins.json').read_text()))
    pins.update({str(ELF): ELF_SHA, str(PROBE): digest(PROBE), str(Path(__file__)): digest(__file__)})
    check(pins)
    OUT.mkdir(parents=True, exist_ok=False)
    shutil.copyfile(ELF, OUT / 'input.elf')
    shutil.copyfile(PROBE, OUT / 'probe.tcl')
    save('pins.json', pins)
    save('build-terminal.json', {'show': terminal})
    image = BUILD / 'sim/simv'
    command = [str(image), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(OUT / 'input.elf'), '+TESTCASE=masklogical_restart_count_probe',
        '+COMMIT_TRACE=' + str(OUT / 'commit_trace.csv'),
        '+VECTOR_TRACE=' + str(OUT / 'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(OUT / 'diagnostic.vdb'),
        '-cm_name', 'masklogical_restart_probe', '-ucli', '-do', str(OUT / 'probe.tcl')]
    save('command.json', {'command': command, 'cwd': str(OUT), 'timeout_s': 900,
                         'window_cycles': [250530, 250750], 'same_full_68_case_elf': True})
    started = time.monotonic()
    result = {'status': 'RUNNING', 'coverage_admitted': False, 'architectural_pass': False}
    save('status.json', result)
    try:
        with (OUT / 'console.log').open('x') as log:
            with subprocess.Popen(command, cwd=OUT, stdout=log, stderr=subprocess.STDOUT,
                                  start_new_session=True) as proc:
                save('started.json', {'pid': proc.pid, 'epoch': time.time(),
                     'elf_sha256': ELF_SHA, 'image_sha256': digest(image)})
                try:
                    code = proc.wait(timeout=900)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                    raise
        text = (OUT / 'console.log').read_text()
        if code != 0 or 'MASKLOGICAL_RESTART_CAPTURE_COMPLETE_NOT_ARCHITECTURAL_PASS' not in text:
            raise ValueError('Incomplete diagnostic capture, simulator return=' + str(code))
        if 'MASKLOGICAL_RESTART_ERROR' in text or not (OUT / 'masklogical-restart.vpd').is_file():
            raise ValueError('Probe rejected or missing waveform')
        check(pins)
        result.update(status='CAPTURE_COMPLETE', returncode=code,
                      wave_sha256=digest(OUT / 'masklogical-restart.vpd'))
    except Exception as exc:
        result.update(status='TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'ERROR',
                      reason=type(exc).__name__ + ': ' + str(exc))
    result['elapsed_s'] = time.monotonic() - started
    save('status.json', result)
    return 0 if result['status'] == 'CAPTURE_COMPLETE' else 1


if __name__ == '__main__':
    raise SystemExit(main())
