#!/usr/bin/env python3
"""Directly owned VCS evaluation on the accepted, unchanged area-baseline image."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CHAIN = HERE.parent/'chain_profile'
sys.path.insert(0, str(CHAIN))
from build_soc import OUT, digest, execute, require, save, verify
from run_case import checked_soc, checked_software, successful_log


def combine(first, second):
    result = dict(first)
    for path, sha in second.items():
        require(path not in result or result[path] == sha, 'Conflicting input identity: '+path)
        result[path] = sha
    return result


def load_checker(kind):
    require(kind in ('qwen3_abba', 'regression', 'boundary'), 'Unknown evaluation kind')
    path = HERE/'check.py' if kind == 'qwen3_abba' else HERE/kind/'check.py'
    require(path.is_file(), 'Reviewed checker is not prepared')
    spec = importlib.util.spec_from_file_location('akv_pair_'+kind+'_checker', path)
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(path.parent))
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    require(callable(getattr(module, 'check_run', None)) and
            callable(getattr(module, 'check_vector_workcounts', None)),
            'Full numerical/work and independent instruction-work gates required')
    return path, module


def run(args):
    socdir, build = args.soc_build.resolve(strict=True), args.build.resolve(strict=True)
    out = args.output.resolve()
    require(not out.exists() and out.is_relative_to(OUT.resolve()) and
            not out.is_relative_to(socdir) and not out.is_relative_to(build), 'Fresh independent output required')
    require(1 <= args.timeout <= 10800, 'Evaluation timeout must be at most three hours')
    out.mkdir()
    work = out/'work'
    work.mkdir()
    statusfile = out/'status.json'
    status = dict(state='PREFLIGHT', kind=args.kind, owner_pid=os.getpid(), child_pid=None,
                  started=datetime.now(timezone.utc).isoformat())
    result = dict(state='PREFLIGHT', performance_measured=False, whole_model=False,
                  deployment_approved=False, hardware_changed=False)
    save(statusfile, status)
    try:
        soc, pins = checked_soc(socdir)
        software, extra = checked_software(build)
        pins = combine(pins, extra)
        checker_path, checker = load_checker(args.kind)
        helper_pins = {str(p): digest(p) for p in (Path(__file__), checker_path,
                       CHAIN/'run_case.py', CHAIN/'build_soc.py',
                       ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh')}
        for p in (ROOT/'verification/ara_verify').rglob('*.py'):
            helper_pins[str(p)] = digest(p)
        pins = combine(pins, helper_pins)
        save(out/'source-pins.json', pins)
        verify(pins)
        simv, elf = Path(soc['simv']), Path(software['elf'])
        status.update(simv=str(simv), elf=str(elf), build=str(build), soc_build=str(socdir))
        env = os.environ.copy()
        env.update(PYTHONPATH=str(ROOT/'verification'), PYTHONDONTWRITEBYTECODE='1',
                   READELF='/usr/bin/readelf', LC_ALL='C')
        os.environ.update(env)
        execute(['bash', ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                 simv.parent, elf, 'akv_v2'], work, out/'image-contract.log', 180,
                status, statusfile, 'IMAGE_CONTRACT')
        verify(pins)
        if args.preflight_only:
            result.update(state='PREFLIGHT_PASS', note='No RTL execution or performance acceptance')
        else:
            command = [simv, '-no_save', '-l', work/'run.vcs.log', '+PRELOAD='+str(elf),
                       '+TESTCASE=akv_pair_'+args.kind, '+NO_FSDB', '+NO_INSTR_TRACE',
                       '+VECTOR_TRACE='+str(work/'vector_trace.csv'),
                       '+COMMIT_TRACE='+str(work/'commit.csv'), '+AKV_PERF', '+AKV_SUMMARY',
                       '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']
            started = time.monotonic()
            execute(command, work, work/'console.log', args.timeout, status, statusfile, 'RUNNING')
            wall = time.monotonic()-started
            log, vector = work/'run.vcs.log', work/'vector_trace.csv'
            successful_log(log.read_text())
            measured = checker.check_run(log, build)
            require(measured.get('state') == 'PASS', 'Full numerical/CSR/guard/input/work gate did not pass')
            vector_work = checker.check_vector_workcounts(vector, build)
            require(isinstance(vector_work, dict) and vector_work, 'No independently checked instruction work')
            protocol = work/'uvm_result.json'
            execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                     '--require-backend', '--require-axi', '--require-axi-write',
                     '--vector-trace', vector, '--log', log, '--simv', simv, '--elf', elf,
                     '--output', protocol], work, work/'checker.log', 600,
                    status, statusfile, 'PROTOCOL_CHECK')
            proof = json.loads(protocol.read_text())
            require(proof.get('status') == 'PASS' and proof.get('issues') == [] and
                    proof['elf_sha256'] == software['elf_sha256'] and
                    proof['log_sha256'] == digest(log) and proof['vector_trace_sha256'] == digest(vector),
                    'Independent protocol evidence/identity mismatch')
            verify(pins)
            result.update(state='PASS', performance_measured=args.kind != 'boundary', independent_protocol_checked=True,
                          post_pins_match=True, measured=measured, vector_command_work=vector_work,
                          wall_seconds=wall, artifacts={str(p): digest(p) for p in work.iterdir() if p.is_file()})
        verify(pins)
        result.update(kind=args.kind, build=str(build), soc_build=str(socdir),
                      configuration=soc['configuration'], software_sha256=software['elf_sha256'],
                      image_sha256=digest(simv), source_pins_sha256=digest(out/'source-pins.json'))
    except BaseException as exc:
        result.update(state='TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'FAIL', error=repr(exc))
        raise
    finally:
        save(out/'result.json', result)
        status.update(state=result['state'], child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        save(statusfile, status)
    print(json.dumps(dict(state=result['state'], kind=args.kind, output=str(out))), flush=True)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--soc-build', type=Path, default=OUT/'chain_soc_admitted_20261107_01')
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kind', choices=('qwen3_abba', 'regression', 'boundary'), default='qwen3_abba')
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--preflight-only', action='store_true')
    def interrupted(sig, _frame):
        raise InterruptedError('Signal '+str(sig))
    for sig in (signal.SIGINT, signal.SIGTERM):
        signal.signal(sig, interrupted)
    run(parser.parse_args())
