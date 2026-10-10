#!/usr/bin/env python3
"""Admit corrected runtime02 without simulation, relocation, or tool launches.

--check is read-only. --prepare adds NEW producer metadata and a DVE input list
only after a standalone PASS and full 650-case admission. The parent may then
export DVE separately to RUNTIME/combined-dve. --finalize consumes that completed
report through run_targeted_extension.summarize; its invoke callback is scoped
to one exact report command and never launches a child.

The versioned gap65-observed-v1 row retains the standalone producer layout.
ROW=tests is the actual result-directory label, not the app/coverage identity.
Future checked extensions MUST call this module's install_hooks before admission.
Only this one kind/case is dispatched to the recovery audit; all normal baseline
rules are delegated unchanged. Original logs, summaries and rejection survive.
"""
import argparse
import copy
from dataclasses import asdict
import json
from pathlib import Path
import re
import shlex
import sys
from unittest.mock import patch

sys.dont_write_bytecode = True
# Import order deliberately binds HOST04 and the boot adapter's SCRIPT.
import run_gap65_boot_checked_observed as boot
import run_gap65_late_fault_observed as observed
import coverage_evidence as evidence
import run_targeted_extension as targeted
import gap65_observer_echo as echo
from ara_verify.runner import FAIL_RE

full, require = evidence.full, evidence.require
ROOT = observed.ROOT
RUNTIME = ROOT / 'verification/out/gap65-late-fault-runtime-20261004-02'
ADMISSION = ROOT / 'verification/out/gap65-late-fault-preflight-20261004-05/admission.json'
ADMISSION_SHA = 'cd862bf91daf17964cbb5be4db58d37b1442af00fb088f4e01724133b106023e'
ELF_SHA = 'a1f5038742e8390278d56f1fa4bc36704323f2846eb98177b14fd3ffdfec7c0b'
BASELINE = observed.BASELINE
SCRIPT = Path(__file__).resolve()
ROW = 'tests'
SCHEMA = 'gap65-observed-report-v1'
KIND = 'gap65-observed-v1'
_NORMAL_ROW = evidence.Evidence.baseline_row


def artifact_at(runtime):
    return runtime / 'results/tests' / ('app_' + observed.NAME)


