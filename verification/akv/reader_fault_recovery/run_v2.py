#!/usr/bin/env python3
"""Fixed recovery02: reuse run01 simulation and recovery01 UVM; correct export paths."""
from pathlib import Path
import argparse
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import adapter
import member_profile
c = adapter.c
base = c.load('held_ar_recovery_frozen_run', HERE/'run.py')
ROOT = c.ROOT
original = base.original
BUILD, BUILD_SHA, BASELINE, EXPORTER = base.BUILD, base.BUILD_SHA, base.BASELINE, base.EXPORTER
PREFLIGHT_STATE = base.PREFLIGHT_STATE
RECOVERY01 = ROOT/'verification/out/reader-held-ar-recovery-20261025-01'
PREFLIGHT01 = ROOT/'verification/out/reader-held-ar-recovery-preflight-20261025-01'
PREFLIGHT01_SHA = 'a3cab535576bdaab28bfa8926c56f1965d9c052bf33911cf17b7d4123246b42b'
own_pins = base.own_pins
configuration = base.configuration
baseline_inputs = base.baseline_inputs
exact_command = base.exact_command
verify_protocol = base.verify_protocol
baseline_then_candidate = base.baseline_then_candidate


def check_approval(directory, expected, config, pins, profile_hashes):
    approved = base.check_approval(directory, expected, config, pins)
    receipt = c.s.read_json(directory/'preflight.json')
    c.require(set(profile_hashes) == set(c.MODES) and
              receipt.get('baseline_uvm_seal_sha256') == c.digest(directory/'baseline-uvm-seal.json') and
              receipt.get('export_profile_sha256') == profile_hashes and
              all(c.digest(directory/'profiles'/(mode+'.json')) == sha for mode,sha in profile_hashes.items()),
              'Preflight UVM seal or successor profiles drift')
    c.s.merge_pins(approved, c.s.hashes([directory/'baseline-uvm-seal.json',
                                       *[directory/'profiles'/(m+'.json') for m in c.MODES]]))
    return approved


def checked_baseline_uvm(report, prepared, baseline_evidence):
    status, result = (c.s.read_json(RECOVERY01/n) for n in ('status.json', 'result.json'))
    expected_config = dict(build=str(BUILD), build_sha256=BUILD_SHA, baseline=str(BASELINE),
                           candidate_timeout_seconds=900, fsdbreport=str(EXPORTER))
    c.require(status == result and status.get('state') == 'FAIL' and status.get('child_pid') is None and
              status.get('error') == "ValueError('EXTRACTING returned 1')" and
              status.get('extracting_exit_code') == 1 and status.get('uvm_check_exit_code') == 0 and
              status.get('variant') == 'baseline' and status.get('candidate_simulations_launched') == 0 and
              status.get('baseline_simulations_launched') == 0 and status.get('baseline_reused') is True and
              status.get('original_worker_state') == 'FAIL' and status.get('configuration') == expected_config and
              not (RECOVERY01/'candidate').exists(), 'Only exact recovery01 extraction failure is reusable')
    c.require(c.digest(PREFLIGHT01/'preflight.json') == PREFLIGHT01_SHA, 'Original preflight identity drift')
    prior = c.s.read_json(PREFLIGHT01/'preflight.json')
    c.require(prior['source_pins_sha256'] == c.digest(PREFLIGHT01/'source-pins.json') and
              prior['baseline_input_seal_sha256'] == c.digest(PREFLIGHT01/'baseline-input-seal.json'),
              'Original preflight pin/seal drift')
    oldpins = c.s.read_json(PREFLIGHT01/'source-pins.json')
    c.s.merge_pins(oldpins, c.s.hashes([PREFLIGHT01/n for n in
                    ('preflight.json', 'status.json', 'source-pins.json', 'baseline-input-seal.json')]))
    c.require(oldpins == c.s.read_json(RECOVERY01/'source-pins.json') and
              c.digest(RECOVERY01/'baseline-input-seal.json') == prior['baseline_input_seal_sha256'],
              'Recovery01 inputs differ from its approved preflight')
    seal = c.s.read_json(RECOVERY01/'baseline-input-seal.json')
    c.require(seal['evidence_sha256'] == baseline_evidence, 'Recovered baseline raw evidence changed')
    pins = dict(oldpins)
    c.s.verify_pins(pins)
    work, raw = RECOVERY01/'baseline-audit', BASELINE/'baseline'
    simv, elf = Path(report['images']['baseline']['simv']), Path(report['elf'])
    exact_command(work, 'uvm-check', [sys.executable, '-B', '-m', 'ara_verify.uvm_dut',
        '--require-events', '--require-backend', '--require-axi', '--require-axi-write',
        '--vector-trace', raw/'vector_trace.csv', '--log', raw/'run.vcs.log', '--simv', simv,
        '--elf', elf, '--output', work/'uvm_result.json'], 600)
    expected_extract = dict(argv=list(map(str, [sys.executable, '-B',
        ROOT/'hardware/scripts/fsdb_trace/extract_cycles.py', '--fsdb', raw/'reader.fsdb',
        '--profile', Path(prepared['recipes']['baseline']['capture']), '--begin', '0ns', '--end', '250000ns',
        '--output', work/'cycles', '--fsdbreport', EXPORTER])), cwd=str(work), timeout_seconds=300)
    c.require(c.s.read_json(work/'extract.command.json') == expected_extract and
              c.s.read_json(work/'extract.exit.json') == dict(error="ValueError('EXTRACTING returned 1')", exit_code=1),
              'Original extraction failure command/exit drift')
    proof = work/'uvm_result.json'
    evidence = c.s.hashes([RECOVERY01/n for n in
        ('status.json', 'result.json', 'source-pins.json', 'baseline-input-seal.json')] +
        [work/n for n in ('uvm_result.json', 'uvm-check.log', 'uvm-check.command.json', 'uvm-check.exit.json',
                          'extract.log', 'extract.command.json', 'extract.exit.json')])
    verify_protocol(proof, raw/'run.vcs.log', raw/'vector_trace.csv', report['elf_sha256'], report['images']['baseline']['pins'])
    c.s.verify_pins(evidence)
    c.s.merge_pins(pins, evidence)
    return proof, pins, dict(previous_recovery_state='FAIL', previous_clean_pass=False, source=str(proof),
        source_sha256=c.digest(proof), evidence_sha256=evidence)


