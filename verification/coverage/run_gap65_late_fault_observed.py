#!/usr/bin/env python3
"""One sealed gap65 case, read-only UCLI witness, no collection or DVE hook.

--prepare and --check never start a subprocess. --run is for a future explicitly
authorized execution, with the externally retained admission SHA256 required.
The existing host preflight, runner and independent audit are not modified.
"""
import argparse
import csv
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import sys
sys.dont_write_bytecode = True
import coverage_evidence as evidence
import coverage_bitmap_delta as bitmaps
import gap65_late_fault_checks as checks
import run_gap65_late_fault_checked_extension as host
from ara_verify.runner import RegressionRunner, RunOptions, _cancel_signals
from ara_verify.model import TestCase
from ara_verify.plan import audit_run

ROOT, full, require = checks.ROOT, evidence.full, evidence.require
SCRIPT = Path(__file__).resolve()
OBSERVER = ROOT / 'verification/probes/gap65_late_fault.tcl'
HOST = ROOT / 'verification/out/gap65-late-fault-preflight-20261004-02'
BASELINE = ROOT / 'verification/out/gap67-current-20261004-01'
DOCS = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1/doc/UserGuide/smartsearch/doc/html/ucli_ug/commands')
FIELDS = 'clk rst_n cycle state next_state fault m n k_blocks row_base integer_busy compute_active issue_active commit vrf_req'.split()
NAME, CASE = checks.NAME, host.CASE
sha, save, read = full.base.sha256, full.save, full.read


def observer_samples(text):
    rows = list(csv.reader(io.StringIO(text), delimiter='\t'))
    require(len(rows) == 4 and rows[0] == ['phase', *FIELDS] and rows[3] == ['END'],
            'missing/extra/partial observer records')
    samples = []
    for row, phase in zip(rows[1:3], ('before', 'after')):
        require(len(row) == len(FIELDS) + 1 and row[0] == phase, 'observer phase/field mismatch')
        values = []
        for field in row[1:]:
            match = re.fullmatch(r"(?:[0-9]*'d)?([0-9]+)", field)
            require(match is not None, 'unknown or nondecimal observer value: ' + field)
            values.append(int(match[1]))
        samples.append(dict(zip(FIELDS, values)))
    for sample in samples:
        require(all(sample[k] == v for k, v in dict(clk=0, rst_n=1, m=4, n=5,
            k_blocks=1, row_base=0, commit=0, vrf_req=0).items()), 'observer command/reset/commit mismatch')
    require(samples[0]['integer_busy'] == samples[0]['compute_active'] == samples[0]['issue_active'] == 1,
            'fault not observed during active integer computation')
    checks.check_state_samples(samples)
    return samples


def verify_plan(path, digest):
    proof = evidence.Evidence()
    proof.pin(path, digest)
    plan = proof.read(path)
    require(plan['status'] == 'READY_FOR_REVIEW_NO_RTL_RUN' and plan['case'] == CASE and
            plan['timeout_s'] == 300 and plan['observer'] == str(OBSERVER) and
            plan['host_preflight'] == str(HOST), 'foreign or unbounded gap65 admission')
    proof.hashes(plan['files'])
    require(full.batch.simulation_image(Path(plan['simv'])) == plan['image'], 'image membership drift')
    require(full.base.inventory(Path(plan['design_vdb'])) == plan['design_files'], 'design VDB drift')
    return plan, proof.files