def validate_runtime(runtime, admission, digest, proof):
    require(runtime == RUNTIME and admission == ADMISSION and digest == ADMISSION_SHA,
            'only externally sealed corrected runtime02/preflight05 admitted')
    require(observed.HOST == ROOT / 'verification/out/gap65-late-fault-preflight-20261004-04'
            and observed.SCRIPT == Path(boot.__file__).resolve(), 'corrected boot adapter not bound')
    plan, pins = observed.verify_plan(admission, digest)
    proof.hashes(pins)
    require(plan['elf_sha256'] == ELF_SHA and plan['baseline'] == str(BASELINE)
            and plan['baseline_passed'] == 650 and plan['target'] == observed.checks.TARGET,
            'corrected ELF/baseline/target identity differs')
    require(not (runtime / 'result.json').exists(), 'original diagnostic result unexpectedly published')
    rejection = proof.read(runtime / 'rejected.json')
    require(rejection == dict(status='REJECTED', reason='runtime failure',
                             aggregate_admitted=False, retry_allowed=False),
            'only exact source-echo postcheck rejection recoverable')
    artifact = artifact_at(runtime)
    vdb = artifact / 'work/code.vdb'
    require(vdb.resolve(strict=True) == vdb,
            'foreign or relocated standalone VDB')
    original_files = full.pins([p for p in (runtime / 'results').rglob('*') if p.is_file()])
    proof.hashes(original_files)
    summaries = proof.read(runtime / 'results/summary.json')
    require(len(summaries) == 1, 'one standalone summary required')
    summary = summaries[0]
    require(summary['name'] == observed.CASE and summary['kind'] == 'app'
            and summary['returncode'] == 0 and full.batch.classify(summary, 0) == 'PASS'
            and summary['artifact_dir'] == str(artifact), 'standalone summary is not this case PASS')
    run = proof.read(runtime / 'results/run.json')
    require(run['status'] == 'COMPLETE' and run['source_snapshot']['sha256'] == digest
            and run['input_snapshots'] is True and run['commit_trace'] is True
            and run['timeout_s'] == 300, 'standalone run incomplete or unbound')
    config = proof.read(runtime / 'runtime.json')
    require(config['admission'] == str(admission) and config['admission_sha256'] == digest,
            'runtime admission differs')
    expected_inputs = {str(runtime / 'inputs' / (observed.NAME + '.elf')),
                       str(runtime / 'inputs/simulator.conf')}
    require(set(config['files']) == expected_inputs, 'runtime input membership differs')
    proof.hashes(config['files'])
    proof.pin(runtime / 'inputs' / (observed.NAME + '.elf'), ELF_SHA)
    proof.pin(runtime / 'inputs/simulator.conf', observed.sha(Path(plan['simv']).parent / 'simulator.conf'))
    wrapper = proof.pin(runtime / 'inputs/observed_simv')
    tokens = shlex.split(wrapper.read_text().split('\n', 1)[1])
    require(wrapper.read_text().startswith('#!/bin/sh\n') and tokens[:1] == ['exec']
            and len(tokens) == 10 and tokens[2:] == ['-B', str(observed.SCRIPT), '--sim-exec',
                str(runtime / 'runtime.json'), '--config-sha256', observed.sha(runtime / 'runtime.json'),
                '--', '$@'], 'runtime wrapper command differs')
    wrapper_image = full.batch.simulation_image(wrapper)
    proof.hashes(wrapper_image)
    metadata = proof.read(artifact / 'inputs.json')
    require(metadata['simv']['path'] == str(wrapper)
            and metadata['simv']['image_sha256'] == wrapper_image
            and metadata['binary']['sha256'] == ELF_SHA, 'runtime input metadata differs')
    proof.pin(artifact / 'input.elf', ELF_SHA)
    elf_proof = proof.read(observed.HOST / 'elf-proof.json')
    require(elf_proof['elf_sha256'] == ELF_SHA, 'host ELF proof differs')
    normalization = {}
    script = proof.pin(observed.OBSERVER, plan['files'][str(observed.OBSERVER)]).read_text()
    for path in (artifact / 'console.log', artifact / 'work/run.vcs.log'):
        original = proof.pin(path).read_text()
        require(FAIL_RE.search(original) is None, 'ordinary runner detects actual runtime failure')
        normalized, record = echo.normalize(original, script)
        observed.checks.check_runtime_log(normalized, elf_proof)
        normalization[str(path)] = dict(record, original_sha256=observed.sha(path))
    samples = observed.observer_samples(proof.pin(artifact / 'work/gap65-observer.tsv').read_text())
    audit = observed.audit_run(runtime / 'results', require_trace=True)
    full.batch.audit_ok(audit, dict(kind='directed', source_name=observed.CASE), artifact)
    vdb_files = full.batch.valid_vdb(vdb, observed.NAME, plan['simv'])
    proof.hashes(vdb_files)
    command = observed.simulator_command_after(plan, runtime, artifact)
    require(proof.read(artifact / 'work/coverage.command.json') ==
            dict(command=command, cwd=str(artifact / 'work')), 'runtime command/cwd differs')
    info = full.batch.xml_root(vdb / 'snps/coverage/db/testdata' / observed.NAME / 'siminfo.xml')
    require(shlex.split(info.find('srctest').get('cmdline')) == command, 'VDB observer command differs')
    raw = observed.bitmaps.read_metric(vdb / 'snps/coverage/db/testdata' / observed.NAME /
                                      'fsm.verilog.data.xml')[observed.checks.TARGET_SCOPE]
    before = proof.read(BASELINE / 'combined-bits.json')['metrics']['fsm'][observed.checks.TARGET_SCOPE]
    gain = observed.checks.check_target_delta(before, raw)
    result = dict(status='PASS_POSTPROCESS_RECOVERY', schema=SCHEMA,
                  scope='new readmission proof; original standalone rejection is preserved',
                  original_rejection=str(runtime / 'rejected.json'), rejection=rejection,
                  samples=samples, raw_before=before, raw_after=raw, target_delta=gain,
                  vdb=str(vdb), vdb_files=vdb_files, admission_sha256=digest,
                  normalization=normalization, files=original_files)
    full.check(original_files)
    return plan, result, summaries, audit, wrapper_image


