#!/usr/bin/env python3
"""Audit existing raw RTL evidence without changing its failed worker or rerunning VCS."""
import argparse
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location('pair_frozen_owner', HERE/'run.py')
owner = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(owner)
require, digest, save, verify = owner.require, owner.digest, owner.save, owner.verify
EVIDENCE_KIND = 'POST_RUN_CHECKER_SEMANTICS_AUDIT'
FAILURES = dict(boundary="ValueError('Duplicate/replayed boundary allocation')",
                regression="ValueError('Unknown/malformed native work record')")


def load_checker(kind):
    require(kind in FAILURES, 'No reviewed checker correction for this case')
    path = HERE/kind/'check_successor.py'
    spec = importlib.util.spec_from_file_location('pair_postrun_'+kind, path)
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    return path, checker


def original_failure(report, kind):
    require(report['state'] == 'FAIL' and report['error'] == FAILURES[kind] and
            report['hardware_changed'] is False and report['whole_model'] is False,
            'Original failure is not the specifically reviewed checker rejection')


def audit(args):
    original, out = args.original.resolve(strict=True), args.output.resolve()
    require(original.is_relative_to(owner.OUT) and out.is_relative_to(owner.OUT) and
            not out.exists() and not out.is_relative_to(original), 'Use a new independent audit directory')
    out.mkdir()
    status_path = out/'status.json'
    status = dict(state='PREFLIGHT', owner_pid=os.getpid(), child_pid=None,
                  started=datetime.now(timezone.utc).isoformat())
    result = dict(state='FAIL', evidence_kind=EVIDENCE_KIND, new_rtl_execution=False,
                  original_worker_relabelled=False, original_worker=str(original),
                  hardware_changed=False, whole_model=False, deployment_approved=False)
    save(status_path, status)
    try:
        old_report, old_status = original/'result.json', original/'status.json'
        failure, terminal = json.loads(old_report.read_text()), json.loads(old_status.read_text())
        kind = terminal['kind']
        require(kind in FAILURES and terminal['state'] == 'FAIL' and terminal['child_pid'] is None and
                'finished' in terminal, 'Original worker is not terminal')
        original_failure(failure, kind)
        builddir, socdir, work = Path(terminal['build']), Path(terminal['soc_build']), original/'work'
        soc, pins = owner.checked_soc(socdir)
        software, extra = owner.checked_software(builddir)
        pins = owner.combine(pins, extra)
        inherited = json.loads((original/'source-pins.json').read_text())
        pins = owner.combine(pins, inherited)
        checker_path, checker = load_checker(kind)
        extra = {str(p): digest(p) for p in (Path(__file__), HERE/'test_audit_successor.py',
                 checker_path, checker_path.with_name('test_successor.py'),
                 old_report, old_status, original/'source-pins.json')}
        raw_pins = {str(p): digest(p) for p in work.iterdir() if p.is_file()}
        pins = owner.combine(pins, owner.combine(extra, raw_pins))
        save(out/'source-pins.json', pins)
        verify(pins)
        log, vector = work/'run.vcs.log', work/'vector_trace.csv'
        launch = json.loads((work/'console.command.json').read_text())
        expected = [soc['simv'], '-no_save', '-l', str(log), '+PRELOAD='+software['elf'],
                    '+TESTCASE=akv_pair_'+kind, '+NO_FSDB', '+NO_INSTR_TRACE',
                    '+VECTOR_TRACE='+str(vector), '+COMMIT_TRACE='+str(work/'commit.csv'),
                    '+AKV_PERF', '+AKV_SUMMARY', '+ARA_CONTRACT_TRACE_LIMIT=2000000',
                    '+ARA_UVM_TRACE_LIMIT=2000000']
        require(launch['argv'] == expected and launch['cwd'] == str(work), 'Original executable/launch drift')
        owner.successful_log(log.read_text())
        measured = checker.check_run(log, builddir)
        vector_work = checker.check_vector_workcounts(vector, builddir)
        require(measured.get('state') == 'PASS' and vector_work, 'Independent raw functional/work audit failed')
        env = os.environ.copy()
        env.update(PYTHONPATH=str(owner.ROOT/'verification'), PYTHONDONTWRITEBYTECODE='1',
                   READELF='/usr/bin/readelf', LC_ALL='C')
        os.environ.update(env)
        proofpath = out/'uvm_result.json'
        owner.execute([sys.executable, '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
                       '--require-backend', '--require-axi', '--require-axi-write',
                       '--vector-trace', vector, '--log', log, '--simv', soc['simv'], '--elf', software['elf'],
                       '--output', proofpath], out, out/'protocol.log', 600, status, status_path, 'PROTOCOL_CHECK')
        proof = json.loads(proofpath.read_text())
        require(proof.get('status') == 'PASS' and proof.get('issues') == [] and
                proof['elf_sha256'] == software['elf_sha256'] and proof['log_sha256'] == digest(log) and
                proof['vector_trace_sha256'] == digest(vector), 'Protocol audit/identity failed')
        verify(pins)
        result.update(state='PASS', kind=kind, performance_measured=kind != 'boundary',
                      independent_protocol_checked=True, post_pins_match=True,
                      measured=measured, vector_command_work=vector_work, raw_work=str(work),
                      original_worker_report=str(old_report), original_worker_report_sha256=digest(old_report),
                      original_worker_state='FAIL', original_worker_error=failure['error'],
                      configuration=soc['configuration'], image_sha256=digest(soc['simv']),
                      software_sha256=software['elf_sha256'], build=str(builddir), soc_build=str(socdir),
                      checker_successor=str(checker_path), checker_successor_sha256=digest(checker_path),
                      source_pins_sha256=digest(out/'source-pins.json'),
                      scope='Separate functional/protocol audit of immutable original raw execution; not a clean original-worker PASS',
                      artifacts={**raw_pins, **{str(p): digest(p) for p in out.iterdir()
                                 if p.is_file() and p.name not in ('status.json', 'result.json')}})
    except BaseException as exc:
        result.update(error=repr(exc))
        raise
    finally:
        save(out/'result.json', result)
        status.update(state=result['state'], child_pid=None, finished=datetime.now(timezone.utc).isoformat())
        save(status_path, status)
    print(json.dumps(dict(state=result['state'], evidence_kind=EVIDENCE_KIND, output=str(out))))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    audit(parser.parse_args())
