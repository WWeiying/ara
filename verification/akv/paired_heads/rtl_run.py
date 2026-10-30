#!/usr/bin/env python3
"""Run the reviewed paired-head ELF on the accepted existing VCS image."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / 'verification/qbs'))
from rtl_check import check_pins, check_output, check_perf, require
from run_half_scale_soc import atomic_json, digest, hashes, image_files, script_files, check_result
from run_tile_context_engine import run_command


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--timeout', type=int, default=10800)
    p.add_argument('--preflight-only', action='store_true')
    a = p.parse_args()
    require(1 <= a.timeout <= 10800, 'Timeout must be 1..10800 seconds')
    build = a.build.resolve(strict=True)
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    work = out / 'work'
    work.mkdir()
    state = dict(state='PREFLIGHT', pid=os.getpid(), child_pid=None,
                 started=datetime.now(timezone.utc).isoformat(), timeout_seconds=a.timeout)
    env = dict(os.environ, PYTHONPATH=str(ROOT / 'verification'), PYTHONDONTWRITEBYTECODE='1')
    env.pop('LLAMA_ATTN_SIM_L2_BYTES', None)
    env.pop('LD_PRELOAD', None)

    def save():
        atomic_json(out / 'status.json', state)

    def started(pid):
        state['child_pid'] = pid
        save()

    def interrupted(signum, _frame):
        raise InterruptedError('Signal ' + str(signum))

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)

    def execute(command, log, timeout):
        command = list(map(str, command))
        atomic_json(log.with_suffix('.command.json'), dict(argv=command, cwd=str(log.parent)))
        try:
            require(run_command(command, log, timeout, env, started) == 0,
                    'Command failed: ' + str(log))
        finally:
            state['child_pid'] = None
            save()

    save()
    try:
        report = check_pins(build)
        simv = Path(report['simv']).resolve(strict=True)
        elf = Path(report['elf']).resolve(strict=True)
        image = hashes(image_files(simv))
        require(image == report['accepted_image_pins'], 'Accepted image changed')
        pins = json.loads((build / 'source-pins.json').read_text())
        groups = [report['artifact_sha256'], image,
                  hashes([build / 'build.json', build / 'source-pins.json', Path(__file__),
                          HERE / 'rtl_check.py', ROOT / 'verification/akv/run_refill_overlap_probe.py',
                          ROOT / 'verification/qbs/run_tile_context_engine.py',
                          *script_files(), Path(sys.executable).resolve()])]
        for group in groups:
            for path, value in group.items():
                require(path not in pins or pins[path] == value, 'Conflicting input pin: ' + path)
                pins[path] = value

        def check_identity():
            require(hashes(map(Path, pins)) == pins, 'Execution source/image/artifact drift')

        def manifest(stage):
            execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                     simv.parent / 'vcs_source_manifest.json', '--check'], out / (stage + '.log'), 300)

        check_identity()
        atomic_json(out / 'source-pins.json', pins)
        receipt_hash = digest(out / 'source-pins.json')
        manifest('manifest-before')
        check_identity()
        if a.preflight_only:
            state['state'] = 'PREFLIGHT_PASS_NOT_RUN'
            atomic_json(out / 'result.json', dict(state=state['state'], elf_sha256=digest(elf)))
            return
        state.update(state='RUNNING', simv=str(simv), elf=str(elf))
        save()
        log, trace = work / 'run.vcs.log', work / 'vector_trace.csv'
        execute([simv, '-no_save', '-l', log, '+PRELOAD=' + str(elf),
                 '+TESTCASE=akv_paired_heads_rtl', '+NO_FSDB', '+NO_INSTR_TRACE',
                 '+AKV_PERF', '+AKV_SUMMARY', '+VECTOR_TRACE=' + str(trace),
                 '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
                work / 'console.log', a.timeout)
        state['state'] = 'CHECKING'
        save()
        text = log.read_text()
        numeric = check_output(text, report['cases'], (build / 'golden.bin').read_bytes())
        counters = check_perf(text)
        execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                 '--require-backend', '--require-axi', '--require-axi-write', '--vector-trace', trace,
                 '--log', log, '--simv', simv, '--elf', elf, '--output', work / 'uvm_result.json'],
                work / 'checker.log', 600)
        check_result(work / 'uvm_result.json', report['elf_sha256'], image)
        uvm = json.loads((work / 'uvm_result.json').read_text())
        require(uvm['log_sha256'] == digest(log) and uvm['vector_trace_sha256'] == digest(trace),
                'Independent checker log/trace mismatch')
        manifest('manifest-after')
        check_identity()
        require(digest(out / 'source-pins.json') == receipt_hash, 'Execution pin receipt changed')
        atomic_json(out / 'result.json', dict(state='PASS', numeric=numeric, hardware_totals=counters,
            scope='Focused QK independent finite-input oracle and PV canonical regression; not whole Attention or performance',
            evidence_sha256=hashes([log, trace, work / 'uvm_result.json', out / 'source-pins.json'])))
        state['state'] = 'PASS'
    except BaseException as exc:
        state.update(state='FAIL', error=repr(exc))
        atomic_json(out / 'result.json', dict(state='FAIL', error=repr(exc)))
        raise
    finally:
        state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        save()


if __name__ == '__main__':
    main()
