#!/usr/bin/env python3
"""Recover one completed baseline; execute only the first candidate simulation."""
import argparse
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import adapter
c = adapter.c
ROOT = c.ROOT
original = c.load('held_ar_recovery_original_run', HERE.parent/'reader_fault_gate/run.py')
BUILD = ROOT/'verification/out/reader-held-ar-build-20261025-02'
BUILD_SHA = '2ee6fc2d5e8372f7a22f938055c9648038d3694aeecfe2485383f491c5402aba'
BASELINE = ROOT/'verification/out/reader-held-ar-run-20261025-01'
ORIGINAL_ERROR = "ValueError('Unknown/malformed injection record')"
PREFLIGHT_STATE = 'READER_FAULT_RECOVERY_PREFLIGHT_ONLY'
EXPORTER = Path('/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1/bin/fsdbreport')
RAW_NAMES = ('run.vcs.log', 'vector_trace.csv', 'reader.fsdb', 'console.log',
             'console.command.json', 'console.exit.json', 'manifest-before.log',
             'manifest-before.command.json', 'manifest-before.exit.json',
             'image-contract.log', 'image-contract.command.json', 'image-contract.exit.json')


def exact_command(directory, stem, argv, timeout):
    command = c.s.read_json(directory/(stem+'.command.json'))
    c.require(command == dict(argv=list(map(str, argv)), cwd=str(directory), timeout_seconds=timeout),
              'Original command/cwd/timeout mismatch: '+stem)
    c.require(c.s.read_json(directory/(stem+'.exit.json')) == dict(error=None, exit_code=0),
              'Original phase not successful: '+stem)


def failed_terminal(status, result, build):
    c.require(status == result and status.get('state') == 'FAIL' and
              status.get('error') == ORIGINAL_ERROR and status.get('variant') == 'baseline' and
              status.get('build') == str(build) and 'child_pid' in status and
              status['child_pid'] is None and status.get('running_exit_code') == 0 and
              status.get('manifest_before_exit_code') == 0 and status.get('image_contract_exit_code') == 0 and
              type(status.get('simulator_pid')) is int and status['simulator_pid'] > 0,
              'Only exact terminal run01 post-simulation parser failure is recoverable')


def own_pins():
    files = [p for p in HERE.iterdir() if p.suffix in ('.py', '.md')]
    files += [Path(sys.executable).resolve(), *c.s.script_files(),
              ROOT/'hardware/scripts/fsdb_trace/extract_cycles.py']
    for module in tuple(sys.modules.values()):
        name = getattr(module, '__file__', None)
        if name and Path(name).resolve().is_relative_to(ROOT): files.append(Path(name).resolve())
    return c.s.hashes(files)


def baseline_inputs(baseline, build, report, prepared, build_pins):
    c.require(baseline == BASELINE and build == BUILD, 'Recovery is restricted to reviewed run01/build02')
    failed_terminal(c.s.read_json(baseline/'status.json'), c.s.read_json(baseline/'result.json'), build)
    c.require(not (baseline/'candidate').exists(), 'Candidate was already attempted in original run')
    pins = c.s.read_json(baseline/'source-pins.json')
    c.require(all(pins.get(p) == h for p, h in build_pins.items()), 'Original run/build input binding differs')
    c.s.verify_pins(pins)
    work = baseline/'baseline'
    files = [baseline/n for n in ('status.json', 'result.json', 'source-pins.json')]
    files += [work/n for n in RAW_NAMES]
    files += [work/n for n in ('ucli.key', 'novas_dump.log') if (work/n).exists()]
    c.require(all(p.is_file() and p.resolve(strict=True) == p for p in files), 'Missing/aliased baseline evidence')
    c.require(all((work/n).stat().st_size > 0 for n in ('run.vcs.log', 'vector_trace.csv', 'reader.fsdb')),
              'Empty baseline raw evidence')
    # This is a new post-termination seal, not a claim that run01 sealed its outputs.
    evidence = c.s.hashes(files)
    recipe = prepared['recipes']['baseline']
    simv, elf = Path(report['images']['baseline']['simv']), Path(report['elf'])
    argv = original.simulation_command(simv, elf, report['weights']['address'],
        Path(recipe['script']), work/'run.vcs.log', work/'vector_trace.csv')
    exact_command(work, 'console', argv, 900)
    exact_command(work, 'manifest-before', [sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest',
        '--output', simv.parent/'vcs_source_manifest.json', '--check'], 300)
    exact_command(work, 'image-contract', ['bash', ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
        simv.parent, elf], 180)
    parsed = adapter.check_log((work/'run.vcs.log').read_text(), Path(recipe['vlsu']).read_text(),
                               report['weights']['address'], argv)
    c.require(parsed['commands'] == 71, 'Incomplete recovered baseline')
    c.s.verify_pins(evidence)
    c.s.merge_pins(pins, evidence)
    return pins, evidence, list(map(str, argv)), parsed


