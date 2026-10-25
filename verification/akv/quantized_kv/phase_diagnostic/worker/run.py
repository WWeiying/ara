#!/usr/bin/env python3
"""One reviewed three-call diagnostic; offline by default, never performance acceptance."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib.util
from pathlib import Path
import signal
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
PHASE = HERE.parent
CANONICAL_SHA = '715dfe948977163c993e6bc0b587c62cec5d15d13f1191e6d8104da41b2bcf79'
MAX_TIMEOUT = 10800


def load(name, path, expected):
    if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
        raise ValueError('Helper identity drift: '+str(path))
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


accepted = load('phase_worker_accepted_canonical', PHASE.parent/'canonical_q4_hsb/run.py', CANONICAL_SHA)
s, Execution = accepted.s, accepted.Execution
sys.path.insert(0, str(PHASE.parent))
checker = load('phase_worker_diagnostic_checker', HERE/'check.py',
               hashlib.sha256((HERE/'check.py').read_bytes()).hexdigest())


def fields(report, wanted, context):
    s.require(all(type(report.get(k)) is type(v) and report[k] == v for k, v in wanted.items()),
              'Wrong '+context+' fields')


def checked_path(value):
    path = Path(value)
    s.require(path.is_absolute() and path == path.resolve(strict=True) and path.is_file(),
              'Need absolute nonaliased file: '+str(path))
    return path


def checked_review(path, expected):
    path = checked_path(path)
    s.require(s.digest(path) == expected, 'Parent review SHA differs')
    review = s.read_json(path)
    fields(review, dict(schema='quant_hsb_phase_worker_review_v1'), 'parent review')
    runtime = review['runtime_environment']
    s.require(type(runtime) is dict and set(runtime) == {'LD_LIBRARY_PATH'} and
              (runtime['LD_LIBRARY_PATH'] is None or type(runtime['LD_LIBRARY_PATH']) is str),
              'Need exact reviewed runtime loader environment')
    receipt = checked_path(review['program_receipt'])
    s.require(receipt.name == 'build.json' and receipt.is_relative_to(PHASE/'prepare/out'),
              'Need owned diagnostic preparation receipt')
    s.require(s.digest(receipt) == review['program_receipt_sha256'], 'Program receipt SHA differs')
    helpers = review['helper_pins']
    required = {str(p) for directory in (PHASE/'prepare', PHASE/'analysis')
                for p in directory.iterdir() if p.is_file() and
                (p.suffix == '.py' or p.name in ('README.md', '.gitignore'))}
    s.require(required and required <= helpers.keys() and
              str(PHASE/'analysis/analyze.py') in helpers and
              all(str(checked_path(p)) == p for p in helpers), 'Incomplete/noncanonical helper review')
    s.verify_pins(helpers)
    pins = dict(helpers)
    s.merge_pins(pins, s.hashes([path, receipt]))
    phase_map = checked_path(review['phase_map'])
    s.require(s.digest(phase_map) == review['phase_map_sha256'], 'Phase map review SHA differs')
    s.merge_pins(pins, {str(phase_map): review['phase_map_sha256']})
    return review, receipt, pins


def checked_program(review, receipt, pins):
    """Replay exact source transform and linked-byte/layout review without tools."""
    # Load all producer code only after its externally reviewed identities passed.
    prep = PHASE/'prepare'
    renderer = load('render', prep/'render.py', pins[str(prep/'render.py')])
    load('elf', prep/'elf.py', pins[str(prep/'elf.py')])
    producer = load('phase_worker_prepare_build', prep/'build.py', pins[str(prep/'build.py')])
    report = s.read_json(receipt)
    fields(report, dict(state='DIAGNOSTIC_GNU_STATIC_PASS_NOT_EXECUTED', execution='NOT_RUN',
        diagnostic_only=True, trials=3, trial_order=[0, 1, 2], outputs_per_trial=768,
        total_outputs=2304, expected_qbs_commands=8, repeat_checks=0, post_pins_match=True,
        runtime_acceptance=False, numerical_execution_checked=False, performance_claim=False,
        old_timed_machine_identity=False, accepted_six_call_evidence_replaced=False,
        accepted_program_receipt_sha256=accepted.RECEIPT_SHA, accepted_elf_sha256=accepted.ELF_SHA,
        simulations_launched=0), 'diagnostic program')
    directory = receipt.parent
    names = {'diagnostic.c', 'link.ld', 'source-transform.json', 'planned-commands.json',
             'input-pins-before.json', 'input-pins-after.json', 'dependency-pins.json',
             'commands.json', 'dependencies.log', 'compile.log', 'link.log', 'disassembly.log',
             'object-map.json', 'main.o', 'link.map', 'q4_hsb_phase_diagnostic.elf'}
    artifacts = report['artifacts']
    s.require(set(artifacts) == {str(directory/n) for n in names}, 'Incomplete diagnostic artifacts')
    s.merge_pins(pins, artifacts)
    s.verify_pins(pins)
    before = s.read_json(directory/'input-pins-before.json')
    s.require(before and before == s.read_json(directory/'input-pins-after.json') and
              s.digest(directory/'input-pins-before.json') == report['input_pins_sha256'],
              'Program pre/post pins differ')
    s.merge_pins(pins, before)
    original, original_pins = accepted.checked_program()
    s.merge_pins(pins, original_pins)
    s.require(original_pins.items() <= before.items(), 'Preparation lacks accepted provenance pins')
    source = renderer.SOURCE.read_bytes()
    generated = (directory/'diagnostic.c').read_bytes()
    proof = renderer.provenance(generated)
    s.require(renderer.render(source) == generated and renderer.inverse(generated) == source and
              proof == report['source_provenance'] == s.read_json(directory/'source-transform.json') and
              proof['timed_region_sha256'] == accepted.TIMED_SHA,
              'Diagnostic reversible source transformation/provenance differs')
    elf = directory/'q4_hsb_phase_diagnostic.elf'
    fields(report, dict(elf=str(elf), elf_sha256=s.digest(elf),
                       rebuilt_objects=[str(directory/'main.o')]), 'diagnostic ELF')
    s.require(report['reused_objects'] == original['original_16_object_identity_map'] and
              len(report['reused_objects']) == 16, 'Need original sixteen nonmain objects')
    s.merge_pins(pins, report['reused_objects'])
    s.require((directory/'link.ld').read_text() == producer.linker(directory), 'Link transformation differs')
    mapping = producer.mapped(elf, (directory/'disassembly.log').read_text(),
                             s.read_json(accepted.PROGRAM/'layout-review.json'))
    s.require(mapping == s.read_json(directory/'object-map.json'), 'Actual linked object map differs')
    s.require(mapping['objects']['attention_golden']['payload_sha256'] == s.digest(accepted.GOLD),
              'Linked original capture golden differs')
    deps = s.read_json(directory/'dependency-pins.json')
    s.require(deps and all(before.get(p) == sha for p, sha in deps.items()), 'Unpinned compiler dependencies')
    s.merge_pins(pins, deps)
    planned, commands = s.read_json(directory/'planned-commands.json'), s.read_json(directory/'commands.json')
    s.require(len(planned) == len(commands) == 4 and
              [r['label'] for r in planned] == ['dependencies', 'compile', 'link', 'disassembly'] and
              all(r == dict(p, exit_code=0) for p, r in zip(planned, commands)),
              'Compiler command execution receipt differs')
    cc, link = producer.templates()
    old_source = next(x for x in cc if x.endswith('.c'))
    cc = [str(directory/'diagnostic.c') if x == old_source else x for x in cc]
    cc[cc.index('-o')+1] = str(directory/'main.o')
    link = [str(directory/'main.o') if x == str(accepted.PROGRAM/'main.o') else
            '-Wl,-Map='+str(directory/'link.map') if x.startswith('-Wl,-Map=') else x for x in link]
    link[link.index('-T')+1] = str(directory/'link.ld')
    link[link.index('-o')+1] = str(elf)
    drop = {cc.index('-c'), cc.index('-o'), cc.index('-o')+1}
    deps_command = [x for i, x in enumerate(cc) if i not in drop]+['-M', '-MT', 'object']
    disassemble = [str(Path(cc[0]).with_name('riscv64-unknown-elf-objdump')), '-d', str(elf)]
    expected = [dict(label=label, argv=argv, cwd=str(directory), timeout_seconds=120)
                for label, argv in zip(('dependencies', 'compile', 'link', 'disassembly'),
                                       (deps_command, cc, link, disassemble))]
    s.require(planned == expected, 'Diagnostic commands differ from accepted-source transformation')
    s.verify_pins(pins)
    return report, pins


def own_pins():
    paths = [*HERE.glob('*.py'), HERE/'README.md', accepted.GOLD, accepted.RTL,
             ROOT/'hardware/tb/ara_commit_monitor.sv', Path(sys.executable).resolve(),
             ROOT/'software/qbs/src/qbs_native_riscv.c', ROOT/'software/qbs/include/qbs/qbs_abi.h',
             ROOT/'verification/akv/run_refill_overlap_probe.py',
             ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh', *s.script_files()]
    paths += [Path('/usr/bin')/n for n in ('bash', 'readelf', 'awk', 'sed', 'grep', 'tail', 'head')]
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).is_file() and Path(name).resolve().is_relative_to(ROOT):
            paths.append(Path(name).resolve())
    return s.hashes(paths)


def prepare_inputs(args):
    review, receipt, pins = checked_review(args.review, args.review_sha256)
    report, pins = checked_program(review, receipt, pins)
    soc, canonical_pins, image = accepted.canonical.checked_soc(args.soc_build, accepted.SOC_SHA)
    s.merge_pins(pins, canonical_pins)
    s.merge_pins(pins, image)
    s.merge_pins(pins, own_pins())
    s.verify_pins(pins)
    return report, soc, pins, image


def simulation_command(simv, elf, work):
    return [simv, '-no_save', '-l', work/'run.vcs.log', '+PRELOAD='+str(elf),
            '+TESTCASE=quant_hsb_phase_diagnostic', '+NO_FSDB', '+NO_INSTR_TRACE', '+QBS_PERF',
            '+COMMIT_TRACE='+str(work/'commit_trace.csv'),
            '+VECTOR_TRACE='+str(work/'vector_trace.csv'),
            '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000']


def protocol(work, elf_sha, image):
    accepted.protocol(work, elf_sha, image)


def analysis_inputs(work, report, args, pins):
    review = s.read_json(args.review)
    directory = Path(report['elf']).parent
    mapping = s.read_json(directory/'object-map.json')
    inputs = dict(schema='quant_hsb_worker_retirement_inputs_v1',
        files={role: str(path) for role, path in dict(elf=Path(report['elf']),
            disassembly=directory/'disassembly.log', log=work/'run.vcs.log',
            commit=work/'commit_trace.csv', vector=work/'vector_trace.csv',
            golden=accepted.GOLD, rtl=accepted.RTL, phase_map=Path(review['phase_map'])).items()},
        boundary_pcs=[row['pc'] for row in mapping['rdcycle_sites']],
        helper=str(PHASE/'analysis/analyze.py'), pins=dict(pins))
    s.merge_pins(inputs['pins'], s.hashes(Path(p) for p in inputs['files'].values()))
    path = work/'analysis-inputs.json'
    s.atomic_json(path, inputs)
    return path, s.digest(path)


def analysis_command(work, inputs, sha):
    return [sys.executable, '-B', HERE/'retirement.py', '--inputs', inputs,
            '--inputs-sha256', sha, '--output', work/'analysis.json']


def checked_analysis(work, report, parsed):
    """Fail closed until the reviewed analyzer supplies all identity/completeness gates."""
    result = s.read_json(work/'analysis.json')
    fields(result, dict(schema='quantkv_phase_analysis_v1', state='DIAGNOSTIC_RETIREMENT_PROVEN',
        diagnostic_only=True, scalar_trace_truncated=False, csr_reads=6,
        functional_acceptance=False, hardware_utilization_claimed=False,
        performance_acceptance=False, pre_post_pins_match=True, elf_sha256=report['elf_sha256']),
        'retirement analysis')
    wanted = s.hashes([Path(report['elf']), work/'run.vcs.log', work/'commit_trace.csv', work/'vector_trace.csv'])
    s.require(all(result['input_pins'].get(p) == sha for p, sha in wanted.items()), 'Analysis raw input identity differs')
    s.verify_pins(result['input_pins'])
    windows = result['windows']
    s.require(len(windows) == 3 and len(result['measurement_pcs']) == 2 and all(
        all(type(row.get(k)) is int and row[k] == call[k] for k in ('trial', 'mode', 'cycles')) and
        row['csr_cycle_delta'] == call['cycles'] and row['retired_instructions'] > 0 and
        row['qbs_command_words'] == (['06b5045b', '02b5045b']*4 if call['mode'] == 2 else [])
        for row, call in zip(windows, parsed['trials'])), 'Analysis windows/work differ from own calls')
    return result


def run(args):
    s.require(type(args.timeout) is int and 1 <= args.timeout <= MAX_TIMEOUT, 'Timeout must be 1..10800 seconds')
    args.soc_build = args.soc_build.resolve(strict=True)
    output = args.output.absolute()
    review = checked_path(args.review)
    protected = [args.soc_build, HERE, review.parent, PHASE/'prepare', PHASE/'analysis', accepted.PROGRAM,
                 accepted.GOLD.parent]
    s.require(output == output.resolve() and not output.exists() and not any(
        output.is_relative_to(p) or p.is_relative_to(output) for p in protected), 'Need fresh independent output')
    s.require(not any(output.is_relative_to(ROOT/p) for p in ('hardware', 'software', 'verification/akv')),
              'Output must not overlap source directories')
    output.mkdir(parents=True)
    work = output/'work'
    work.mkdir()
    owner = Execution(output)
    owner.env.update(PATH='/usr/bin:/bin', READELF='/usr/bin/readelf', LC_ALL='C')
    for key in ('BASH_ENV', 'ENV', 'PYTHONHOME', 'PYTHONSTARTUP', 'PYTHONINSPECT'):
        owner.env.pop(key, None)
    owner.state.update(simulations_launched=0, timeout_seconds=args.timeout, soc_build=str(args.soc_build))
    owner.save()
    result = dict(execution='NOT_RUN', diagnostic_only=True, repeat_checks=0,
                  fresh_elf_diagnostic=True, old_elf_continuation=False, timed_machine_identity=False,
                  performance_acceptance=False, accepted_six_call_evidence_replaced=False,
                  whole_model=False, deployment_approved=False, independent_protocol_checked=False,
                  retirement_analysis_checked=False, post_pins_match=False)
    try:
        report, soc, pins, image = prepare_inputs(args)
        elf, simv = Path(report['elf']), Path(soc['simv'])
        runtime = {'LD_LIBRARY_PATH': owner.env.get('LD_LIBRARY_PATH')}
        s.require(s.read_json(review)['runtime_environment'] == runtime,
                  'Runtime loader environment differs from parent review')
        runtime_path = output/'runtime-environment.json'
        s.atomic_json(runtime_path, runtime)
        runtime_sha = s.digest(runtime_path)
        owner.state.update(elf=str(elf), simv=str(simv))
        s.atomic_json(output/'source-pins.json', pins)
        receipt = s.digest(output/'source-pins.json')
        result.update(elf_sha256=report['elf_sha256'], soc_build_sha256=accepted.SOC_SHA,
                      image_pins=image, source_pins_sha256=receipt, review_sha256=args.review_sha256,
                      runtime_environment=runtime, runtime_environment_sha256=runtime_sha)

        def identity():
            s.require(s.digest(runtime_path) == runtime_sha and
                      {'LD_LIBRARY_PATH': owner.env.get('LD_LIBRARY_PATH')} == runtime,
                      'Runtime loader environment drift')
            s.require(s.digest(output/'source-pins.json') == receipt, 'Worker receipt drift')
            s.verify_pins(pins)
            s.require(s.hashes(s.image_files(simv)) == image, 'Canonical image drift')

        def manifest(stage):
            identity()
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                simv.parent/'vcs_source_manifest.json', '--check'], output/(stage+'.log'),
                300, stage.upper().replace('-', '_'))
            identity()

        identity()
        if not args.execute_reviewed_diagnostic:
            result.update(state='DIAGNOSTIC_PREFLIGHT_NOT_RUN', simulations_launched=0,
                          post_pins_match=True)
        else:
            manifest('manifest-before')
            owner.execute(['bash', ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                simv.parent, elf], output/'image-contract.log', 180, 'IMAGE_CONTRACT')
            identity()
            owner.state['simulations_launched'] = 1
            owner.save()
            result['execution'] = 'SIMULATION_ATTEMPTED'
            owner.execute(simulation_command(simv, elf, work), work/'console.log', args.timeout, 'RUNNING')
            identity()
            raw_pins = s.hashes([elf, work/'run.vcs.log', work/'commit_trace.csv', work/'vector_trace.csv'])
            result['raw_replay'] = checker.check_log((work/'run.vcs.log').read_text(),
                                                     accepted.GOLD.read_bytes(), accepted.RTL.read_text())
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                '--require-backend', '--require-axi', '--require-axi-write', '--vector-trace',
                work/'vector_trace.csv', '--log', work/'run.vcs.log', '--simv', simv, '--elf', elf,
                '--output', work/'uvm_result.json'], work/'checker.log', 600, 'CHECKING')
            protocol(work, report['elf_sha256'], image)
            identity()
            inputs, analysis_sha = analysis_inputs(work, report, args, pins)
            owner.execute(analysis_command(work, inputs, analysis_sha), work/'analysis.log', 1800, 'ANALYZING')
            result['retirement_analysis'] = checked_analysis(work, report, result['raw_replay'])
            s.require(s.digest(inputs) == analysis_sha and
                      result['retirement_analysis']['input_manifest_sha256'] == analysis_sha,
                      'Retirement manifest drift')
            s.verify_pins(raw_pins)
            manifest('manifest-after')
            protocol(work, report['elf_sha256'], image)
            identity()
            result.update(state='PASS', acceptance='THREE_CALL_PHASE_DIAGNOSTIC_ONLY',
                          execution='SIMULATED_ONCE', simulations_launched=1, simulator_exit_code=0,
                          post_pins_match=True, independent_protocol_checked=True, retirement_analysis_checked=True)
        identity()
        result['evidence_sha256'] = s.hashes(p for p in output.rglob('*') if p.is_file() and
                                            p.name not in ('result.json', 'status.json'))
        s.atomic_json(output/'result.json', result)
        owner.state['state'] = result['state']
        return result
    except BaseException as exc:
        state = ('TIMEOUT' if isinstance(exc, subprocess.TimeoutExpired) else
                 'INTERRUPTED' if isinstance(exc, InterruptedError) else 'FAIL')
        result.pop('acceptance', None)
        result.update(state=state, error=repr(exc), post_pins_match=False,
                      simulations_launched=owner.state['simulations_launched'])
        owner.state.update(state=state, error=repr(exc))
        result['partial_evidence_sha256'] = s.hashes(p for p in output.rglob('*') if p.is_file() and
                                                    p.name not in ('result.json', 'status.json'))
        s.atomic_json(output/'result.json', result)
        raise
    finally:
        owner.state.update(child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        owner.save()


def main():
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--soc-build', type=Path, default=accepted.SOC_BUILD)
    parser.add_argument('--review', type=Path, required=True)
    parser.add_argument('--review-sha256', required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=MAX_TIMEOUT)
    parser.add_argument('--execute-reviewed-diagnostic', action='store_true')
    args = parser.parse_args()

    def interrupted(sig, _frame):
        raise InterruptedError(f'Signal {sig}')

    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, interrupted)
    run(args)


if __name__ == '__main__':
    main()