def baseline_row(proof, row, image, simv):
    if row.get('kind') != KIND:
        return _NORMAL_ROW(proof, row, image, simv)
    require(row['name'] == ROW and row['coverage_test'] == observed.NAME
            and row.get('schema') == SCHEMA and row.get('producer') == str(RUNTIME)
            and row['status'] == 'PASS' and row['passed_only'] is True
            and row['vdb_valid'] is True and row['reused'] is False and row['returncode'] == 0,
            'foreign or unverified gap65 recovery row')
    proof.hashes(row['files'])
    plan = proof.plan(RUNTIME)
    proof.collection(RUNTIME, image)
    require(plan['image'] == image and plan['simv'] == simv
            and plan.get('gap65_report_only') == SCHEMA and len(plan['cases']) == 1,
            'gap65 producer identity differs')
    case = plan['cases'][0]
    require(case['source_name'] == observed.CASE and case['name'] == ROW
            and case['kind'] == KIND and all(row[k] == case[k] for k in
                ('kind', 'elf_sha256', 'coverage_test', 'contract'))
            and case['elf_sha256'] == ELF_SHA and case['timeout_s'] == 300
            and case['frozen_elf'] == str(RUNTIME / 'inputs' / (observed.NAME + '.elf'))
            and case['contract'] == full.contract(dict(case, kind='directed')),
            'gap65 producer case/contract differs')
    require(proof.read(RUNTIME / 'outcomes/tests.json') == row, 'gap65 producer outcome differs')
    proof.pin(case['frozen_elf'], row['elf_sha256'])
    for path in (RUNTIME / 'observed-recovery/result.json', RUNTIME / 'observed-recovery/independent_audit.json'):
        require(str(path) in row['files'], 'unbound recovery proof')
    source, result, _, audit, wrapper_image = validate_runtime(RUNTIME, ADMISSION, ADMISSION_SHA, proof)
    require(source['image'] == image and source['simv'] == simv and wrapper_image == plan['wrapper_image']
            and row['vdb'] == result['vdb'] and row['vdb_files'] == result['vdb_files']
            and proof.read(RUNTIME / 'observed-recovery/result.json') == result
            and proof.read(RUNTIME / 'observed-recovery/independent_audit.json') == audit,
            'gap65 independently recomputed recovery differs')


def install_hooks():
    """Opt-in only: one versioned row; normal Evidence admission is unchanged."""
    evidence.Evidence.baseline_row = baseline_row