def configuration(args):
    return dict(build=str(args.build.resolve()), build_sha256=args.expected_build_sha256,
                baseline=str(args.baseline.resolve()), candidate_timeout_seconds=args.timeout,
                fsdbreport=str(args.fsdbreport.absolute()))


def check_approval(directory, expected, config, pins):
    c.require(re.fullmatch('[0-9a-f]{64}', expected or '') is not None and
              c.digest(directory/'preflight.json') == expected, 'Reviewed recovery preflight SHA mismatch')
    receipt = c.s.read_json(directory/'preflight.json')
    status = c.s.read_json(directory/'status.json')
    c.require(receipt.get('state') == status.get('state') == PREFLIGHT_STATE and
              status.get('child_pid') is None and receipt.get('execution') == 'NO_EDA_INVOKED' and
              receipt.get('configuration') == config, 'Wrong/nonterminal recovery preflight')
    c.require(receipt['source_pins_sha256'] == c.digest(directory/'source-pins.json') and
              c.s.read_json(directory/'source-pins.json') == pins, 'Preflight input inventory drift')
    c.require(receipt['baseline_input_seal_sha256'] == c.digest(directory/'baseline-input-seal.json'),
              'Preflight baseline seal drift')
    c.s.verify_pins(pins)
    return c.s.hashes([directory/n for n in
                      ('preflight.json', 'status.json', 'source-pins.json', 'baseline-input-seal.json')])


def verify_protocol(path, log, trace, elf_sha, image):
    c.s.check_result(path, elf_sha, image)
    proof = c.s.read_json(path)
    c.require(proof['log_sha256'] == c.digest(log) and proof['vector_trace_sha256'] == c.digest(trace),
              'Actual unfiltered UVM input identity mismatch')
    c.require(proof.get('contract_event_count', 0) > 0 and proof.get('uvm_backend_event_count', 0) > 0 and
              proof.get('axi_read_counts', {}).get('completed', 0) > 0 and
              proof.get('axi_write_counts', {}).get('matched', 0) > 0, 'Missing actual UVM scope')


def audit_variant(owner, mode, raw, work, expectedargv, report, prepared, exporter, identity):
    identity()
    recipe = prepared['recipes'][mode]
    image = report['images'][mode]
    simv, elf = Path(image['simv']), Path(report['elf'])
    target = report['weights']['address']
    log, trace, fsdb = (raw/n for n in ('run.vcs.log', 'vector_trace.csv', 'reader.fsdb'))
    raw_pins = c.s.hashes([log, trace, fsdb, raw/'console.command.json', raw/'console.exit.json', raw/'console.log'])
    c.require(c.s.read_json(raw/'console.exit.json') == dict(error=None, exit_code=0), 'Simulator did not exit cleanly')
    c.require(c.s.read_json(raw/'console.command.json')['argv'] == list(map(str, expectedargv)), 'Simulation argv drift')
    adapter.check_log(log.read_text(), Path(recipe['vlsu']).read_text(), target, expectedargv)
    owner.state['variant'] = mode
    # Actual UVM consumes original files, never the command-stripped parser view.
    owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
        '--require-axi', '--require-axi-write', '--vector-trace', trace, '--log', log,
        '--simv', simv, '--elf', elf, '--output', work/'uvm_result.json'], work/'uvm-check.log', 600, 'UVM_CHECK')
    verify_protocol(work/'uvm_result.json', log, trace, report['elf_sha256'], image['pins'])
    owner.execute([sys.executable, '-B', ROOT/'hardware/scripts/fsdb_trace/extract_cycles.py',
        '--fsdb', fsdb, '--profile', Path(recipe['capture']), '--begin', '0ns', '--end', '250000ns',
        '--output', work/'cycles', '--fsdbreport', exporter], work/'extract.log', 300, 'EXTRACTING')
    original.check_metadata(c.s.read_json(work/'cycles/metadata.json'), c.s.read_json(Path(recipe['capture'])))
    parsed = adapter.check_log_and_cycles(log.read_text(), Path(recipe['vlsu']).read_text(),
                                         work/'cycles/cycles.csv', target, expectedargv)
    c.save(work/'checked.json', parsed)
    owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
        simv.parent/'vcs_source_manifest.json', '--check'], work/'manifest-after.log', 300, 'MANIFEST_AFTER')
    c.s.verify_pins(raw_pins)
    identity()
    return parsed


