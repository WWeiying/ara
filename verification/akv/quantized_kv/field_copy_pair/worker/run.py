#!/usr/bin/env python3
"""One direct-owned reviewed side; offline preflight by default."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
import os
from pathlib import Path
import signal
import subprocess
import sys
from types import SimpleNamespace

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PAIR = HERE.parent
MAX_TIMEOUT = 10800
SIDES = ('baseline', 'candidate')
REVISIONS = dict(baseline='839a03622130dba7299155f1ccd55c004a6b676a',
                 candidate='083d4ed84f47905a675566cc4c459d2e70549ac0')


def load(name, path, expected):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('Helper identity drift: '+str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


accepted = load('field_copy_pair_accepted_image', PAIR.parent/'canonical_q4_hsb/run.py',
                '715dfe948977163c993e6bc0b587c62cec5d15d13f1191e6d8104da41b2bcf79')
s = accepted.s
sys.path.insert(0, str(HERE))
import compare as comparison


def fields(report, expected, context):
    s.require(all(type(report.get(k)) is type(v) and report[k] == v for k, v in expected.items()),
              'Wrong '+context+' fields')


def path(value):
    p = Path(value)
    s.require(p.is_absolute() and p == p.resolve(strict=True), 'Need absolute nonaliased input: '+str(p))
    return p


def run_command(argv, log, timeout, env, started):
    """Original bounded process-group cleanup with a private cwd."""
    with log.open('x') as stream:
        process = subprocess.Popen(argv, cwd=log.parent, stdout=stream,
            stderr=subprocess.STDOUT, env=env, start_new_session=True)
        try:
            started(process.pid)
            return process.wait(timeout=timeout)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except (subprocess.TimeoutExpired, ProcessLookupError):
                pass
            finally:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
            raise


private_s = SimpleNamespace(**vars(s))
private_s.run_command = run_command


class Execution(accepted.Execution):
    execute = accepted.canonical.build.clone(accepted.Execution.execute, {'s': private_s})


def own_pins():
    paths = [*HERE.glob('*.py'), HERE/'README.md', PAIR/'PLAN.md', Path(sys.executable).resolve(),
             ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh', *s.script_files()]
    paths += [Path('/usr/bin')/name for name in ('bash', 'readelf', 'awk', 'sed', 'grep', 'tail', 'head')]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).is_file() and Path(name).resolve().is_relative_to(ROOT):
            paths.append(Path(name).resolve())
    return s.hashes(paths)


def prepare_inputs(args):
    import admission
    return admission.prepare_inputs(args)


def simulation_command(simv, elf, work):
    return [simv, '-no_save', '-l', work/'run.vcs.log', '+PRELOAD='+str(elf),
        '+TESTCASE=quant_threeway_attention', '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
        '+VECTOR_TRACE='+str(work/'vector_trace.csv'),
        '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']


def uvm_command(simv, elf, work):
    return [sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
        '--require-backend', '--require-axi', '--require-axi-write', '--vector-trace',
        work/'vector_trace.csv', '--log', work/'run.vcs.log', '--simv', simv, '--elf', elf,
        '--output', work/'uvm_result.json']


def checked_raw(work, program):
    parsed = accepted.checker.check_log((work/'run.vcs.log').read_text(), 1,
                                       Path(program['golden']).read_bytes(), accepted.RTL.read_text())
    comparison.validate(parsed)
    return parsed


def independent_protocol(work, program, image):
    accepted.protocol(work, program['elf_sha256'], image)


def fresh_output(output, inputs):
    output = output.absolute()
    s.require(output == output.resolve() and not output.exists() and not any(
        output.is_relative_to(p) or p.is_relative_to(output) for p in inputs), 'Use a fresh independent output')
    s.require(not any(output.is_relative_to(ROOT/p) for p in ('hardware', 'software', 'verification/akv')),
              'Output must not overlap source directories')
    return output


def run(args):
    s.require(type(args.timeout) is int and 1 <= args.timeout <= MAX_TIMEOUT, 'Timeout must be 1..10800 seconds')
    s.require(args.side in SIDES, 'Need baseline or candidate side')
    review_path, build = path(args.review), path(args.soc_build)
    output = fresh_output(args.output, [build, PAIR, review_path.parent])
    output.mkdir(parents=True)
    work = output/'work'
    work.mkdir()
    owner = Execution(output)
    owner.env.update(PATH='/usr/bin:/bin', READELF='/usr/bin/readelf', LC_ALL='C')
    for key in ('BASH_ENV', 'ENV', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONINSPECT'):
        owner.env.pop(key, None)
    runtime = {'LD_LIBRARY_PATH': owner.env.get('LD_LIBRARY_PATH')}
    owner.state.update(side=args.side, simulations_launched=0, timeout_seconds=args.timeout,
                       simv_cwd=str(work), direct_service_ownership_required=True)
    owner.save()
    result = dict(schema='field_copy_pair_side_v1', side=args.side, revision=REVISIONS[args.side],
                  execution='NOT_RUN', performance_acceptance=False, independent_parent_review_required=True,
                  historical_timing_used=False, independent_protocol_checked=False, post_pins_match=False)
    try:
        prepared, soc, pins, image, review = prepare_inputs(args)
        s.require(review['runtime_environment'] == runtime, 'Reviewed loader environment differs')
        program = prepared['programs'][args.side]
        elf, simv = Path(program['elf']), Path(soc['simv'])
        owner.state.update(elf=str(elf), simv=str(simv))
        s.atomic_json(output/'runtime-environment.json', runtime)
        runtime_sha = s.digest(output/'runtime-environment.json')
        s.atomic_json(output/'source-pins.json', pins)
        pins_sha = s.digest(output/'source-pins.json')
        result.update(elf=str(elf), elf_sha256=program['elf_sha256'], image_pins=image,
            review_sha256=args.review_sha256, prepared_pair_sha256=review['prepared_pair_sha256'],
            source_pins_sha256=pins_sha, runtime_environment=runtime, runtime_environment_sha256=runtime_sha,
            soc_build=str(build), soc_build_sha256=accepted.SOC_SHA, simulator_flags='ORIGINAL_VECTOR_WORK_UVM_NO_COMMIT')

        def identity():
            s.require(s.digest(output/'source-pins.json') == pins_sha and
                      s.digest(output/'runtime-environment.json') == runtime_sha and
                      {'LD_LIBRARY_PATH': owner.env.get('LD_LIBRARY_PATH')} == runtime, 'Worker receipt/environment drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, 'Actual canonical image drift')

        def manifest(stage):
            identity()
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                simv.parent/'vcs_source_manifest.json', '--check'], output/(stage+'.log'), 300,
                stage.upper().replace('-', '_'))
            identity()

        identity()
        if not args.execute_reviewed_side:
            result.update(state='FIELD_COPY_SIDE_PREFLIGHT_NOT_RUN', simulations_launched=0, post_pins_match=True)
        else:
            manifest('manifest-before')
            owner.execute(['bash', ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh', simv.parent, elf],
                          output/'image-contract.log', 180, 'IMAGE_CONTRACT')
            identity()
            owner.state['simulations_launched'] = 1
            owner.save()
            result['execution'] = 'SIMULATION_ATTEMPTED'
            owner.execute(simulation_command(simv, elf, work), work/'console.log', args.timeout, 'RUNNING')
            identity()
            raw_pins = s.hashes([work/'run.vcs.log', work/'vector_trace.csv'])
            result['raw_replay'] = checked_raw(work, program)
            owner.execute(uvm_command(simv, elf, work), work/'checker.log', 600, 'CHECKING')
            independent_protocol(work, program, image)
            s.verify_pins(raw_pins)
            manifest('manifest-after')
            independent_protocol(work, program, image)
            identity()
            result.update(state='FIELD_COPY_SIDE_CHECKED', execution='SIMULATED_ONCE', simulations_launched=1,
                          simulator_exit_code=0, post_pins_match=True, independent_protocol_checked=True,
                          output_words_checked=4608, mirrored_calls_checked=6, native_commands_checked=16)
        identity()
        result['evidence_sha256'] = s.hashes(p for p in output.rglob('*') if p.is_file() and
                                            p.name not in ('status.json', 'result.json'))
        s.atomic_json(output/'result.json', result)
        owner.state['state'] = result['state']
        return result
    except BaseException as exc:
        state = ('TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else
                 'INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL')
        result.update(state=state, error=repr(exc), post_pins_match=False,
                      simulations_launched=owner.state['simulations_launched'])
        owner.state.update(state=state, error=repr(exc))
        result['partial_evidence_sha256'] = s.hashes(p for p in output.rglob('*') if p.is_file() and
                                                    p.name not in ('status.json', 'result.json'))
        s.atomic_json(output/'result.json', result)
        raise
    finally:
        owner.state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        owner.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--side', choices=SIDES, required=True)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--review-sha256', required=True)
    parser.add_argument('--soc-build', type=Path, default=accepted.SOC_BUILD)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=MAX_TIMEOUT)
    parser.add_argument('--execute-reviewed-side', action='store_true')
    args = parser.parse_args()

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(args)
