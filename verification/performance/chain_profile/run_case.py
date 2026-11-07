#!/usr/bin/env python3
"""One frozen, independently checked VCS profiling execution."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
from build_soc import ROOT, HERE, OUT, digest, execute, require, save, verify


def checked_soc(directory):
    report = json.loads((directory / 'build.json').read_text())
    require(report.get('state') in ('CURRENT_AREA_SOC_BUILT_NOT_EXECUTED',
                                   'CURRENT_AREA_SOC_COMPILE_AUDITED_NOT_EXECUTED')
            and report.get('post_pins_match') is True, 'No frozen current SoC build')
    require(report['configuration'] == dict(schema_version=2, config='chain_profile_area_baseline',
        nr_lanes=4, vlen=1024, qbs_enabled=1, akv_enabled=1, akv_v2_enabled=1,
        sim_l2_bytes=16777216, shared_simd_multiplier=1, shared_fma=0, ideal_dispatcher=0,
        memory_note='Simulation-only capacity; no memory latency or interface-width change'),
        'Unexpected simulation configuration')
    pinfile = directory / 'source-pins.json'
    require(digest(pinfile) == report['source_pins_sha256'], 'SoC source inventory drift')
    pins = json.loads(pinfile.read_text())
    pins.update(report['image_pins'])
    pins.update({str(p): digest(p) for p in (pinfile, directory / 'build.json')})
    verify(pins)
    return report, pins


def checked_software(directory):
    report = json.loads((directory / 'build.json').read_text())
    require(report.get('state') == 'BUILT_NOT_EXECUTED', 'Software is not ready')
    pinfile = directory / 'source-pins.json'
    require(digest(pinfile) == report['source_pins_sha256'], 'Software inventory drift')
    pins = json.loads(pinfile.read_text())
    for p, value in report.get('artifacts', {}).items():
        require(p not in pins or pins[p] == value, 'Conflicting software artifact pin')
        pins[p] = value
    elf = Path(report['elf'])
    require(elf.is_relative_to(directory) and elf.is_file() and
            elf.read_bytes()[:4] == b'\x7fELF' and digest(elf) == report['elf_sha256'],
            'ELF location/identity drift')
    pins.update({str(p): digest(p) for p in (pinfile, directory / 'build.json', elf)})
    verify(pins)
    return report, pins


def successful_log(text):
    require('Core Test *** SUCCESS ***' in text and
            not re.search(r'Fatal:|Error:|Error-|\bFAILED\b', text), 'Firmware/assertion/EOC failure')


def run(args):
    socdir, build, out = args.soc_build.resolve(strict=True), args.build.resolve(strict=True), args.output.resolve()
    require(not out.exists() and out.is_relative_to(OUT.resolve()) and
            not out.is_relative_to(socdir) and not out.is_relative_to(build), 'Fresh independent run required')
    require(1 <= args.timeout <= 10800, 'Simulation timeout outside 1..10800')
    out.mkdir(parents=True)
    work = out / 'work'
    work.mkdir()
    state = dict(state='PREFLIGHT', kind=args.kind, owner_pid=os.getpid(), child_pid=None,
                 started=datetime.now(timezone.utc).isoformat())
    statusfile = out / 'status.json'
    save(statusfile, state)
    result = dict(state='PREFLIGHT', performance_measured=False, whole_model=False)
    try:
        soc, pins = checked_soc(socdir)
        software, extra = checked_software(build)
        for p, value in extra.items():
            require(p not in pins or pins[p] == value, 'Hardware/software pin conflict')
            pins[p] = value
        checker = None
        if args.kind != 'smoke':
            path = HERE / ('q6_decode' if args.kind == 'q6' else 'f16_decode') / args.checker_name
            require(args.checker_name in ('check.py', 'check_successor.py'), 'Unreviewed checker selection')
            require(path.is_file(), 'No reviewed numerical checker')
            for f in path.parent.rglob('*'):
                if f.is_file() and f.suffix in ('.py', '.h', '.c', '.S'):
                    pins[str(f)] = digest(f)
            spec = importlib.util.spec_from_file_location('chain_' + args.kind + '_check', path)
            checker = importlib.util.module_from_spec(spec)
            sys.path.insert(0, str(path.parent))
            sys.modules[spec.name] = checker
            spec.loader.exec_module(checker)
            require(callable(getattr(checker, 'check_run', None)), 'Missing check_run API')
        for f in (ROOT / 'verification/ara_verify').rglob('*.py'):
            pins[str(f)] = digest(f)
        for f in (Path(__file__), HERE / 'build_soc.py',
                  ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh'):
            pins[str(f)] = digest(f)
        save(out / 'source-pins.json', pins)
        verify(pins)
        simv, elf = Path(soc['simv']), Path(software['elf'])
        state.update(simv=str(simv), elf=str(elf), build=str(build), soc_build=str(socdir))
        env = os.environ.copy()
        env.update(PYTHONPATH=str(ROOT / 'verification'), PYTHONDONTWRITEBYTECODE='1',
                   READELF='/usr/bin/readelf', LC_ALL='C')
        os.environ.update(env)
        contract = ['bash', str(ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh'),
                    str(simv.parent), str(elf)]
        if args.kind == 'f16':
            contract.append('akv_v2')
        execute(contract, work, out / 'image-contract.log', 180, state, statusfile, 'IMAGE_CONTRACT')
        command = [str(simv), '-no_save', '-l', str(work / 'run.vcs.log'), '+PRELOAD=' + str(elf),
                   '+TESTCASE=chain_' + args.kind, '+NO_FSDB', '+NO_INSTR_TRACE',
                   '+VECTOR_TRACE=' + str(work / 'vector_trace.csv'),
                   '+COMMIT_TRACE=' + str(work / 'commit.csv'),
                   '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']
        if args.kind != 'smoke':
            command += ['+QBS_PERF', '+AKV_PERF', '+AKV_SUMMARY', '+QBS_ROOT_TRACE',
                        '+CHAIN_TRACE=' + str(work / 'boundary.csv'), '+CHAIN_WINDOW=1000']
        verify(pins)
        before = time.monotonic()
        execute(command, work, work / 'console.log', args.timeout, state, statusfile, 'RUNNING')
        wall = time.monotonic() - before
        log = work / 'run.vcs.log'
        text = log.read_text(errors='strict')
        successful_log(text)
        if args.kind == 'smoke':
            require(re.search(r'^PASSED: .*[/\\]vadd\.c!$', text, re.M), 'Missing numerical RVV smoke verdict')
            measured = dict(state='PASS', scope='RVV vadd numerical image smoke; no profiling claim')
        else:
            measured = checker.check_run(log, build)
            require(isinstance(measured, dict) and measured.get('state') == 'PASS',
                    'Full numerical/CSR/work checks did not pass')
        protocol = work / 'uvm_result.json'
        execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                 '--require-backend', '--require-axi', '--require-axi-write',
                 '--vector-trace', work / 'vector_trace.csv', '--log', log, '--simv', simv,
                 '--elf', elf, '--output', protocol], work, work / 'checker.log', 600,
                state, statusfile, 'PROTOCOL_CHECK')
        proof = json.loads(protocol.read_text())
        require(proof.get('status') == 'PASS' and proof.get('issues') == [] and
                proof['elf_sha256'] == software['elf_sha256'] and
                proof['log_sha256'] == digest(log) and
                proof['vector_trace_sha256'] == digest(work / 'vector_trace.csv'), 'Independent protocol mismatch')
        verify(pins)
        result.update(state='PASS', kind=args.kind, performance_measured=args.kind != 'smoke',
                      independent_protocol_checked=True, post_pins_match=True,
                      source_pins_sha256=digest(out / 'source-pins.json'),
                      measured=measured, build=str(build), soc_build=str(socdir),
                      software_sha256=software['elf_sha256'], image_sha256=digest(simv),
                      configuration=soc['configuration'], wall_seconds=wall,
                      artifacts={str(f): digest(f) for f in work.iterdir() if f.is_file()})
    except BaseException as exc:
        result.update(state='TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'FAIL', error=repr(exc))
        raise
    finally:
        save(out / 'result.json', result)
        state.update(state=result['state'], child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        save(statusfile, state)
    print(json.dumps(dict(state=result['state'], kind=args.kind, output=str(out))), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--soc-build', type=Path, required=True)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kind', choices=('smoke', 'q6', 'f16'), required=True)
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--checker-name', choices=('check.py', 'check_successor.py'), default='check.py')
    def interrupted(sig, _frame):
        raise InterruptedError('Signal ' + str(sig))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    run(parser.parse_args())
