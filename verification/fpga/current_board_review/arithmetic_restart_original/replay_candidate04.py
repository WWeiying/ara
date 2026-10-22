#!/usr/bin/env python3
"""Prepare five original prefixes; parent-only launch after terminal regression38.

No waiting worker, polling, image build, ELF rebuild or automatic retry.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REVIEW = HERE.parent
sys.path.insert(0, str(REVIEW / 'integration'))
import replay_memory_regression as base

read, save, sha, require = base.read, base.save, base.sha, base.require
PREPARED = HERE / 'prepared02'
PRIOR = REVIEW / 'integration/candidate04_regression38_03'
IMAGE = Path('/home/wangwy/fpga_runs/current_board_memory_candidate04/campaign/image')
IMAGE_SHA = 'e26b4a68939946d104c37917cf688a40ea6e1f963f048a586a5662d58c368673'
NAMES = ['arithmetic_e8_m4_prefix56', 'arithmetic_e8_m8_prefix38',
         'arithmetic_e16_m8_prefix56', 'arithmetic_e8_m2_prefix56', 'arithmetic_e16_m4_prefix56']
COUNTS = [56, 38, 56, 56, 56]
TIMEOUTS = [4000, 4000, 4000, 1800, 1800]
RESERVATIONS = {'nf7': (2, REVIEW / 'masked_translation/indexed_review'),
                'nf8': (8, REVIEW / 'masked_translation/nf8_strided_review'),
                'gather': (4, REVIEW / 'gather_original_review'),
                'whole': (6, REVIEW / 'whole_register_original')}
BAD = re.compile(r'\bRVV_[A-Z0-9_]*FAIL[A-Z0-9_]*\b|RVV_MATRIX_UNSUPPORTED_CAPACITY|'
                 r'BOARD_CASE_FAIL|BOARD_REPLAY_(?:TRAP|MISMATCH|SERVICE_FAIL|VLEN_FAIL)|'
                 r'\b(?:MATRIX_FAIL|EXTENSION_MATRIX_FAIL|EXTENDED_FAIL|EPOCH_FAIL)\b|'
                 r'Core Test \*\*\* FAIL|Error-\[|\b[Ff][Aa][Tt][Aa][Ll]\b|UVM_FATAL|\bSKIP\b')


def console_ok(text, entry):
    lines = [line.strip() for line in text.splitlines()]
    markers = ['BOARD_CASE_BEGIN ' + entry['id'], *entry['pass_markers']]
    return (bool(entry['pass_markers']) and len(markers) == len(set(markers)) and
            all(lines.count(marker) == 1 for marker in markers) and
            text.count('Core Test *** SUCCESS *** (tohost = 0)') == 1 and
            '$finish' in text and BAD.search(text) is None)


def identity():
    require(sha(IMAGE / 'image.json') == IMAGE_SHA, 'Wrong frozen M4 image')
    base.IMAGE = IMAGE
    return base.image_context()


def runner_class(parent, entries):
    class Runner(parent):
        def _run_test(self, test, image):
            try:
                result = super()._run_test(test, image)
                if result.status == 'PASS':
                    text = (result.artifact_dir / 'console.log').read_text()
                    if result.returncode != 0 or not console_ok(text, entries[test.name]):
                        result.status, result.reason = 'FAIL', 'Exact original oracle/raw failure veto'
                if result.status not in ('PASS', 'DRY_RUN'):
                    self.cancel_event.set()
                return result
            except BaseException:
                self.cancel_event.set()
                raise
    return Runner


def execute(data, out, dry):
    ledger, repo, (parent, options_type, testcase, _) = identity()
    entries = {c['id']: c for c in data['cases']}
    tests = [testcase(c['id'], 'app', '', Path(c['elf']), c['id'], c['timeout_s']) for c in data['cases']]
    options = options_type(repo, out, 'default', 2, 1, dry,
                           False, True, Path(ledger['simv']), True, None)
    return runner_class(parent, entries)(options, tests, sys.argv).run()


def makespan(durations):
    workers = [0, 0]
    for seconds in durations:
        index = workers.index(min(workers))
        workers[index] += seconds
    return max(workers)


def prepare(out):
    require(not out.exists(), 'Fresh owned output required')
    ready = read(HERE / 'readiness01.json')
    require(ready['status'] == 'READY_REFERENCE_ONLY_NO_DUT' and ready['spike_pass'] == 5 and
            ready['host_positive_runs'] == 10 and ready['host_negative_rejections'] == 40,
            'Reference readiness missing')
    programs = read(PREPARED / 'soc/programs.json')
    require(list(programs['programs']) == NAMES and programs['backend'] == 'vcs-soc', 'Wrong five ELFs')
    require(programs['provenance_sha256'] == sha(PREPARED / 'prepared/provenance.json'), 'Source manifest drift')
    base.shared.check(PREPARED / 'prepared')
    pins = {**read(PREPARED / 'input_pins.json'), **ready['evidence']}
    base.verify_pins(pins)
    ledger, repo, _ = identity()
    snapshot = Path(ledger['snapshot']) / 'snapshot.json'
    pins.update(ledger['files'])
    pins.update({str(repo / name): digest for name, digest in read(snapshot)['files'].items()})
    for path in [Path(__file__).resolve(), HERE / 'test_replay_candidate04.py', HERE / 'readiness01.json',
                 Path(base.__file__), Path(base.shared.__file__), REVIEW / 'integration/prepare.py',
                 IMAGE / 'image.json', snapshot, Path(ledger['simv']).parent / 'simulator.conf',
                 Path(ledger['simv']).parent / 'vcs_source_manifest.json', PRIOR / 'plan.json']:
        pins[str(path)] = sha(path)
    for path in PREPARED.rglob('*'):
        if path.is_file(): pins[str(path)] = sha(path)
    out.mkdir(parents=True)
    tested = subprocess.run([sys.executable, '-B', '-m', 'unittest', '-v', 'test_replay_candidate04'],
                            cwd=HERE, capture_output=True, text=True, timeout=60)
    (out/'host_tests.log').write_text(tested.stdout + tested.stderr)
    require(tested.returncode == 0, 'Replay host checks failed')
    pins[str(out/'host_tests.log')] = sha(out/'host_tests.log')
    (out / 'inputs').mkdir()
    cases = []
    for name, count, timeout in zip(NAMES, COUNTS, TIMEOUTS):
        entry = programs['programs'][name]
        proof = next(r for r in ready['records'] if r['id'] == name)
        require(entry['configurations'] == proof['configurations'] == count, 'Wrong original trial count')
        require(proof['proposed_inner_timeout_s'] == timeout, 'Original budget changed')
        require(sha(Path(entry['path'])) == entry['sha256'] == proof['soc_elf_sha256'], 'ELF drift')
        elf = out / 'inputs' / (name + '.elf')
        shutil.copyfile(entry['path'], elf)
        require(sha(elf) == entry['sha256'], 'Copy drift')
        elf.chmod(0o444); pins[str(elf)] = entry['sha256']
        cases.append(dict(id=name, elf=str(elf), sha256=entry['sha256'], original_port_elf=entry['path'],
                          pass_markers=entry['pass_markers'], configurations=count, timeout_s=timeout,
                          target_pc=entry['target_pc'], target_opcode=entry['target_opcode'], evidence=proof))
    data = dict(status='PREPARED_NOT_LAUNCHED', image=str(IMAGE), image_sha256=IMAGE_SHA,
                simv=ledger['simv'], snapshot_sha256=ledger['snapshot_sha256'], jobs=2, seed=1,
                cases=cases, pins=pins, stop_first_fail=True, retries=0, outer_timeout_s=10000,
                budget=dict(reference='readiness01.json measured alias-prefix anchors + exact Spike counts',
                            estimated_jobs2_seconds=[round(makespan([c['evidence']['estimated_vcs_seconds'][i]
                                                                    for c in cases]), 1) for i in (0, 1)],
                            timeout_schedule_s=makespan(TIMEOUTS), sum_inner_timeouts_s=sum(TIMEOUTS),
                            limitation='Cross-suite wall-time estimate, not DUT cycle measurement'),
                admission=dict(mode='parent launch only after regression38 terminal; no polling worker',
                               predecessor=str(PRIOR), predecessor_plan_sha256=sha(PRIOR / 'plan.json'),
                               cap=24, min_available_bytes=32*1024**3, current_reserved_before38=24,
                               predecessor_release=4, own_jobs=2,
                               continuing_reservations={k:dict(slots=n, root=str(p)) for k,(n,p) in RESERVATIONS.items()}),
                scope='Five contiguous original prefixes, 262 configurations; no whole22-matrix/Linux closure',
                source_provenance='Reconstructed C generates all22 exact archived Linux ELF bytes; original C text lost')
    save(out / 'plan.json', data)
    results = execute(data, out / 'dryrun', True)
    require(len(results) == 5 and [r.name for r in results] == NAMES and
            all(r.status == 'DRY_RUN' for r in results), 'Unexpected dry-run execution')
    base.verify_pins(pins)
    save(out / 'preflight.json', dict(status='PASS_PREPARE_ONLY', cases=5, jobs=2, VCS_started=False,
         plan_sha256=sha(out / 'plan.json'), dryrun_summary_sha256=sha(out / 'dryrun/summary.json'),
         host_tests_returncode=tested.returncode, host_tests_log_sha256=sha(out/'host_tests.log'),
         admission_checked=False, terminal38_checked=False, parent_approval=False))
    print('READY_NOT_LAUNCHED ' + sha(out / 'plan.json'), flush=True)


def terminal38(data):
    prior = read(PRIOR / 'plan.json')
    require(sha(PRIOR / 'plan.json') == data['admission']['predecessor_plan_sha256'], 'Predecessor plan drift')
    terminal = read(PRIOR / 'complete.json')
    run = read(PRIOR / 'replay/run.json')
    summary = read(PRIOR / 'replay/summary.json')
    require(run.get('simv') == read(IMAGE/'image.json')['simv'], 'Predecessor runner used different image')
    names = [c['id'] for c in prior['cases']]
    validate_terminal38(terminal, run, summary, names, data['admission']['predecessor_plan_sha256'])
    return {str(path): sha(path) for path in (PRIOR / 'plan.json', PRIOR / 'complete.json',
                                             PRIOR / 'replay/run.json', PRIOR / 'replay/summary.json')}


def validate_terminal38(terminal, run, summary, names, digest):
    require(len(names) == len(set(names)) == 38 and terminal.get('status') == 'PASS_38_CANDIDATE04' and
            terminal.get('plan_sha256') == digest and terminal.get('image_sha256') == IMAGE_SHA and
            terminal.get('pins_unchanged') is True and terminal.get('finished'), 'Predecessor not accepted terminal M4')
    require(run.get('status') == 'COMPLETE' and run.get('status_counts') == {'PASS':38} and
            run.get('tests') == names, 'Predecessor runner not complete38')
    for rows in (summary, terminal.get('results', [])):
        require(len(rows) == 38 and [r['name'] for r in rows] == names and
                all(r['status'] == 'PASS' and r['returncode'] == 0 for r in rows), 'Predecessor details incomplete')


def capacity(live, available, out):
    hits = {key:0 for key in RESERVATIONS}
    other = own = prior = 0
    for process in live:
        paths = ' '.join(process['argv']) + ' ' + process.get('cwd', '')
        if str(out) + '/' in paths:
            own += 1
        elif str(PRIOR) + '/' in paths:
            prior += 1
        else:
            matched = [k for k,(_,root) in RESERVATIONS.items() if str(root)+'/' in paths]
            require(len(matched) <= 1, 'Ambiguous reservation membership')
            if matched: hits[matched[0]] += 1
            else: other += 1
    reserved_live = sum(max(slots, hits[k]) for k,(slots,_) in RESERVATIONS.items())
    total = reserved_live + other + prior + max(2, own)
    return dict(passed=total<=24 and available>=32*1024**3 and own==0 and prior==0,
                total_live_reserved=total, cap=24, available_bytes=available, own_live=own,
                predecessor_live=prior, other_live=other, reserved_group_live=hits,
                continuing_reserved_slots=20, own_reserved_slots=2, live=live, time=time.time())


def inventory():
    live = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if (proc / 'comm').read_text().strip() != 'simv': continue
            args = [x.decode(errors='replace') for x in (proc / 'cmdline').read_bytes().split(b'\0') if x]
            cwd = str((proc / 'cwd').resolve(strict=True))
            live.append(dict(pid=int(proc.name), argv=args, cwd=cwd))
        except FileNotFoundError:
            continue
        # Permission/other errors must not silently undercount live simulators.
    memory = dict(line.split(':',1) for line in Path('/proc/meminfo').read_text().splitlines())
    return live, int(memory['MemAvailable'].split()[0])*1024


def accept_results(data, out, results, ledger):
    require(len(results)==5 and [r.name for r in results]==NAMES and
            all(r.status=='PASS' and r.returncode==0 for r in results), 'Not exact-five PASS')
    run = read(out / 'replay/run.json'); summary = read(out / 'replay/summary.json')
    require(run['status']=='COMPLETE' and run['tests']==NAMES and run['status_counts']=={'PASS':5},
            'Runner incomplete')
    require(len(summary)==5 and [r['name'] for r in summary]==NAMES and
            all(r['status']=='PASS' and r['returncode']==0 for r in summary), 'Summary incomplete')
    records = []
    for case, result in zip(data['cases'], results):
        directory = out / 'replay/tests' / case['id']
        inputs = read(directory / 'inputs.json')
        require(sha(directory/'input.elf')==case['sha256'] and
                inputs['binary']==dict(source=case['elf'], path=str(directory/'input.elf'), sha256=case['sha256']),
                'Actual private ELF identity')
        require(inputs['simv']==dict(path=ledger['simv'], image_sha256=ledger['files']), 'Actual image identity')
        text = (directory / 'console.log').read_text()
        require(console_ok(text, case), 'Terminal raw/oracle veto')
        records.append(dict(name=case['id'], status='PASS', returncode=0, elapsed_s=result.elapsed_s,
                            configurations=case['configurations'], console_sha256=sha(directory/'console.log'),
                            elf_sha256=case['sha256']))
    return records


def work(out, approved, authorized):
    require(authorized and approved==sha(out/'plan.json'), 'Explicit parent authorization/hash required')
    require(not (out/'attempt.json').exists() and not (out/'replay').exists(), 'Attempt/output collision; no retry')
    data = read(out / 'plan.json')
    require(data['jobs']==2 and data['image_sha256']==IMAGE_SHA and
            [c['id'] for c in data['cases']]==NAMES and
            [c['configurations'] for c in data['cases']]==COUNTS and
            [c['timeout_s'] for c in data['cases']]==TIMEOUTS, 'Plan scope changed')
    base.verify_pins(data['pins'])
    with (out/'attempt.json').open('x') as stream:
        json.dump(dict(plan_sha256=approved, time=time.time(), pid=os.getpid()),stream,indent=2)
    try:
        gate_pins = terminal38(data)
        live, memory = inventory()
        admission = capacity(live, memory, out)
        save(out/'admission.json', admission)
        require(admission['passed'], 'No capacity/release; refused once without retry')
        ledger, _, _ = identity()
    except Exception as error:
        save(out/'gate_refusal.json',dict(status='REFUSED_NOT_LAUNCHED',error=str(error), retries=0))
        return 2
    save(out/'launch.json',dict(time=time.time(),plan_sha256=approved,jobs=2,gate_pins=gate_pins))
    try:
        results = execute(data, out/'replay', False)
        base.verify_pins(data['pins']); base.verify_pins(gate_pins); identity()
        records = accept_results(data, out, results, ledger)
        save(out/'complete.json',dict(status='PASS_5_ARITHMETIC_PREFIXES_CANDIDATE04',results=records,
             plan_sha256=approved,image_sha256=IMAGE_SHA,pins_unchanged=True,finished=time.time(),scope=data['scope']))
        return 0
    except BaseException as error:
        save(out/'complete.json',dict(status='NOT_ACCEPTED',error=str(error),finished=time.time(),
                                      plan_sha256=approved,image_sha256=IMAGE_SHA))
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode',choices=['prepare','work'])
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--approved-plan-sha256')
    parser.add_argument('--authorize-run',action='store_true')
    args = parser.parse_args(); out = args.out.resolve()
    require(out.is_relative_to(HERE) and out!=HERE,'Output must be in owned arithmetic directory')
    env = base.shared.environment();os.environ.clear();os.environ.update(env)
    if args.mode=='prepare': prepare(out);return 0
    return work(out,args.approved_plan_sha256,args.authorize_run)


if __name__=='__main__':
    raise SystemExit(main())
