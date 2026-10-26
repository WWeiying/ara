#!/usr/bin/env python3
"""Offline preflight by default; explicit reviewed execution is one bounded ABBA."""
import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]


def local(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


prep = local('grouped_pair_prepare', HERE / 'prepare.py')
check = local('grouped_pair_check', HERE / 'check.py')
EXECUTOR = HERE.parents[1] / 'field_copy_pair/worker/run.py'
prep.require(prep.sha(EXECUTOR) == '82d5848ca749dc30b634527182d22b98e7d944aa7caddc7b2322466882f8678b',
             'Frozen bounded executor changed')
original = local('grouped_pair_bounded_executor', EXECUTOR)
accepted, s = original.accepted, original.s


def prepare_inputs(args):
    s.require(prep.sha(args.build) == args.build_sha256, 'Reviewed build receipt identity')
    program, pins = prep.checked_build(args.build)
    soc, sources, image = accepted.canonical.checked_soc(args.soc_build, accepted.SOC_SHA)
    s.merge_pins(pins, sources)
    s.merge_pins(pins, image)
    paths = [p for p in HERE.iterdir() if p.is_file()]
    paths += [accepted.RTL, *s.script_files(), Path(sys.executable).resolve(),
              ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh']
    paths += [Path('/usr/bin') / n for n in ('bash', 'readelf', 'awk', 'sed', 'grep', 'head', 'tail')]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).is_file() and Path(name).resolve().is_relative_to(ROOT):
            paths.append(Path(name).resolve())
    s.merge_pins(pins, s.hashes(paths))
    s.verify_pins(pins)
    return program, soc, pins, image


def simulation_command(simv, elf, work):
    return [simv, '-no_save', '-l', work / 'run.vcs.log', '+PRELOAD=' + str(elf),
            '+TESTCASE=quant_grouped_pv_pair', '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
            '+VECTOR_TRACE=' + str(work / 'vector_trace.csv'),
            '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']


def run(args):
    s.require(type(args.timeout) is int and 1 <= args.timeout <= 10800, 'Timeout must be 1..10800')
    args.build = args.build.resolve(strict=True)
    args.soc_build = args.soc_build.resolve(strict=True)
    output = original.fresh_output(args.output, [HERE, args.build.parent, args.soc_build])
    output.mkdir(parents=True)
    work = output / 'work'
    work.mkdir()
    owner = original.Execution(output)
    owner.env.update(PATH='/usr/bin:/bin', READELF='/usr/bin/readelf', LC_ALL='C')
    for key in ('BASH_ENV', 'ENV', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONINSPECT'):
        owner.env.pop(key, None)
    owner.state.update(simulations_launched=0, timeout_seconds=args.timeout)
    owner.save()
    result = dict(schema='grouped_pv_pair_run_v1', execution='NOT_RUN', whole_model=False,
                  hardware_only=False, deployment_approved=False, numerical_host_recompute=False)
    try:
        program, soc, pins, image = prepare_inputs(args)
        elf, simv = Path(program['elf']), Path(soc['simv'])
        owner.state.update(elf=str(elf), simv=str(simv))
        s.atomic_json(output / 'source-pins.json', pins)
        pin_sha = s.digest(output / 'source-pins.json')
        result.update(elf=str(elf), elf_sha256=program['elf_sha256'], image_pins=image,
                      source_pins_sha256=pin_sha, build=str(args.build), build_sha256=args.build_sha256,
                      soc_build=str(args.soc_build), soc_build_sha256=accepted.SOC_SHA)

        def identity():
            s.require(s.digest(output / 'source-pins.json') == pin_sha, 'Worker pin map drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, 'Image inventory drift')

        def manifest(stage):
            identity()
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                           simv.parent / 'vcs_source_manifest.json', '--check'], output / (stage+'.log'),
                          300, stage.upper().replace('-', '_'))
            identity()

        identity()
        if not args.execute_reviewed:
            result.update(state='PREFLIGHT_NOT_RUN', simulations_launched=0,
                          independent_protocol_checked=False, performance_measured=False)
        else:
            manifest('manifest-before')
            owner.execute(['bash', ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                           simv.parent, elf], output / 'image-contract.log', 180, 'IMAGE_CONTRACT')
            identity()
            argv = simulation_command(simv, elf, work)
            owner.state['simulations_launched'] = 1
            owner.save()
            owner.execute(argv, work / 'console.log', args.timeout, 'RUNNING')
            result['raw_replay'] = check.check_log((work / 'run.vcs.log').read_text(),
                Path(program['golden']).read_bytes(), accepted.RTL.read_text(), argv)
            # UVM always sees the actual unfiltered simulator log and trace.
            owner.execute(original.uvm_command(simv, elf, work), work / 'checker.log', 600, 'CHECKING')
            accepted.protocol(work, program['elf_sha256'], image)
            manifest('manifest-after')
            result.update(state='PASS', execution='SIMULATED_ONCE', simulations_launched=1,
                          simulator_exit_code=0, independent_protocol_checked=True,
                          performance_measured=True)
        identity()
        result['post_pins_match'] = True
        # Active stdout/status can change after return and are not sealed evidence.
        result['evidence_sha256'] = s.hashes(p for p in output.rglob('*') if p.is_file() and
                                           p.name not in ('worker.log', 'status.json', 'result.json'))
        s.atomic_json(output / 'result.json', result)
        owner.state['state'] = result['state']
        return result
    except BaseException as exc:
        state = ('TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else
                 'INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL')
        result.update(state=state, error=repr(exc), post_pins_match=False,
                      simulations_launched=owner.state['simulations_launched'])
        s.atomic_json(output / 'result.json', result)
        owner.state.update(state=state, error=repr(exc))
        raise
    finally:
        owner.state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        owner.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--build', type=Path, required=True, help='Fresh pair build.json')
    parser.add_argument('--build-sha256', required=True)
    parser.add_argument('--soc-build', type=Path, default=accepted.SOC_BUILD)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=10800)
    parser.add_argument('--execute-reviewed', action='store_true')
    args = parser.parse_args()

    def interrupted(signum, _frame):
        raise InterruptedError(f'Signal {signum}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(args)
