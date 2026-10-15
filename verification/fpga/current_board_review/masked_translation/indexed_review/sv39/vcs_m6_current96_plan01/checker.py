"""M6 provenance gates around the unchanged accepted NF7 numerical oracle."""
import json
from pathlib import Path
import re
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
REF = HERE.parent
ROOT = HERE.parents[3]
OLD = REF/'vcs_plan06'
SHAPES = [f'nf7_g{g:02d}' for g in range(24)]
READY_SHA = 'f39037e695688e0706324b3f9d27dc62e0765848348e306d19a4d8f4572f611c'
OLD_PLAN_SHA = 'edc7b0e20d0ef1cbf99b978421b8ca5df1eb9ce6505ec22e3bbc69db3e901839'
AUDIT_SHA = '183b1bd1a268741f5c49dfa97b57ae9a8e239ff02bd5e478a3773f94bcf63a80'
IMAGE_SHA = 'a681e2744dc51a9ebfbef39d6da68707e29041e7fe4ad79ed392c62466167da0'
sys.path.insert(0, str(ROOT/'gather_repair05'))
import regression as common
read, sha, require = common.read, common.sha, common.require
VETO = re.compile(common.BAD.pattern+r'|IX_SV39_FAIL|\b(?:FAIL|FAILED|ABORT|MISMATCH|TIMEOUT|CANCELLED|Traceback)\b', re.I)


def scope():
    require(sha(OLD/'programs/programs.json') == READY_SHA and sha(OLD/'plan.json') == OLD_PLAN_SHA,
            'Accepted NF7 manifest/plan drift')
    audit = REF/'terminal_audit01/results/complete.json'
    require(sha(audit) == AUDIT_SHA and read(audit)['status'] == 'NF7_M2_FULL96_INDEPENDENT_CSV_AUDIT_PASS',
            'Missing original M2 independent acceptance')
    programs = read(OLD/'programs/programs.json')['programs']
    geometry = read(REF.parent/'geometry01.json')['cases']
    require(list(programs) == SHAPES, 'Exact24 ordered runtime IDs')
    cases = []
    for g, name in enumerate(SHAPES):
        e = programs[name]; source = Path(e['path']).parent
        status = read(source/'status.json'); cfg = read(source/'cases.json')
        trials = list(range(4*g, 4*g+4))
        require(e['cases'] == status['trials'] == trials and cfg == geometry[4*g:4*g+4],
                'Original group/predecessor geometry drift')
        require(sha(Path(e['path'])) == e['sha256'] == status['elf_sha256']['soc'], 'Accepted ELF drift')
        ledger = OLD/f'ledgers/g{g:02d}.json'
        require(len(read(ledger)) == status['checks'] and e['pass_markers'] == ['IX_SV39_PASS'], 'Full oracle missing')
        cases.append(dict(id=name, original_name='rvv_fault_replay_segment_nf7_indexed_e32_mf2',
            group=g, trials=trials, elf=e['path'], sha256=e['sha256'], source=str(source),
            ledger=str(ledger), checks=status['checks'], checkpoints=len(status['checkpoints']),
            traps=len(status['traps']), timeout_s=2400, pass_markers=e['pass_markers']))
    require(sum(c['checks'] for c in cases) == 284816 and sum(c['checkpoints'] for c in cases) == 168,
            'Original full96 totals drift')
    return cases


def source_pins(cases):
    oldpins = read(OLD/'plan.json')['pins']
    pins = dict(read(REF.parent/'geometry01.json')['source_identity'])
    paths = [OLD/'plan.json', OLD/'programs/programs.json', OLD/'reference_acceptance.json',
             OLD/'complete.json', REF.parent/'geometry01.json',
             REF/'terminal_audit01/results/complete.json', REF/'terminal_audit01/results/evidence_pins.json',
             REF/'terminal_audit01/REPORT.md']
    paths += [p for p in REF.iterdir() if p.suffix in ('.py','.c','.h','.S')]
    for c in cases:
        d = Path(c['source'])
        paths += [d/n for n in ('soc.elf','soc.symbols.json','soc.dis','cases.json','status.json')]
        paths += [Path(c['ledger']), d.parent/'source_provenance.json', d.parent/'input_pins.json']
        paths += list((d.parent/'prepared').iterdir())
        for p,h in read(d.parent/'input_pins.json').items():
            require(p not in pins or pins[p] == h, 'Conflicting source pin')
            pins[p] = h
    for p in set(paths):
        h = sha(p)
        require(str(p) not in oldpins or oldpins[str(p)] == h, 'M2 accepted source/oracle drift: '+str(p))
        pins[str(p)] = h
    # Enumerate isolated observer imports without reading a reference trace.
    command = [sys.executable,'-B',str(HERE/'observer.py'),'pins']
    imported = json.loads(subprocess.check_output(command, text=True, cwd=HERE))
    pins.update(imported)
    common.base.verify_pins(pins)
    return pins


def runtime_case(c):
    require(c['id'] in SHAPES and c['original_name'] == 'rvv_fault_replay_segment_nf7_indexed_e32_mf2',
            'Runtime/historical identity mismatch')
    return dict(c, original_name=c['id'])


def observer_gate(report, c):
    require(report['status'] == 'NF7_CSV_ORACLE_PASS' and report['trials'] == c['trials'] and
            report['checks'] == c['checks'] and len(report['checkpoints']) == c['checkpoints'] and
            len(report['traps']) == c['traps'], 'Incomplete NF7 original oracle')


def log_gate(text):
    require(not VETO.search(text), 'Raw failure veto')


def artifacts(result, c, image, deadline):
    require(result.name == c['id'], 'Wrong runtime result identity')
    common.check_artifacts(result, runtime_case(c), image)
    root = result.artifact_dir
    for p in (root/'console.log', root/'work/run.vcs.log'):
        log_gate(p.read_text())
    require((root/'console.log').read_text().count('IX_SV39_PASS') == 1, 'Exact firmware marker count')
    child = read(root/'child_outcome.unvalidated.json')
    require(child['schema'] == 'UNVALIDATED_SIMULATOR_OUTCOME_V1' and
            type(child['returncode']) is int and child['returncode'] == result.returncode == 0 and
            child['elapsed_s'] == result.elapsed_s and child['timed_out'] is False and
            child['failure_seen'] is False and child['architectural_acceptance'] is False and
            child['command'] == read(root/'command.json')['command'] and
            child['command_sha256'] == sha(root/'command.json'), 'Direct child outcome mismatch')
    command = [sys.executable,'-B',str(HERE/'observer.py'),'check','--group',str(c['group']),
               '--csv',str(root/'commit_trace.csv'),'--out',str(root/'observer.json')]
    import time
    remaining = deadline-time.monotonic()
    require(remaining > 0, 'Original2700s group envelope exhausted before observer')
    common.save(root/'observer.command.json',dict(command=command,cwd=str(HERE),remaining_group_s=remaining))
    with (root/'observer.stdout').open('x') as stdout, (root/'observer.stderr').open('x') as stderr:
        p = subprocess.run(command,cwd=HERE,stdout=stdout,stderr=stderr,timeout=remaining)
    require(p.returncode == 0, 'Original NF7 observer failed')
    report = read(root/'observer.json'); observer_gate(report,c)
    return dict(status='STRICT_NF7_GROUP_PASS_M6',runtime_id=c['id'],trials=c['trials'],
                historical_source=c['original_name'],observer=report,
                child_outcome_sha256=sha(root/'child_outcome.unvalidated.json'))