def validate(runtime=RUNTIME, admission=ADMISSION, digest=ADMISSION_SHA):
    proof = evidence.Evidence()
    plan, result, summaries, audit, wrapper_image = validate_runtime(runtime, admission, digest, proof)
    prior = proof.plan(BASELINE)
    require(all(prior[k] == plan[k] for k in ('image', 'simv', 'design_vdb', 'design_files')),
            '650 producer image/design differs')
    collection = proof.collection(BASELINE, plan['image'])
    require(collection['status'] == 'PASS' and collection['passed'] == collection['total'] == 650
            and proof.read(BASELINE / 'checkpoint.json')['coverage_status'] == 'COMPLETE',
            'completed checked650 baseline required')
    rows = proof.ledger(BASELINE, plan['image'])
    for index, row in enumerate(rows, 1):
        proof.baseline_row(row, plan['image'], plan['simv'])
        if index % 100 == 0:
            print('CHECKED baseline: %d/650' % index, flush=True)
    targeted.admission.admitted(rows, plan['simv'])
    require(ROW not in {r['name'] for r in rows} and observed.NAME not in {r['coverage_test'] for r in rows}
            and ELF_SHA not in {r['elf_sha256'] for r in rows}
            and result['vdb'] not in {r['vdb'] for r in rows}, 'duplicate new name/test/ELF/VDB')
    listing = proof.pin(BASELINE / 'combined-dve/inputs.txt').read_text().splitlines()
    require(listing == [plan['design_vdb'], *[r['vdb'] for r in rows]], '650 DVE membership differs')
    bits = proof.read(BASELINE / 'combined-bits.json')
    require(bits['tests'] == [r['vdb'] for r in rows], '650 bitmap membership differs')
    proof.hashes(bits['input_hashes'])
    before = bits['metrics']['fsm'][observed.checks.TARGET_SCOPE]
    gain = observed.checks.check_target_delta(before, result['raw_after'])
    require(before == result['raw_before'] and gain == result['target_delta'], 'standalone target delta differs')
    for module in (boot, observed, evidence, targeted, echo):
        proof.pin(Path(module.__file__).resolve())
    proof.pin(SCRIPT)
    full.check(proof.files)
    return dict(proof=proof, admission=plan, prior=prior, result=result, rows=rows,
                summaries=summaries, audit=audit, wrapper_image=wrapper_image)


