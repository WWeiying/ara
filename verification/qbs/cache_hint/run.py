#!/usr/bin/env python3
"""Run cache-hint measurement on the accepted retirement SoC image."""
import argparse
from pathlib import Path
import signal
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE.parent/'tile_boundary'))
from run_ordinary import checked_review, runtime
sys.path.insert(0, str(HERE))
from check import check_log


def run(args):
    s = runtime.s
    out = args.output.resolve()
    s.require(out.is_relative_to(ROOT/'verification/out') and not out.exists(), 'Fresh output required')
    out.mkdir()
    work = out/'work'
    work.mkdir()
    owner = runtime.Execution(out)
    owner.env['PYTHONPATH'] = str(ROOT/'verification')
    owner.env['PYTHONDONTWRITEBYTECODE'] = '1'
    owner.state.update(simulations_launched=0)
    owner.save()
    result = dict(state='PREFLIGHT', performance_measured=False)
    try:
        soc, pins, image = checked_review(args.soc_build, args.expected_soc_sha256)
        build = args.build.resolve(strict=True)
        report = s.read_json(build/'build.json')
        s.require(report['state'] == 'BUILT_NOT_EXECUTED' and report.get('cache_hint') is True
                  and report['commands_per_trial'] == 0 and report['reused_objects'] == 0,
                  'Wrong experiment build')
        s.require(s.digest(build/'source-pins.json') == report['source_pins_sha256'], 'Build pins')
        s.merge_pins(pins, s.read_json(build/'source-pins.json'))
        s.merge_pins(pins, report['artifacts'])
        elf, golden = Path(report['elf']), Path(report['golden'])
        s.require(s.digest(elf) == report['elf_sha256'] and
                  s.digest(golden) == report['golden_sha256'], 'ELF/golden identity')
        files = [build/'build.json', Path(__file__), HERE/'check.py']
        for module in tuple(sys.modules.values()):
            name = getattr(module, '__file__', None)
            if name and Path(name).is_file() and Path(name).resolve().is_relative_to(ROOT):
                files.append(Path(name).resolve())
        s.merge_pins(pins, s.hashes(files))
        s.atomic_json(out/'source-pins.json', pins)
        simv = Path(soc['simv'])
        def identity():
            s.verify_pins(pins)
            runtime.verify_current(soc, image, pins)
        identity()
        if args.execute:
            owner.execute(['bash', ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                           simv.parent, elf], out/'image-contract.log', 180, 'IMAGE_CONTRACT')
            owner.state['simulations_launched'] = 1
            owner.save()
            owner.execute([simv, '-no_save', '-l', work/'run.vcs.log', '+PRELOAD='+str(elf),
                '+TESTCASE=cache_hint', '+NO_FSDB', '+NO_INSTR_TRACE',
                '+VECTOR_TRACE='+str(work/'vector_trace.csv'),
                '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
                work/'console.log', args.timeout, 'RUNNING')
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                '--require-backend', '--require-axi', '--require-axi-write', '--vector-trace',
                work/'vector_trace.csv', '--log', work/'run.vcs.log', '--simv', simv,
                '--elf', elf, '--output', work/'uvm_result.json'], work/'checker.log', 600, 'CHECKING')
            measured = check_log((work/'run.vcs.log').read_text(), golden.read_bytes())
            uvm = s.read_json(work/'uvm_result.json')
            s.require(uvm['status'] == 'PASS' and not uvm.get('issues'), 'Protocol check failed')
            result.update(state='PASS', measured=measured, performance_measured=True)
        else:
            result['state'] = 'PREFLIGHT_NOT_RUN'
        identity()
        result.update(post_pins_match=True, elf_sha256=report['elf_sha256'], image_pins=image,
                      source_pins_sha256=s.digest(out/'source-pins.json'))
    except BaseException as exc:
        result.update(state='FAIL', error=repr(exc))
        raise
    finally:
        s.atomic_json(out/'result.json', result)
        owner.state.update(state=result['state'], child_pid=None)
        owner.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    parser.add_argument('--soc-build', type=Path, required=True)
    parser.add_argument('--expected-soc-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=5400)
    parser.add_argument('--execute', action='store_true')
    args = parser.parse_args()
    if not 1 <= args.timeout <= 10800:
        parser.error('timeout must be 1..10800')
    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(args)
