"""Full native-printing successor; unchanged 68-case independent oracle."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

import run_masklogical_same_source_repair as oracle
import run_masklogical_same_source_repair_v2 as binding

ROOT = Path(__file__).resolve().parents[2]
PRE = ROOT / 'verification/out/masklogical-same-source-native-preflight-20261008-01'
ELF_SHA = '43d5d7b1c9b14a0c73f1cd6ea879164eb74d83f7633e232d7a443f52e9ad259e'
ORIGINAL_MATRIX_SHA = '858b384be8b936ad8c8acd30d22775235cb0bffbf3e8e475ef600eac50099931'


def execute(build, out, timeout_s):
    oracle.require(timeout_s > 0 and not out.exists(), 'Positive budget and fresh output required')
    image, pins = binding.bind_build(build)
    manifest_path = PRE / 'manifest.json'
    manifest = json.loads(manifest_path.read_text())
    oracle.require(manifest['cases'] == 68 and manifest['expected_checks'] == 65860 and
        manifest['original_matrix_sha256'] == ORIGINAL_MATRIX_SHA and
        manifest['native_stdio_gate']['status'] == 'PASS' and not manifest['startup_changed'],
        'Native successor changed computation, startup or print contract')
    for key in ('source_pins', 'tool_pins', 'binary_pins'):
        pins.update(manifest[key])
    for path in (Path(__file__), Path(binding.__file__), Path(oracle.__file__), oracle.PROBE,
                 Path(oracle.wave.__file__), Path(oracle.canonical.__file__),
                 oracle.canonical.CONVERTER, manifest_path, PRE / 'native-stdio-gate.json'):
        pins[str(path)] = oracle.digest(path)
    oracle.check_pins(pins)
    oracle.require(oracle.digest(PRE / 'input.elf') == ELF_SHA and ELF_SHA != oracle.ELF_SHA,
                   'Native successor ELF identity differs')
    out.mkdir(parents=True)
    shutil.copyfile(PRE / 'input.elf', out / 'input.elf')
    # Only the cold probe is reused. New linking changes PCs/cache timing;
    # the old fixed restart window was already proved on build04 separately.
    shutil.copyfile(oracle.PROBE, out / 'probe.tcl')
    oracle.save(out / 'source-pins.json', pins)
    command = [str(image), '-l', 'run.vcs.log', '+NO_FSDB', '+ntb_random_seed=1',
        '+PRELOAD=' + str(out / 'input.elf'), '+TESTCASE=masklogical_same_source_native',
        '+COMMIT_TRACE=' + str(out / 'commit_trace.csv'),
        '+VECTOR_TRACE=' + str(out / 'vector_trace.csv'),
        '-cm', 'line+cond+fsm+tgl+branch', '-cm_dir', str(out / 'code.vdb'),
        '-cm_name', 'masklogical_same_source_native', '-ucli', '-do', str(out / 'probe.tcl')]
    oracle.save(out / 'command.json', dict(command=command, cwd=str(out), timeout_s=timeout_s,
        cases=68, checks=65860, build=str(build), elf_sha256=ELF_SHA,
        superseded_elf_sha256=oracle.ELF_SHA, original_oracle_unchanged=True))
    started = time.monotonic()
    oracle.save(out / 'status.json', dict(status='RUNNING', coverage_admitted=False))
    try:
        with (out / 'console.log').open('x') as log:
            with subprocess.Popen(command, cwd=out, stdout=log, stderr=subprocess.STDOUT,
                                  start_new_session=True) as proc:
                oracle.save(out / 'started.json', dict(pid=proc.pid, epoch=time.time(), image=str(image),
                    image_sha256=oracle.digest(image), elf_sha256=ELF_SHA))
                try:
                    code = proc.wait(timeout=timeout_s)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGTERM)
                    try:
                        proc.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        os.killpg(proc.pid, signal.SIGKILL); proc.wait()
                    oracle.save(out / 'simulation-status.json', dict(status='TIMEOUT',
                        returncode=proc.returncode, elapsed_s=time.monotonic()-started, pid=proc.pid))
                    raise
                oracle.save(out / 'simulation-status.json', dict(status='EXITED', returncode=code,
                    elapsed_s=time.monotonic()-started, pid=proc.pid))
                oracle.require(code == 0, f'Simulator exited {code}')
        oracle.check_pins(pins)
        oracle.require(oracle.digest(out / 'input.elf') == ELF_SHA, 'Runtime ELF changed')
        result = oracle.audit(out)
        oracle.check_pins(pins)
        result.update(elf_sha256=ELF_SHA, original_oracle_unchanged=True,
                      original_matrix_sha256=ORIGINAL_MATRIX_SHA)
        result['artifacts'] = {str(p): oracle.digest(p) for p in out.iterdir() if p.is_file()}
    except Exception as exc:
        result = dict(status='TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'FAIL',
                      reason=type(exc).__name__ + ': ' + str(exc), coverage_admitted=False)
    result['elapsed_s'] = time.monotonic() - started
    oracle.save(out / 'status.json', result)
    return 0 if result['status'] == 'PASS' else 1


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout-s', type=int, required=True)
    args = p.parse_args()
    raise SystemExit(execute(args.build.resolve(), args.output.resolve(), args.timeout_s))
