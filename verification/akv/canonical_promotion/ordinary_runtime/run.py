#!/usr/bin/env python3
"""Frozen real Attention ELF on a reviewed actual-canonical image, never an overlay."""
import argparse
from datetime import datetime, timezone
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


baseline = load('canonical_runtime_baseline', HERE.parent / 'ordinary_baseline/baseline.py')
builder = load('canonical_runtime_builder', HERE.parent / 'canonical_soc/build.py')
contract = baseline.contract
old_run = load('canonical_runtime_original_command', baseline.OLD / 'run.py')
s = contract.s
Execution = contract.Execution
STATE = 'CANONICAL_SOC_BUILT_NOT_EXECUTED'
ACCEPTANCE = 'CANONICAL_ORDINARY_SAME_ELF_PASS'


def require_fields(report, status):
    wanted = dict(state=STATE, schema='canonical_soc_v1', canonical=True, source_root=str(ROOT),
                  plan_sha256=builder.PLAN_SHA, post_pins_match=True, compiler_exit_code=0,
                  execution='NOT_RUN', simulations_launched=0, performance_measured=False)
    s.require(all(type(report.get(k)) is type(v) and report[k] == v for k, v in wanted.items()),
              'Wrong canonical build receipt type/state')
    s.require(status.get('state') == STATE and 'child_pid' in status and status['child_pid'] is None and
              status.get('canonical') is True and status.get('source_root') == str(ROOT) and
              status.get('execution') == 'NOT_RUN' and type(status.get('compile_exit_code')) is int and
              status['compile_exit_code'] == 0, 'Canonical compiler is not terminal successful')


def build_dependencies(common):
    return [builder.PLAN, builder.PLAN.parent / 'coherent.patch', builder.OLD_LIST,
            *[builder.HERE / n for n in ('build.py', 'test_build.py', 'README.md')],
            Path(common.__file__), common.SOC_COMPILE_PRIOR,
            common.SOC_COMPILE_PRIOR.parent / 'vcs_source_manifest.json',
            ROOT / 'verification/ara_verify/vcs_source_manifest.py', Path(sys.executable).resolve()]