def prepare(output):
    require(output.parent == ROOT / 'verification/out' and
            output.name.startswith('gap65-late-fault-preflight-') and not output.exists(), 'fresh gap65 preflight required')
    admission = evidence.Evidence()
    spec = admission.read(HOST / 'selection.checked-draft.json')
    require(len(spec['cases']) == 1, 'one host case required')
    host.precheck(spec['cases'][0], admission, evidence.precheck)
    # One full host recheck above; runtime needs the immutable result records,
    # not repeated rehashes of every historical test VDB.
    proof = evidence.Evidence()
    proof.hashes(proof.read(HOST / 'draft.sha256.json'))
    for name in ('tool_hashes.json', 'link-inputs.json', 'artifact_hashes.json', 'source_hashes.json'):
        proof.hashes(proof.read(HOST / name))
    prior = proof.plan(BASELINE)
    require(prior['image'] == admission.plan(checks.BASE)['image'], '650 image differs from host preflight')
    proof.hashes(prior['image'])
    proof.hashes(prior['design_files'])
    collection = proof.read(BASELINE / 'collection.json')
    checkpoint = proof.read(BASELINE / 'checkpoint.json')
    require(collection['status'] == 'PASS' and collection['passed'] == 650 and
            collection['image'] == prior['image'] and checkpoint['coverage_status'] == 'COMPLETE',
            'completed 650 baseline required')
    for name in ('all-passed-outcomes.json', 'combined-bits.json'):
        proof.pin(BASELINE / name, collection['reports'][str(BASELINE / name)])
    rows = proof.read(BASELINE / 'all-passed-outcomes.json')
    bits = proof.read(BASELINE / 'combined-bits.json')
    require(len(rows) == 650 and bits['tests'] == [r['vdb'] for r in rows], '650 membership differs')
    target = bits['metrics']['fsm'][checks.TARGET_SCOPE]
    require(target['checksum'] == checks.TARGET['definition_checksum'] and target['width'] == 43 and
            format(int(target['bits'], 16), '043b')[15] == '0', '650 target shape/zero bit differs')
    simdir = Path(prior['simv']).parent
    source = proof.read(simdir / 'vcs_source_manifest.json')
    require(full.base.sources(simdir / 'vcs_source_manifest.json') == source, 'compiled source inventory drift')
    proof.hashes({row['path']: row['sha256'] for row in source['files']})
    for path in (simdir / 'simulator.conf', simdir / 'simv.daidir/vcs_rebuild'):
        proof.pin(path)
    paths = [SCRIPT, OBSERVER, ROOT / 'verification/tests/test_gap65_observed.py',
             HOST / 'local-tests.json', HOST / 'local-tests.log',
             *(DOCS / n for n in ('breakpoint_commands.html', 'simulation_advancing_commands.html',
                                  'signal_variable_expression_commands.html'))]
    for module in tuple(sys.modules.values()):
        path = getattr(module, '__file__', None)
        if path and Path(path).resolve().is_relative_to(ROOT / 'verification'):
            paths.append(Path(path).resolve())
    for path in paths:
        proof.pin(path)
    require(read(HOST / 'local-tests.json')['status'] == 'PASS', 'host unit tests failed')
    output.mkdir()
    plan = dict(status='READY_FOR_REVIEW_NO_RTL_RUN', case=CASE, timeout_s=300,
        host_preflight=str(HOST), observer=str(OBSERVER), elf=spec['cases'][0]['binary'],
        elf_sha256=spec['cases'][0]['binary_sha256'], baseline=str(BASELINE), baseline_passed=650,
        simv=prior['simv'], image=prior['image'], design_vdb=prior['design_vdb'],
        design_files=prior['design_files'], files=proof.files, target=checks.TARGET,
        baseline_validation='Completed collection/ledger/combined-bits hashes only at runtime; fullbatch must readmit VDBs before any aggregate merge.',
        host_admission_checked_files=len(admission.files),
        observer_api='documented conditional negedge stop, get -radix decimal, run; no HDL writes',
        observer_budget=dict(snapshots=2, signal_reads=30, seek_limit_ns=100000,
            ordinary_estimate_s=read(HOST / 'cost-preflight.json')['conditional_seconds_upper'],
            wall_cap_s=300, overhead_measured=False, automatic_retry=False,
            note='Constant-count Tcl snapshots replace polling. 300s is a fail-closed cap, not a measured runtime guarantee.'),
        launch_authorized=False, simulation_started=False, rtl_pass=False,
        old_observer_gate_preserved=True, scope='standalone diagnostic only; no batch/DVE/coverage-policy application')
    full.check(proof.files)
    save(output / 'admission.json', plan)
    digest = sha(output / 'admission.json')
    save(output / 'admission.sha256.json', {str(output / 'admission.json'): digest})
    verify_plan(output / 'admission.json', digest)
    print(json.dumps(dict(status=plan['status'], admission_sha256=digest, output=str(output))))


