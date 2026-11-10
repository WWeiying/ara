#!/usr/bin/env python3
"""Explicit-review QK architectural runner. Preparation never executes simv."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
import cases
import check
from generate import HERE, ROOT, OUT, need, sha, verify
from build import OWN, save

CPU_POST = 'ce293df18df94a81a0e4fe99ebc798a356c437219de79d79f900bf2362f93249'
SIM_SECONDS, PROTOCOL_SECONDS, SERVICE_SECONDS = 5400, 900, 7200


def checked_soc(path):
    path = Path(path).resolve(strict=True)
    m = json.loads((path / 'build.json').read_text())
    need(m['state'] == 'STAGE3_SOC_BUILT_NOT_EXECUTED' and m['post_pins_match'] and
         m['source_pins_sha256'] == sha(path / 'source-pins.json'), 'Not the fresh stage3 image contract')
    c = m['configuration']
    needed = dict(nr_lanes=4, vlen=1024, shared_simd_multiplier=1, shared_fma=0, ideal_dispatcher=0,
                  qbs_enabled=1, akv_enabled=1, akv_v2_enabled=1, resident_qk_enabled=1,
                  resident_pv_enabled=1, resident_capability=0, sim_l2_bytes=16777216, qbs_lane_multiplier=0)
    need(all(c.get(k) == v for k, v in needed.items()), 'SoC configuration mismatch')
    need(c['cpu_retirement_overlay']['after_sha256'] == CPU_POST, 'CPU retirement fix missing')
    pins = json.loads((path / 'source-pins.json').read_text())
    verify(pins); verify(m['image_pins'])
    need(sha(path / 'source/hardware/deps/cva6/core/commit_stage.sv') == CPU_POST, 'Patched CPU byte identity mismatch')
    need(m['simv'] == str(path / 'sim/simv') and m['simv'] in m['image_pins'], 'Unpinned/wrong simulator')
    return m, pins | m['image_pins'] | {str(path / 'build.json'): sha(path / 'build.json'),
                                         str(path / 'source-pins.json'): sha(path / 'source-pins.json')}


def recipes(out, soc, software, software_build):
    work = out / 'work'
    python = str(Path(sys.executable).resolve())
    return dict(simulation=[soc['simv'], '-no_save', '-l', str(work / 'run.vcs.log'),
        '+PRELOAD=' + software['elf'], '+TESTCASE=resident_qk_boundary', '+NO_FSDB', '+NO_INSTR_TRACE',
        '+VECTOR_TRACE=' + str(work / 'vector_trace.csv'), '+COMMIT_TRACE=' + str(work / 'commit.csv'),
        '+AKV_PERF', '+AKV_SUMMARY', '+RESIDENT_PV_PERF', '+RESIDENT_PV_WATCHDOG',
        '+ARA_CONTRACT_TRACE_LIMIT=2000000', '+ARA_UVM_TRACE_LIMIT=2000000'],
        protocol=[python, '-B', '-m', 'ara_verify.uvm_dut', '--require-events', '--require-backend',
            '--require-axi', '--require-axi-write', '--vector-trace', str(work / 'vector_trace.csv'),
            '--log', str(work / 'run.vcs.log'), '--simv', soc['simv'], '--elf', software['elf'],
            '--output', str(work / 'uvm_result.json')],
        boundary=[python, '-B', str(out / 'inputs/qk_boundary/check.py'), '--build', str(software_build),
            '--log', str(work / 'run.vcs.log'), '--vector', str(work / 'vector_trace.csv'),
            '--commit', str(work / 'commit.csv')])


def scoped_exceptions(text, vectors, proof, uvm):
    events, issues = uvm._events(text, '[ARA_CONTRACT_TRACE]', uvm._CONTRACT_EVENT, 16)
    need(not issues and events, 'Contract trace malformed/missing')
    pending, transactions = {}, []
    for cycle, req, rid, word, resp, sid, exc in events:
        old = pending.pop(sid) if resp and sid in pending else None
        if req:
            need(rid not in pending, 'Duplicate CVXIF transaction')
            current = dict(instruction=word, error=None, request_cycle=cycle)
            pending[rid] = current
            transactions.append(current)
        if resp:
            owner = old if old is not None else pending.pop(sid, None)
            need(owner is not None, 'Orphan CVXIF response')
            owner.update(error=exc, response_cycle=cycle)
    need(not pending, 'Unreturned CVXIF request')
    expected = []
    for s in cases.attempts(vectors['cases']):
        if not (s['error'] and s['kind'] in ('fs_off', 'vs_off')):
            expected.append((s['instruction'], s['error']))
        if s['id'] == 0:
            expected.append((cases.QK, 0))  # Parent leaf helper, after direct call.
    actual = [(r['instruction'], r['error']) for r in transactions if check.qk(r['instruction'])]
    need(actual == expected and len(actual) == 34, 'QK actual request/exception sequence')
    need(all(r['error'] == 0 for r in transactions if not check.qk(r['instruction'])) and
         sum(r['error'] for r in transactions) == proof['contract_counts']['exceptions'] == 10,
         'Unexpected exception outside ten accelerator rejects')
    return dict(qk_requests=34, accelerator_rejections=10, cpu_only_off_rejections=2, issues_ignored=0)


def prepare(out, socdir, software_build):
    need(out.parent == OUT and not out.exists(), 'Use unique direct signoff output')
    soc, pins = checked_soc(socdir)
    software, _, _ = check.checked_build(software_build)
    pins.update(json.loads((software_build / 'source-pins.json').read_text()))
    pins.update(software['artifacts'])
    pins[str(software_build / 'build.json')] = sha(software_build / 'build.json')
    out.mkdir(); (out / 'work').mkdir(); (out / 'inputs').mkdir()
    local = out / 'inputs/qk_boundary'
    local.mkdir()
    for name in OWN:
        source = software_build / 'inputs/qk_boundary' / name
        shutil.copyfile(source, local / name)
    # Full checker package inventory, not just the entry point. No global edits.
    for source in (ROOT / 'verification/ara_verify').rglob('*.py'):
        dest = out / 'inputs/verification' / source.relative_to(ROOT / 'verification')
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, dest)
        pins[str(source)] = sha(source)
    selection = dict(soc_build=str(socdir), software_build=str(software_build),
                     commands=recipes(out, soc, software, software_build),
                     sim_seconds=SIM_SECONDS, protocol_seconds=PROTOCOL_SECONDS, service_seconds=SERVICE_SECONDS,
                     protocol_note='Legacy AKV-column classification is not QK semantic acceptance; independent QK checker required')
    save(out / 'selection.json', selection)
    for p in (*out.joinpath('inputs').rglob('*'), out / 'selection.json', Path(sys.executable).resolve(),
              Path('/usr/bin/systemd-run'), Path('/usr/bin/systemctl')):
        if p.is_file(): pins[str(p)] = sha(p)
    verify(pins)
    save(out / 'source-pins.json', pins)
    save(out / 'prepared.json', dict(state='PREPARED_NOT_EXECUTED', parent_review_required=True,
                                     source_pins_sha256=sha(out / 'source-pins.json')))
    return dict(output=str(out), source_pins_sha256=sha(out / 'source-pins.json'),
                frozen_runner=str(local / 'run.py'), execution='NOT_RUN')


def execute(out, review):
    need(Path(__file__).resolve() == out / 'inputs/qk_boundary/run.py' and
         sha(out / 'source-pins.json') == review, 'Frozen worker/explicit review hash required')
    need(not (out / 'attempt.json').exists() and not any((out / 'work').iterdir()), 'No repeat execution')
    unit = 'resident-qk-boundary-' + out.name + '.service'
    main = int(subprocess.check_output(['systemctl', '--user', 'show', unit, '-p', 'MainPID', '--value'], text=True).strip())
    cgroup = Path('/proc/self/cgroup').read_text()
    need(main == os.getpid() and unit in cgroup, 'systemd must directly own worker')
    save(out / 'attempt.json', dict(pid=os.getpid(), cgroup=cgroup, review_sha256=review))
    s = json.loads((out / 'selection.json').read_text())
    pins = json.loads((out / 'source-pins.json').read_text())
    work = out / 'work'
    report = dict(state='FAIL', automatic_retry=False, performance_measured=False, deployment_approved=False,
                  numerical_checked=False, independent_protocol_checked=False)
    environment = os.environ.copy()
    environment.update(PYTHONPATH=str(out / 'inputs/verification'), PYTHONDONTWRITEBYTECODE='1')

    def run_command(name, timeout):
        with (work / (name + '.log')).open('x') as stream:
            subprocess.run(s['commands'][name], cwd=work, env=environment, stdout=stream,
                           stderr=subprocess.STDOUT, check=True, timeout=timeout)
    try:
        verify(pins)
        soc, _ = checked_soc(Path(s['soc_build']))
        software, vectors, _ = check.checked_build(Path(s['software_build']))
        print('QK_BOUNDARY_RUNNING', flush=True)
        run_command('simulation', SIM_SECONDS)
        log, vector = work / 'run.vcs.log', work / 'vector_trace.csv'
        text = log.read_text()
        need(text.count('Core Test *** SUCCESS ***') == 1 and
             not re_failure(text), 'Unsuccessful/ambiguous EOC or UVM/fatal failure')
        run_command('protocol', PROTOCOL_SECONDS)
        proof = json.loads((work / 'uvm_result.json').read_text())
        image = {p: h for p, h in soc['image_pins'].items() if p == soc['simv'] or p.endswith('.so')}
        need(any(p.endswith('.so') for p in image) and proof.get('status') == 'PASS' and proof.get('issues') == [] and
             proof.get('elf_sha256') == software['elf_sha256'] and proof.get('simv_sha256') == sha(soc['simv']) and
             proof.get('sim_image_sha256') == image and proof.get('log_sha256') == sha(log) and
             proof.get('vector_trace_sha256') == sha(vector), 'Independent protocol evidence identity')
        sys.path.insert(0, str(out / 'inputs/verification'))
        from ara_verify import uvm_dut
        negative = scoped_exceptions(text, vectors, proof, uvm_dut)
        run_command('boundary', 300)
        checked = json.loads((work / 'boundary.log').read_text())
        need(checked['numerical_checked'] and checked['architecture_checked'] and not checked['protocol_checked'],
             'Architectural checker scope mismatch')
        for p in (log, vector, work / 'commit.csv'):
            need(checked['evidence_sha256'][str(p)] == sha(p), 'Architectural evidence mismatch')
        verify(pins)
        verify(soc['image_pins'])
        report.update(state='PASS', numerical_checked=True, independent_protocol_checked=True,
                      architecture_checked=True, post_pins_match=True, negative=negative, work=checked['work'])
    except Exception as exc:
        report['error'] = repr(exc)
    report['source_pins_sha256'] = sha(out / 'source-pins.json')
    report['artifacts'] = {str(p): sha(p) for p in work.rglob('*') if p.is_file()}
    save(out / 'report.json', report)
    return 0 if report['state'] == 'PASS' else 1


def re_failure(text):
    import re
    return bool(re.search(r'(?m)(?:^UVM_(?:ERROR|FATAL)\b(?!\s*:\s*0\s*$)|^Fatal:|^Error-|Core Test \*\*\* FAILED)', text))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('action', choices=('prepare', 'run'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--soc-build', type=Path)
    p.add_argument('--software-build', type=Path)
    p.add_argument('--parent-reviewed', action='store_true')
    p.add_argument('--review-sha256')
    a = p.parse_args()
    need(a.output.is_absolute() and a.output.parent == OUT, 'Invalid signoff output')
    if a.action == 'prepare':
        need(a.soc_build is not None and a.software_build is not None, 'Explicit SoC and software build required')
        print(json.dumps(prepare(a.output, a.soc_build.resolve(), a.software_build.resolve()), sort_keys=True))
    else:
        need(a.parent_reviewed and a.review_sha256, 'Explicit review required, no automatic run')
        raise SystemExit(execute(a.output, a.review_sha256))