def write_profiles(prepared, out):
    directory = out/'profiles'; directory.mkdir()
    paths = {}
    for mode in c.MODES:
        original_profile = c.s.read_json(Path(prepared['recipes'][mode]['capture']))
        paths[mode] = directory/(mode+'.json')
        c.save(paths[mode], member_profile.successor(original_profile))
    return paths, {mode:c.digest(path) for mode,path in paths.items()}


def audit_variant(owner, mode, raw, work, expectedargv, report, prepared, exporter, identity,
                  profile, reused_uvm=None):
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
    if reused_uvm is not None:
        c.require(mode == 'baseline' and reused_uvm == RECOVERY01/'baseline-audit/uvm_result.json', 'Wrong UVM reuse')
        verify_protocol(reused_uvm, log, trace, report['elf_sha256'], image['pins'])
        c.save(work/'uvm-reuse.json', dict(source=str(reused_uvm), source_sha256=c.digest(reused_uvm), rerun=False))
    else:
        c.require(mode == 'candidate', 'Baseline UVM must be reused, not rerun')
        owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
            '--require-axi', '--require-axi-write', '--vector-trace', trace, '--log', log,
            '--simv', simv, '--elf', elf, '--output', work/'uvm_result.json'], work/'uvm-check.log', 600, 'UVM_CHECK')
        verify_protocol(work/'uvm_result.json', log, trace, report['elf_sha256'], image['pins'])
    owner.execute([sys.executable, '-B', ROOT/'hardware/scripts/fsdb_trace/extract_cycles.py',
        '--fsdb', fsdb, '--profile', profile, '--begin', '0ns', '--end', '250000ns', '--no-events',
        '--output', work/'cycles', '--fsdbreport', exporter], work/'extract.log', 300, 'EXTRACTING')
    original.check_metadata(c.s.read_json(work/'cycles/metadata.json'), c.s.read_json(profile))
    parsed = adapter.check_log_and_cycles(log.read_text(), Path(recipe['vlsu']).read_text(),
                                         work/'cycles/cycles.csv', target, expectedargv)
    c.save(work/'checked.json', parsed)
    owner.execute([sys.executable, '-B', '-m', 'ara_verify.vcs_source_manifest', '--output',
        simv.parent/'vcs_source_manifest.json', '--check'], work/'manifest-after.log', 300, 'MANIFEST_AFTER')
    c.s.verify_pins(raw_pins)
    identity()
    return parsed


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
        reused_uvm, uvm_pins, uvm_seal = checked_baseline_uvm(report, prepared, evidence)
        c.s.merge_pins(pins, oldpins)
        c.s.merge_pins(pins, uvm_pins)
        c.s.merge_pins(pins, own)
        exporter = args.fsdbreport.absolute()
        toolpins = c.s.hashes(c.hand.exporter_files(exporter))
        c.s.merge_pins(pins, toolpins)
        export_profiles, profile_hashes = write_profiles(prepared, out)
        profile_pins = c.s.hashes(export_profiles.values())
        if not args.preflight_only:
            approval = args.approved_preflight.resolve(strict=True)
            c.require(not (out.is_relative_to(approval) or approval.is_relative_to(out)), 'Separate preflight output required')
            c.s.merge_pins(pins, check_approval(approval, args.expected_preflight_sha256,
                                               configuration(args), pins, profile_hashes))
        c.s.verify_pins(pins)
        c.save(out/'source-pins.json', pins)
        pinsha = c.digest(out/'source-pins.json')
        c.save(out/'baseline-input-seal.json', dict(original_worker_state='FAIL', original_clean_pass=False,
            post_termination_seal=True, baseline=str(baseline), evidence_sha256=evidence, expected_argv=oldargv))
        c.save(out/'baseline-uvm-seal.json', uvm_seal)

        def identity():
            c.require(c.digest(out/'source-pins.json') == pinsha, 'Recovery source receipt drift')
            c.s.verify_pins(pins)
            c.s.verify_pins(profile_pins)
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
                baseline_uvm_seal_sha256=c.digest(out/'baseline-uvm-seal.json'),
                export_profile_sha256=profile_hashes, baseline_uvm_reused=True,
                baseline_log_commands=parsed['commands'], original_worker_state='FAIL',
                baseline_protocol_and_wave_accepted=False, candidate_executed=False))
            owner.state['state'] = PREFLIGHT_STATE
            return

        oldwork, newwork = out/'baseline-audit', out/'candidate'
        oldwork.mkdir()

        def audit_baseline():
            return audit_variant(owner, 'baseline', baseline/'baseline', oldwork, oldargv,
                                 report, prepared, exporter, identity, export_profiles['baseline'], reused_uvm)

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
            return audit_variant(owner, 'candidate', newwork, newwork, argv, report, prepared, exporter,
                                 identity, export_profiles['candidate'])

        result, semantic_profiles = baseline_then_candidate(audit_baseline, execute_candidate)
        identity()
        closed = [out/'source-pins.json', out/'baseline-input-seal.json', out/'baseline-uvm-seal.json',
                  oldwork/'uvm-reuse.json', newwork/'uvm_result.json', newwork/'uvm-check.log', *export_profiles.values()]
        for work in (oldwork, newwork):
            closed += [work/n for n in ('extract.log', 'checked.json',
                'manifest-after.log', 'cycles/cycles.csv', 'cycles/metadata.json', 'cycles/fsdbreport.raw.csv')]
            closed += sorted(work.glob('*.command.json')) + sorted(work.glob('*.exit.json'))
        closed += [newwork/n for n in ('run.vcs.log', 'vector_trace.csv', 'reader.fsdb', 'console.log',
                                       'manifest-before.log', 'image-contract.log')]
        result.update(acceptance='RECOVERED_BASELINE_AND_FRESH_CANDIDATE_CHECKED', build=str(build),
            build_sha256=BUILD_SHA, elf_sha256=report['elf_sha256'], images=report['images'], weights=report['weights'],
            original_run=str(baseline), original_worker_state='FAIL', original_clean_pass=False,
            baseline_execution='REUSED_COMPLETED_RUN01', candidate_execution='FIRST_EXECUTION',
            baseline_uvm_execution='REUSED_RECOVERY01', previous_recovery_state='FAIL',
            export_profile_sha256=profile_hashes, baseline_uvm_evidence_sha256=uvm_seal['evidence_sha256'],
            baseline_simulations_launched=0, candidate_simulations_launched=1,
            approved_preflight=str(approval), approved_preflight_sha256=args.expected_preflight_sha256,
            source_pins_sha256=pinsha, post_pins_match=True, independent_protocol_checked=True,
            simulator_exit_codes=dict(baseline=0, candidate=0), profiles=semantic_profiles,
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