def baseline_then_candidate(baseline_audit, candidate_run_and_audit):
    baseline = baseline_audit()
    c.require(baseline['state'] == 'LOG_AND_WAVE_CHECKED_NOT_OVERALL_ACCEPTANCE' and
              baseline['log']['commands'] == 71, 'Baseline must finish all semantic checks before candidate')
    candidate = candidate_run_and_audit()
    results = dict(baseline=baseline, candidate=candidate)
    return original.compare_pair(results), results


def run(args):
    c.require(type(args.timeout) is int and 1 <= args.timeout <= 900, 'Candidate timeout bound 1..900')
    c.require(args.expected_build_sha256 == BUILD_SHA, 'Only independently reviewed build02 is allowed')
    build, baseline, out = args.build.resolve(strict=True), args.baseline.resolve(strict=True), args.output.resolve()
    c.require(build == BUILD and baseline == BASELINE and not out.exists() and
              not any(out.is_relative_to(p) or p.is_relative_to(out) for p in (build, baseline, HERE)),
              'Fresh independent recovery output required')
    c.require(args.preflight_only or (args.approved_preflight is not None and args.expected_preflight_sha256),
              'Execution requires an explicitly hash-approved offline preflight')
    out.mkdir(parents=True)
    owner = c.Execution(out)
    owner.state.update(configuration=configuration(args), original_worker_state='FAIL', baseline_reused=True,
                       baseline_simulations_launched=0, candidate_simulations_launched=0)
    owner.save()
    try:
        own = own_pins()
        report, prepared, pins = c.checked_build(build, BUILD_SHA)
        oldpins, evidence, oldargv, parsed = baseline_inputs(baseline, build, report, prepared, pins)
        c.s.merge_pins(pins, oldpins)
        c.s.merge_pins(pins, own)
        exporter = args.fsdbreport.absolute()
        toolpins = c.s.hashes(c.hand.exporter_files(exporter))
        c.s.merge_pins(pins, toolpins)
        if not args.preflight_only:
            approval = args.approved_preflight.resolve(strict=True)
            c.require(not (out.is_relative_to(approval) or approval.is_relative_to(out)), 'Separate preflight output required')
            c.s.merge_pins(pins, check_approval(approval, args.expected_preflight_sha256, configuration(args), pins))
        c.s.verify_pins(pins)
        c.save(out/'source-pins.json', pins)
        pinsha = c.digest(out/'source-pins.json')
        c.save(out/'baseline-input-seal.json', dict(original_worker_state='FAIL', original_clean_pass=False,
            post_termination_seal=True, baseline=str(baseline), evidence_sha256=evidence, expected_argv=oldargv))

        def identity():
            c.require(c.digest(out/'source-pins.json') == pinsha, 'Recovery source receipt drift')
            c.s.verify_pins(pins)
            c.require(c.s.hashes(c.hand.exporter_files(exporter)) == toolpins, 'Exporter inventory drift')
            for image in report['images'].values():
                simv = Path(image['simv'])
                c.require(c.s.hashes(c.s.image_files(simv)) == image['pins'], 'Image inventory drift')
                c.verify_manifest(simv.parent/'vcs_source_manifest.json')

        identity()
        if args.preflight_only:
            c.save(out/'preflight.json', dict(state=PREFLIGHT_STATE, execution='NO_EDA_INVOKED',
                configuration=configuration(args), source_pins_sha256=pinsha,
                baseline_input_seal_sha256=c.digest(out/'baseline-input-seal.json'),
                baseline_log_commands=parsed['commands'], original_worker_state='FAIL',
                baseline_protocol_and_wave_accepted=False, candidate_executed=False))
            owner.state['state'] = PREFLIGHT_STATE
            return

        oldwork, newwork = out/'baseline-audit', out/'candidate'
        oldwork.mkdir()

        def audit_baseline():
            return audit_variant(owner, 'baseline', baseline/'baseline', oldwork, oldargv,
                                 report, prepared, exporter, identity)

        def execute_candidate():
            # This is the only simulator call in the successor, after baseline audit.
            identity()
            newwork.mkdir()
            simv = Path(report['images']['candidate']['simv'])
            elf = Path(report['elf'])
            recipe = prepared['recipes']['candidate']
            owner.state['variant'] = 'candidate'
            owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
                simv.parent/'vcs_source_manifest.json', '--check'], newwork/'manifest-before.log', 300, 'MANIFEST_BEFORE')
            owner.execute(['bash', ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh', simv.parent, elf],
                          newwork/'image-contract.log', 180, 'IMAGE_CONTRACT')
            argv = original.simulation_command(simv, elf, report['weights']['address'], Path(recipe['script']),
                                               newwork/'run.vcs.log', newwork/'vector_trace.csv')
            owner.state['candidate_simulations_launched'] = 1
            owner.execute(argv, newwork/'console.log', args.timeout, 'RUNNING')
            exact_command(newwork, 'console', argv, args.timeout)
            return audit_variant(owner, 'candidate', newwork, newwork, argv, report, prepared, exporter, identity)

        result, profiles = baseline_then_candidate(audit_baseline, execute_candidate)
        identity()
        closed = [out/'source-pins.json', out/'baseline-input-seal.json']
        for work in (oldwork, newwork):
            closed += [work/n for n in ('uvm_result.json', 'uvm-check.log', 'extract.log', 'checked.json',
                'manifest-after.log', 'cycles/cycles.csv', 'cycles/metadata.json', 'cycles/fsdbreport.raw.csv')]
            closed += sorted(work.glob('*.command.json')) + sorted(work.glob('*.exit.json'))
        closed += [newwork/n for n in ('run.vcs.log', 'vector_trace.csv', 'reader.fsdb', 'console.log',
                                       'manifest-before.log', 'image-contract.log')]
        result.update(acceptance='RECOVERED_BASELINE_AND_FRESH_CANDIDATE_CHECKED', build=str(build),
            build_sha256=BUILD_SHA, elf_sha256=report['elf_sha256'], images=report['images'], weights=report['weights'],
            original_run=str(baseline), original_worker_state='FAIL', original_clean_pass=False,
            baseline_execution='REUSED_COMPLETED_RUN01', candidate_execution='FIRST_EXECUTION',
            baseline_simulations_launched=0, candidate_simulations_launched=1,
            approved_preflight=str(approval), approved_preflight_sha256=args.expected_preflight_sha256,
            source_pins_sha256=pinsha, post_pins_match=True, independent_protocol_checked=True,
            simulator_exit_codes=dict(baseline=0, candidate=0), profiles=profiles,
            baseline_evidence_sha256=evidence, evidence_sha256=c.closed_evidence(closed))
        c.save(out/'result.json', result)
        owner.state['state'] = result['state']
        c.require(result['state'] == 'PASS', 'Paired regression: full differences retained')
    except BaseException as exc:
        if not (out/'result.json').exists(): c.finish_failure(owner, out, exc)
        raise
    finally:
        owner.state['child_pid'] = None
        owner.save()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--build', type=Path, default=BUILD)
    parser.add_argument('--expected-build-sha256', default=BUILD_SHA)
    parser.add_argument('--baseline', type=Path, default=BASELINE)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--timeout', type=int, default=900)
    parser.add_argument('--fsdbreport', type=Path, default=EXPORTER)
    parser.add_argument('--preflight-only', action='store_true')
    parser.add_argument('--approved-preflight', type=Path)
    parser.add_argument('--expected-preflight-sha256')
    c.install_signals()
    run(parser.parse_args())