def expected_args(output):
    artifact = output / 'results/tests' / ('app_' + NAME)
    return ['-l', 'run.vcs.log', '+ntb_random_seed=1', '+PRELOAD=' + str(artifact / 'input.elf'),
            '+TESTCASE=' + NAME, '+NO_FSDB', '+COMMIT_TRACE=' + str(artifact / 'commit_trace.csv')]


def simulator_command(plan, output, args, cwd):
    require(cwd == output / 'results/tests' / ('app_' + NAME) / 'work', 'foreign observer work directory')
    require(args == expected_args(output), 'simulator arguments differ from exact gap65 command')
    require(sha(cwd.parent / 'input.elf') == plan['elf_sha256'], 'runtime ELF snapshot drift')
    require(not (cwd / 'gap65-observer.tsv').exists(), 'existing observer capture')
    command = full.batch.adapter_command(dict(simv=plan['simv'], image=plan['image'],
                                              results=str(output / 'results')), args, cwd)
    return [command[0], '-ucli', '-do', plan['observer'], '-no_save', *command[1:]]


def revalidate(path, digest, original, runtime_pins):
    plan, current = verify_plan(path, digest)
    require(current == original, 'admission-bound expected pin set changed')
    full.check(runtime_pins)
    return plan


def sim_exec(config, config_sha, args):
    require(sha(config) == config_sha, 'runtime config changed')
    runtime = read(config)
    plan, _ = verify_plan(Path(runtime['admission']), runtime['admission_sha256'])
    full.check(runtime['files'])
    output = config.parent
    command = simulator_command(plan, output, args, Path.cwd().resolve())
    save(Path.cwd() / 'coverage.command.json', dict(command=command, cwd=str(Path.cwd())))
    os.execv(command[0], command)


