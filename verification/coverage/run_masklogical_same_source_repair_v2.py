"""Full unchanged 68-case matrix on a newly pinned build, with explicit budget."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import run_masklogical_same_source_repair as original

DEFAULT_PROBE = Path(__file__).with_name('masklogical_cold_restart_probe.tcl')


def bind_build(build):
    status_path = build / 'build-status.json'
    image_path = build / 'build-image.json'
    sources_path = build / 'build-source-pins.json'
    status = json.loads(status_path.read_text())
    original.require(status['status'] == 'PASS', 'Build receipt is not PASS')
    images = json.loads(image_path.read_text())
    image = build / 'sim/simv'
    original.require(str(image) in images, 'Build image pins do not identify simv')
    if 'image' in status:
        original.require(status['image'] == images, 'Build receipt/image manifest disagree')
    pins = dict(images)
    pins.update(json.loads(sources_path.read_text()))
    for path in (status_path, image_path, sources_path):
        pins[str(path)] = original.digest(path)
    original.check_pins(pins)
    # Successful transient systemd units may already have been garbage-collected.
    # The sealed build PASS receipt and exact current source/image pins are binding.
    return image, pins


def execute(build, out, timeout_s, probe=DEFAULT_PROBE):
    original.require(timeout_s > 0, 'A positive measured execution budget is required')
    original.require(not out.exists(), 'Fresh output directory required')
    image, pins = bind_build(build)
    pre = json.loads((original.PRE / 'manifest.json').read_text())
    for key in ('source_pins', 'tool_pins', 'binary_pins'):
        pins.update(pre[key])
    for path in (Path(__file__), Path(original.__file__), probe,
                 Path(original.wave.__file__), Path(original.canonical.__file__),
                 original.canonical.CONVERTER):
        pins[str(path)] = original.digest(path)
    original.check_pins(pins)
    original.require(original.digest(original.PRE / 'input.elf') == original.ELF_SHA,
                     'Full original matrix ELF differs')
    out.mkdir(parents=True)
    shutil.copyfile(original.PRE / 'input.elf', out / 'input.elf')
    shutil.copyfile(probe, out / 'probe.tcl')
    original.save(out / 'source-pins.json', pins)
    command = [str(image), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(out / 'input.elf'), '+TESTCASE=masklogical_same_source_repair',
        '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'),
        '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'),
        '-cm_name', 'masklogical_same_source_repair', '-ucli', '-do', str(out / 'probe.tcl')]
    original.save(out / 'command.json', dict(command=command, cwd=str(out), timeout_s=timeout_s,
        cases=68, checks=65860, build=str(build), probe=str(probe), service_persistence_required=False))
    started = time.monotonic()
    result = dict(status='RUNNING', coverage_admitted=False)
    original.save(out / 'status.json', result)
    try:
        with (out / 'console.log').open('x') as log:
            with subprocess.Popen(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                                  start_new_session=True) as proc:
                original.save(out / 'started.json', dict(pid=proc.pid, image=str(image),
                    image_sha256=original.digest(image), elf_sha256=original.ELF_SHA, epoch=time.time()))
                try:
                    code = proc.wait(timeout=timeout_s)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL)
                        proc.wait()
                    original.save(out / 'simulation-status.json', dict(status='TIMEOUT',
                        returncode=proc.returncode, elapsed_s=time.monotonic()-started, pid=proc.pid))
                    raise
                original.save(out / 'simulation-status.json', dict(status='EXITED', returncode=code,
                    elapsed_s=time.monotonic()-started, pid=proc.pid))
                original.require(code == 0, f'Simulator exited {code}')
        original.check_pins(pins)
        original.require(original.digest(out / 'input.elf') == original.ELF_SHA, 'Runtime ELF changed')
        result = original.audit(out)
        original.check_pins(pins)
        result['artifacts'] = {str(p): original.digest(p) for p in out.iterdir() if p.is_file()}
    except Exception as error:
        result = dict(status='TIMEOUT' if isinstance(error, subprocess.TimeoutExpired) else 'FAIL',
                      reason=f'{type(error).__name__}: {error}', coverage_admitted=False)
    result['elapsed_s'] = time.monotonic() - started
    original.save(out / 'status.json', result)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout-s', type=int, required=True,
                        help='Wall budget derived from full-ELF instruction count and measured simulation rate')
    parser.add_argument('--probe', type=Path, default=DEFAULT_PROBE)
    args = parser.parse_args()
    raise SystemExit(execute(args.build.resolve(), args.output.resolve(), args.timeout_s, args.probe.resolve()))