def checked_soc(directory, reviewed_sha256):
    """New canonical receipt consumer; intentionally never calls old checked_soc."""
    promoted = builder.guard()
    directory = Path(directory).resolve(strict=True)
    receipt = directory / 'result.json'
    s.require(isinstance(reviewed_sha256, str) and len(reviewed_sha256) == 64 and
              s.digest(receipt) == reviewed_sha256, 'Reviewed canonical build SHA differs')
    report, status = s.read_json(receipt), s.read_json(directory / 'status.json')
    require_fields(report, status)
    source = directory / 'source-pins.json'
    s.require(s.digest(source) == report['source_pins_sha256'], 'Canonical build source receipt drift')
    pins = s.read_json(source)
    simv = directory / 'sim/simv'
    s.require(report['simv'] == str(simv) and simv.resolve(strict=True) == simv, 'Wrong/aliased canonical image')
    image = s.hashes(s.image_files(simv))
    s.require(image == report['image_pins'] == s.read_json(directory / 'image-pins.json'),
              'Canonical image inventory drift')
    artifacts = report['artifact_pins']
    filelist = directory / 'hardware-build/vcs/bender_script_default'
    dpi = directory / 'hardware-build/work-dpi/elfloader.o'
    required = [source, directory / 'image-pins.json', directory / 'planned-command.json',
                directory / 'make.log', directory / 'make.command.json', filelist, dpi,
                directory / 'hardware-build/work-dpi/ara_dpi.so', simv.parent / 'comp.vcs.log']
    s.require(all(artifacts.get(str(p)) == s.digest(p) for p in required) and
              all(artifacts.get(p) == sha for p, sha in image.items()), 'Missing compiled artifact pin')
    s.require(s.read_json(directory / 'make.command.json')['argv'] ==
              s.read_json(directory / 'planned-command.json'), 'Actual make command differs from plan')
    for row in promoted['files']:
        s.require(pins.get(str(ROOT / row['target'])) == row['after_sha256'], 'Missing promoted target source pin')
    for relative, sha in builder.LOCKED.items():
        s.require(pins.get(str(ROOT / relative)) == sha, 'Missing locked dependency input')
    expected = directory / 'expected-sources.f'
    s.require(pins.get(str(expected)) == s.digest(expected) and s.digest(builder.OLD_LIST) == builder.OLD_LIST_SHA,
              'Canonical graph reference/input pin drift')
    common = builder.load_common()
    s.require(all(pins.get(str(path)) == s.digest(path) for path in build_dependencies(common)),
              'Missing exact build helper/tool/compile-provenance input pin')
    wanted_graph = builder.expected_graph(builder.OLD_LIST.read_text())
    s.require(builder.tokens(expected.read_text()) == wanted_graph, 'Wrong pre-build source graph')
    builder.check_graph(filelist.read_text(), wanted_graph, common.SOC_REPEAT_HASHES)
    config = builder.check_config(simv.parent / 'simulator.conf')
    s.require(config == report['config'], 'Canonical configuration receipt differs')
    manifest_path = simv.parent / 'vcs_source_manifest.json'
    manifest = s.read_json(manifest_path)
    extras = [dpi, *builder.UVM]
    s.require(manifest.get('schema_version') == 1 and manifest.get('repo_root') == str(ROOT) and
              manifest.get('filelist') == str(filelist) and manifest.get('extra_sources') == list(map(str, extras)),
              'Manifest must describe actual canonical root and exact native UVM/DPI inputs')
    actual = common.latency.tools.collect(filelist, ROOT, extras)
    s.require(manifest['files'] == actual, 'Canonical compiled source/header inventory drift')
    before = common.latency.tools.collect(expected, ROOT, list(builder.UVM))
    s.require(all(pins.get(row['path']) == row['sha256'] for row in before), 'Incomplete pre-build source pins')
    for row in actual:
        if row['path'] not in (str(filelist), str(dpi)):
            s.require(pins.get(row['path']) == row['sha256'], 'Compiled dependency was not pinned before build')
    vcs = Path(report['lint']['command_argv'][0])
    s.require(vcs.is_absolute() and pins.get(str(vcs)) == s.digest(vcs), 'Unpinned compiler identity')
    lint = common.check_soc_compile((simv.parent / 'comp.vcs.log').read_text(), 0,
                                    builder.expected_vcs(directory, vcs), ROOT)
    s.require(lint == report['lint'], 'Canonical compile admission/raw log differs')
    s.merge_pins(pins, artifacts)
    s.merge_pins(pins, s.hashes([receipt, directory / 'status.json', source]))
    s.verify_pins(pins)
    return report, pins, image