def run(path, digest, output):
    plan, original = verify_plan(path, digest)
    require(output.parent == ROOT / 'verification/out' and
            output.name.startswith('gap65-late-fault-runtime-') and not output.exists(), 'fresh isolated runtime required')
    output.mkdir()
    inputs = output / 'inputs'
    inputs.mkdir()
    elf = inputs / (NAME + '.elf')
    shutil.copyfile(plan['elf'], elf)
    require(sha(elf) == plan['elf_sha256'], 'copied ELF differs')
    shutil.copyfile(Path(plan['simv']).parent / 'simulator.conf', inputs / 'simulator.conf')
    config = output / 'runtime.json'
    save(config, dict(admission=str(path), admission_sha256=digest,
                      files=full.pins([elf, inputs / 'simulator.conf'])))
    wrapper = inputs / 'observed_simv'
    wrapper.write_text('#!/bin/sh\nexec ' + shlex.join([sys.executable, '-B', str(SCRIPT),
        '--sim-exec', str(config), '--config-sha256', sha(config), '--']) + ' "$@"\n')
    wrapper.chmod(0o755)
    Path(str(wrapper) + '.daidir').symlink_to(plan['simv'] + '.daidir', target_is_directory=True)
    runtime_pins = full.pins([config, wrapper, elf, inputs / 'simulator.conf'])
    result_root = output / 'results'
    result_root.mkdir()
    save(result_root / 'run.json', dict(status='RUNNING', invocation=sys.argv,
        source_snapshot={'sha256': digest}, input_snapshots=True, commit_trace=True, timeout_s=300))
    test = TestCase(CASE, 'app', 'unused-no-build', elf, NAME, 300)
    options = RunOptions(ROOT, result_root, 'default', 1, 1, False, False, True, wrapper, True, 300)
    runner = RegressionRunner(options, [test], sys.argv)
    try:
        revalidate(path, digest, original, runtime_pins)
        with _cancel_signals(runner.cancel_event):
            result = runner._run_test(test, wrapper)
        runner._write_reports([result])
        require(result.status == 'PASS', 'ordinary checked-app result: ' + result.status)
        artifact = result.artifact_dir
        for log in (artifact / 'console.log', artifact / 'work/run.vcs.log'):
            checks.check_runtime_log(log.read_text(), read(HOST / 'elf-proof.json'))
        samples = observer_samples((artifact / 'work/gap65-observer.tsv').read_text())
        report = audit_run(result_root, require_trace=True)
        save(output / 'independent_audit.json', report)
        full.batch.audit_ok(report, dict(kind='directed', source_name=CASE), artifact)
        vdb = artifact / 'work/code.vdb'
        vdb_files = full.batch.valid_vdb(vdb, NAME, plan['simv'])
        command = simulator_command_after(plan, output, artifact)
        require(shlex.split(full.batch.xml_root(vdb / 'snps/coverage/db/testdata' / NAME /
                    'siminfo.xml').find('srctest').get('cmdline')) == command, 'VDB observer command differs')
        raw = bitmaps.read_metric(vdb / 'snps/coverage/db/testdata' / NAME / 'fsm.verilog.data.xml')
        before = read(Path(plan['baseline']) / 'combined-bits.json')['metrics']['fsm'][checks.TARGET_SCOPE]
        gain = checks.check_target_delta(before, raw[checks.TARGET_SCOPE])
        report = dict(status='PASS', scope='one isolated diagnostic; not aggregate admission',
            samples=samples, target_delta=gain, raw_before=before, raw_after=raw[checks.TARGET_SCOPE],
            vdb=str(vdb), vdb_files=vdb_files, admission_sha256=digest,
            files=full.pins([p for p in result_root.rglob('*') if p.is_file()]) |
                  full.pins([output / 'independent_audit.json']))
        full.check(vdb_files)
        revalidate(path, digest, original, runtime_pins)
        save(output / 'result.json', report)
        return 0
    except Exception as error:
        save(output / 'rejected.json', dict(status='REJECTED', reason=str(error),
             aggregate_admitted=False, retry_allowed=False))
        raise


def simulator_command_after(plan, output, artifact):
    command = [plan['simv'], '-ucli', '-do', plan['observer'], '-no_save', *expected_args(output),
               '-cm', full.base.METRICS, '-cm_dir', str(artifact / 'work/code.vdb'), '-cm_name', NAME]
    require(read(artifact / 'work/coverage.command.json')['command'] == command, 'runtime command record differs')
    return command


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument('--prepare', action='store_true')
    modes.add_argument('--check', action='store_true')
    modes.add_argument('--run', action='store_true')
    modes.add_argument('--sim-exec', type=Path)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--admission', type=Path)
    parser.add_argument('--admission-sha256')
    parser.add_argument('--config-sha256')
    parser.add_argument('sim_args', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.sim_exec:
        require(args.sim_args[:1] == ['--'], 'missing internal argument separator')
        return sim_exec(args.sim_exec, args.config_sha256, args.sim_args[1:])
    if args.prepare:
        require(args.output is not None, '--output required')
        return prepare(args.output.resolve())
    require(args.admission is not None and args.admission_sha256 is not None,
            'external admission digest required')
    if args.check:
        _, files = verify_plan(args.admission.resolve(), args.admission_sha256)
        print(json.dumps(dict(status='PASS_PREPARATION_ONLY', checked_files=len(files), vcs_launched=False)))
        return 0
    require(args.output is not None, '--output required')
    return run(args.admission.resolve(), args.admission_sha256, args.output.resolve())


if __name__ == '__main__':
    raise SystemExit(main())