def new_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def new_text(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as stream:
        stream.write(value)


def prepare(runtime, admission, digest):
    names = ['plan.json', 'plan.sha256.json', 'checkpoint.json', 'gap65-finalization.json',
             'gap65-report-inputs.txt', 'inputs/baseline-ledger.json', 'inputs/coverage-wrapper.json',
             'outcomes/tests.json', 'observed-recovery/result.json', 'observed-recovery/independent_audit.json']
    require(not any((runtime / n).exists() for n in names), 'existing producer metadata; no retry/overwrite')
    checked = validate(runtime, admission, digest)
    proof, source = checked['proof'], checked['admission']
    frozen = runtime / 'inputs' / (observed.NAME + '.elf')
    test = full.batch.TestCase(observed.CASE, 'app', 'unused-no-build', frozen, observed.NAME, 300)
    case = dict(name=ROW, kind='directed', source_name=observed.CASE, oracle='selfcheck+trace-audit',
                timeout_s=300, frozen_elf=str(frozen), elf_sha256=ELF_SHA, coverage_test=observed.NAME,
                directed_test=dict(asdict(test), binary=str(frozen)),
                source_files={str(frozen): ELF_SHA}, origins=[dict(source=str(admission), name=observed.CASE)],
                coverage_targets=[observed.checks.TARGET_SCOPE],
                coverage_rationale='Observed late-row COMPUTE_TILE fault followed by checked M4 N4 recovery')
    case['contract'] = full.contract(case)
    case['kind'] = KIND
    new_json(runtime / 'observed-recovery/result.json', checked['result'])
    new_json(runtime / 'observed-recovery/independent_audit.json', checked['audit'])
    new_json(runtime / 'inputs/baseline-ledger.json', checked['rows'])
    new_json(runtime / 'inputs/coverage-wrapper.json', dict(simv=source['simv'], image=source['image'],
                                                         results=str(runtime / 'results')))
    report = dict(schema=SCHEMA, status='CHECKED_PASS_REPORT_PENDING', admission=str(admission),
                  admission_sha256=digest, runtime=str(runtime), baseline=str(BASELINE),
                  baseline_passed=650, simulations_started=False, producer_name=ROW,
                  compatibility='Future checked extensions must install finalize_gap65_observed.install_hooks(); '
                                'one versioned standalone row only; normal rows delegated unchanged',
                  checked_files=proof.files)
    new_json(runtime / 'gap65-finalization.json', report)
    proof.hashes(full.pins([runtime / n for n in names if (runtime / n).is_file()]))
    plan = copy.deepcopy(checked['prior'])
    plan.update(cases=[case], baseline=str(BASELINE), baseline_bits=str(BASELINE / 'combined-bits.json'),
                baseline_passed=650, source_selection=dict(baseline=str(BASELINE)),
                wrapper=str(runtime / 'inputs/observed_simv'), wrapper_image=checked['wrapper_image'],
                files=proof.files.copy(), gap65_report_only=SCHEMA)
    row = dict(name=ROW, kind=KIND, schema=SCHEMA, producer=str(runtime),
               status='PASS', reused=False, returncode=0,
               passed_only=True, vdb_valid=True, elf_sha256=ELF_SHA, coverage_test=observed.NAME,
               vdb=checked['result']['vdb'], vdb_files=checked['result']['vdb_files'],
               contract=case['contract'], origins=case['origins'], files=proof.files.copy())
    new_json(runtime / 'outcomes/tests.json', row)
    new_json(runtime / 'plan.json', plan)
    new_json(runtime / 'plan.sha256.json', full.pins([runtime / 'plan.json']))
    new_text(runtime / 'gap65-report-inputs.txt', '\n'.join([source['design_vdb'],
             *[r['vdb'] for r in checked['rows']], row['vdb']]) + '\n')
    normal = evidence.Evidence()
    normal.plans[runtime] = plan
    normal.collections[runtime] = {}  # Collection is deliberately not published before DVE.
    baseline_row(normal, row, source['image'], source['simv'])
    full.check(proof.files)
    return report


def report_callback(runtime, plan, rows, proof):
    target = runtime / 'combined-dve'
    expected_inputs = [plan['design_vdb'], *[r['vdb'] for r in rows]]
    require(proof.pin(target / 'inputs.txt').read_text().splitlines() == expected_inputs,
            'external DVE input membership differs')
    selected = [str(Path(r['vdb']).with_suffix('') / r['coverage_test']) for r in rows]
    require(proof.pin(target / 'selected_tests.txt').read_text().splitlines() == selected,
            'external DVE selected tests differ')
    logs = [proof.pin(target / 'launcher.log'), proof.pin(target / 'DVEfiles/dve_gui.log')]
    diagnostic = (r'(^|\s)(Warning|Error|Fatal)([\s:-]|$)|DVE_COVERAGE_EXPORT_FAILED|'
                  r'Database mismatch|will not be merged|Version Check Error|'
                  r'(checksum mismatches|Total unmappable exclusions|Total exclusions need to review)\s*:\s*[1-9]')
    require(not any(re.search(diagnostic, p.read_text(), re.I | re.M) for p in logs)
            and 'DVE_COVERAGE_EXPORT_DONE' in logs[1].read_text().splitlines(), 'external DVE export failed')
    require(proof.pin(target / 'diagnostics.txt').read_text() == '', 'DVE diagnostic matches')
    require(proof.pin(target / 'summary.csv').stat().st_size > 0
            and not (target / 'summary.csv.partial').exists(), 'incomplete external DVE summary')
    # This campaign's unchanged frozen design has no applicable reviewed waiver.
    waiver = proof.read(target / 'waiver_status.json')
    prior = proof.read(BASELINE / 'combined-dve/waiver_status.json')
    require(waiver == prior and waiver['status'] == 'NOT_APPLICABLE_UNREVIEWED_DESIGN',
            'external DVE waiver policy differs or needs separate review')
    require(waiver['design_sha256'] == observed.sha(Path(plan['design_vdb']) /
            'snps/coverage/db/design/verilog.design.xml'), 'DVE design identity differs')

    def consume(command, log, timeout, env=None):
        require(command == ['bash', str(full.DVE / 'run_dve_coverage.sh'), str(target),
                '--inputs-file', str(runtime / 'combined-inputs.txt')]
                and log == runtime / 'logs/combined-dve.log' and timeout == plan['dve_outer_timeout_s']
                and env == dict(DVE_COVERAGE_TIMEOUT=str(plan['dve_timeout_s']), DVE_WAIVERS='auto'),
                'unexpected tool invocation refused')
        require((runtime / 'combined-inputs.txt').read_text().splitlines() == expected_inputs,
                'summarizer report membership differs')
        full.check(proof.files)
        return 0
    return consume


def finalize(runtime, admission, digest):
    generated = ['all-outcomes.json', 'combined-inputs.txt', 'coverage-delta.json', 'per-case-gains.json',
                 'combined-bits.json', 'raw-bitmap-delta.json', 'all-passed-outcomes.json', 'collection.json',
                 'inputs/tests.vdbs.txt', 'gap65-completion.json', 'checkpoint.json',
                 'gap65-complete-checkpoint.json']
    require(not any((runtime / n).exists() for n in generated), 'existing final reports; no retry/overwrite')
    checked = validate(runtime, admission, digest)
    proof = checked['proof']
    plan = proof.plan(runtime)
    require(plan['gap65_report_only'] == SCHEMA and plan['baseline'] == str(BASELINE)
            and len(plan['cases']) == 1 and plan['cases'][0]['name'] == ROW,
            'foreign finalizer producer plan')
    proof.hashes(plan['files'])
    require(proof.read(runtime / 'inputs/baseline-ledger.json') == checked['rows'], 'prepared baseline differs')
    row = proof.read(runtime / 'outcomes/tests.json')
    require(row['vdb'] == checked['result']['vdb'] and row['vdb_files'] == checked['result']['vdb_files'],
            'prepared standalone outcome differs')
    proof.collections[runtime] = {}  # Only this not-yet-collected producer is cached.
    baseline_row(proof, row, plan['image'], plan['simv'])
    rows = checked['rows'] + [row]
    callback = report_callback(runtime, plan, rows, proof)
    full.check(proof.files)
    # All writes of summarize are fresh reports; only its exact DVE call is intercepted.
    with patch.object(full.batch, 'invoke', callback):
        targeted.summarize(runtime, plan)
    full.check(proof.files)
    normal = evidence.Evidence()
    require(len(normal.ledger(runtime, plan['image'])) == 651, 'final ledger count differs')
    baseline_row(normal, row, plan['image'], plan['simv'])
    require(full.read(runtime / 'combined-bits.json')['tests'] == [r['vdb'] for r in rows],
            'merged bitmap membership differs')
    completion = dict(status='PASS', schema=SCHEMA, aggregate_passed=651, simulations_started=False,
                      tools_launched=False, files=proof.files | normal.files)
    new_json(runtime / 'gap65-completion.json', completion)
    checkpoint = dict(status='PASS', phase='complete',
             coverage_status='COMPLETE', aggregate_passed=651, simulations_started=False,
             completion_sha256=observed.sha(runtime / 'gap65-completion.json'))
    new_json(runtime / 'checkpoint.json', checkpoint)
    new_json(runtime / 'gap65-complete-checkpoint.json', checkpoint)
    return completion


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    for mode in ('check', 'check-quick', 'prepare', 'finalize'):
        modes.add_argument('--' + mode, action='store_true')
    parser.add_argument('--runtime', type=Path, default=RUNTIME)
    parser.add_argument('--admission', type=Path, default=ADMISSION)
    parser.add_argument('--admission-sha256', default=ADMISSION_SHA)
    args = parser.parse_args()
    install_hooks()
    runtime, admission = args.runtime.resolve(), args.admission.resolve()
    if args.check_quick:
        proof = evidence.Evidence()
        _, recovered, _, audit, _ = validate_runtime(runtime, admission, args.admission_sha256, proof)
        full.check(proof.files)
        result = dict(status=recovered['status'], checked_files=len(proof.files),
                      independently_audited=audit['passed_cases'], target_newly_hit=True,
                      aggregate_admitted=False, tools_launched=False)
    elif args.check:
        checked = validate(runtime, admission, args.admission_sha256)
        result = dict(status='CHECKED_PASS_NOT_MERGED', checked_files=len(checked['proof'].files),
                      baseline_passed=650, tools_launched=False)
    else:
        result = (prepare if args.prepare else finalize)(runtime, admission, args.admission_sha256)
    print(json.dumps({k: v for k, v in result.items() if k not in ('files', 'checked_files')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