def own_pins():
    files = [*HERE.glob('*.py'), HERE / 'README.md', Path(sys.executable).resolve(),
             ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh', *s.script_files()]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).resolve().is_relative_to(ROOT) and Path(name).is_file():
            files.append(Path(name).resolve())
    return s.hashes(files)


def verify_current(soc, image, pins):
    builder.guard()
    s.verify_pins(pins)
    simv = Path(soc['simv'])
    s.require(s.hashes(s.image_files(simv)) == image, 'Runtime image inventory changed')
    builder.load_common().verify_manifest(simv.parent / 'vcs_source_manifest.json')


def run(args):
    old_run.validate_timeout(args.timeout)
    build = args.soc_build.resolve(strict=True)
    output = args.output.resolve()
    inputs = (build, contract.DEFAULT_BUILD, contract.DEFAULT_BASELINE, HERE)
    s.require(not output.exists() and not any(output.is_relative_to(p) or p.is_relative_to(output) for p in inputs),
              'Use a fresh independent runtime output')
    output.mkdir(parents=True)
    work = output / 'work'
    work.mkdir()
    owner = Execution(output)
    owner.state.update(soc_build=str(build), expected_soc_sha256=args.expected_soc_sha256,
                       timeout_seconds=args.timeout, simulations_launched=0)
    owner.save()
    result = {}
    try:
        # Canonical admission fails before consuming a baseline or executing any phase.
        soc, pins, image = checked_soc(build, args.expected_soc_sha256)
        report, old, old_records, old_pins = baseline.Consumer().checked_baseline()
        s.merge_pins(pins, old_pins)
        s.merge_pins(pins, own_pins())
        simv, elf = Path(soc['simv']), Path(report['elf'])
        owner.state.update(simv=str(simv), elf=str(elf))
        s.atomic_json(output / 'source-pins.json', pins)
        receipt = s.digest(output / 'source-pins.json')

        def identity():
            s.require(s.digest(output / 'source-pins.json') == receipt, 'Runtime receipt drift')
            verify_current(soc, image, pins)

        identity()
        if args.preflight_only:
            result = dict(state='CANONICAL_ORDINARY_PREFLIGHT_NOT_RUN', execution='NOT_RUN',
                          simulations_launched=0, source_pins_sha256=receipt, post_pins_match=True,
                          elf_sha256=report['elf_sha256'], soc_build_sha256=args.expected_soc_sha256)
        else:
            def manifest(stage):
                owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                    simv.parent / 'vcs_source_manifest.json', '--check'], output / (stage + '.log'),
                    300, stage.upper().replace('-', '_'))

            manifest('manifest-before')
            owner.execute(['bash', ROOT / 'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                simv.parent, elf, 'akv_v2'], output / 'image-contract.log', 180, 'IMAGE_CONTRACT')
            identity()
            owner.state['simulations_launched'] = 1
            owner.execute(old_run.simulation_command(simv, elf, work), work / 'console.log', args.timeout, 'RUNNING')
            new, new_records = contract.raw(output)
            result['raw_replay'] = new
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
                '--require-axi', '--require-axi-write', '--vector-trace', work / 'vector_trace.csv',
                '--log', work / 'run.vcs.log', '--simv', simv, '--elf', elf,
                '--output', work / 'uvm_result.json'], work / 'checker.log', 600, 'CHECKING')
            contract.protocol(output, report['elf_sha256'], image)
            manifest('manifest-after')
            identity()
            closed = [output / 'source-pins.json']
            closed += [work / n for n in ('run.vcs.log', 'vector_trace.csv', 'commit_trace.csv',
                'uvm_result.json', 'console.log', 'checker.log')]
            closed += [output / n for n in ('manifest-before.log', 'manifest-after.log', 'image-contract.log')]
            closed += sorted(output.glob('*.command.json')) + sorted(work.glob('*.command.json'))
            result.update(execution='SIMULATED_ONCE', simulations_launched=1, simulator_exit_code=0,
                post_pins_match=True, independent_protocol_checked=True, source_pins_sha256=receipt,
                elf_sha256=report['elf_sha256'], baseline=str(contract.DEFAULT_BASELINE),
                frozen_elf_build=str(contract.DEFAULT_BUILD), soc_build=str(build),
                soc_build_sha256=args.expected_soc_sha256, image_pins=image, evidence_sha256=s.hashes(closed))
            # Preserve functional evidence even if strict resource nonregression fails.
            comparison = contract.compare(old, new, old_records, new_records)
            result.update(state=comparison['state'], comparison=comparison,
                acceptance=ACCEPTANCE if comparison['state'] == 'PASS' else 'COMPLETE_CALL_REGRESSION',
                model_execution=False, production_deployment_approved=False)
        identity()
        s.atomic_json(output / 'result.json', result)
        owner.state['state'] = result['state']
        return result
    except BaseException as exc:
        state = 'TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else 'INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL'
        owner.state.update(state=state, error=repr(exc))
        result.update(state=state, error=repr(exc), simulations_launched=owner.state['simulations_launched'])
        s.atomic_json(output / 'result.json', result)
        raise
    finally:
        owner.state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        owner.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--soc-build', type=Path, required=True)
    parser.add_argument('--expected-soc-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=9000)
    parser.add_argument('--preflight-only', action='store_true')
    args = parser.parse_args()

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    sys.exit(0 if run(args)['state'] in ('PASS', 'CANONICAL_ORDINARY_PREFLIGHT_NOT_RUN') else 1)
