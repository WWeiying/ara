#!/usr/bin/env python3
"""Pinned current-image projection worker; preflight unless explicitly executed."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import signal
import subprocess
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
sys.dont_write_bytecode = True
EXECUTOR = ROOT / 'verification/akv/quantized_kv/field_copy_pair/worker/run.py'
if hashlib.sha256(EXECUTOR.read_bytes()).hexdigest() != '82d5848ca749dc30b634527182d22b98e7d944aa7caddc7b2322466882f8678b':
    raise ValueError('Bounded executor changed')
spec = importlib.util.spec_from_file_location('projection_bounded_executor', EXECUTOR)
worker = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = worker
spec.loader.exec_module(worker)
s, accepted = worker.s, worker.accepted


def run(args):
    s.require(1 <= args.timeout <= 10800, 'Timeout must be 1..10800 seconds')
    build = args.build.resolve(strict=True)
    output = args.output.absolute()
    s.require(output == output.resolve() and output.is_relative_to(ROOT / 'verification/out') and
              not output.exists() and not output.is_relative_to(build) and
              not build.is_relative_to(output), 'Need fresh independent verification/out directory')
    output.mkdir(parents=True)
    work = output / 'work'
    work.mkdir()
    owner = worker.Execution(output)
    owner.env.update(PATH='/usr/bin:/bin', READELF='/usr/bin/readelf', LC_ALL='C')
    for key in ('BASH_ENV', 'ENV', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONINSPECT'):
        owner.env.pop(key, None)
    owner.state.update(simulations_launched=0, timeout_seconds=args.timeout)
    owner.save()
    result = dict(state='PREFLIGHT', whole_model=False, full_ggml=False,
                  deployment_approved=False, performance_measured=False)
    try:
        report = json.loads((build / 'build.json').read_text())
        pins = json.loads((build / 'manifest.json').read_text())
        elf = build / 'qbs_current_projection_soc'
        s.require(report['state'] == 'READY' and s.digest(elf) == report['elf_sha256'] and
                  s.digest(build / 'manifest.json') == report['manifest_sha256'], 'Build identity drift')
        s.verify_pins(pins)
        soc, sources, image = accepted.canonical.checked_soc(accepted.SOC_BUILD, accepted.SOC_SHA)
        simv = Path(soc['simv'])
        s.merge_pins(pins, sources)
        s.merge_pins(pins, image)
        helpers = [Path(__file__), HERE/'check.py', build/'build.json', build/'manifest.json',
                   ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh', *s.script_files()]
        for module in tuple(sys.modules.values()):
            path = getattr(module, '__file__', None)
            if path and Path(path).is_file() and Path(path).resolve().is_relative_to(ROOT):
                helpers.append(Path(path).resolve())
        s.merge_pins(pins, s.hashes(helpers))
        s.atomic_json(output/'source-pins.json', pins)

        def identity():
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, 'Image drift')

        def manifest(stage):
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest',
                           '--output', simv.parent/'vcs_source_manifest.json', '--check'],
                          output/(stage+'.log'), 300, stage.upper())
            identity()

        identity()
        result.update(build=str(build), elf_sha256=report['elf_sha256'], image_pins=image,
                      source_pins_sha256=s.digest(output/'source-pins.json'))
        if args.execute_reviewed:
            manifest('manifest-before')
            owner.execute(['bash', ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                           simv.parent, elf], output/'image-contract.log', 180, 'IMAGE_CONTRACT')
            command = [simv, '-no_save', '-l', work/'run.vcs.log', '+PRELOAD='+str(elf),
                       '+TESTCASE=q8k_current_projection', '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
                       '+VECTOR_TRACE='+str(work/'vector_trace.csv'),
                       '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']
            owner.state['simulations_launched'] = 1
            owner.save()
            owner.execute(command, work/'console.log', args.timeout, 'RUNNING')
            owner.execute(worker.uvm_command(simv, elf, work), work/'uvm-check.log', 600, 'UVM_CHECK')
            accepted.protocol(work, report['elf_sha256'], image)
            owner.execute([sys.executable, '-B', HERE/'check.py', '--build', build,
                           '--log', work/'run.vcs.log', '--trace', work/'vector_trace.csv',
                           '--uvm', work/'uvm_result.json'], work/'slice-check.json', 600, 'SLICE_CHECK')
            checked = json.loads((work/'slice-check.json').read_text())
            s.require(checked['state'] == 'PASS', 'Slice check failed')
            manifest('manifest-after')
            result.update(state='PASS', measured=checked, performance_measured=True)
        else:
            result['state'] = 'PREFLIGHT_NOT_RUN'
        identity()
        result['post_pins_match'] = True
        owner.state['state'] = result['state']
    except BaseException as exc:
        result.update(state='TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'FAIL', error=repr(exc))
        owner.state.update(state=result['state'], error=repr(exc))
        raise
    finally:
        result['simulations_launched'] = owner.state['simulations_launched']
        s.atomic_json(output/'result.json', result)
        owner.state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        owner.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--execute-reviewed', action='store_true')
    def interrupted(signum, _frame):
        raise InterruptedError(f'Signal {signum}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(parser.parse_args())
