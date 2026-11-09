#!/usr/bin/env python3
"""Freeze and run the bounded four-production-VMFPU numerical integration gate."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[3]
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
ACCEPTED = OUT / 'resident_pv_vmfpu_20261108_04'
CLUSTER = OUT / 'resident_pv_cluster_agent_20261108_02'
CORPUS = OUT / 'resident_pv_cluster_corpus_20261108_01'
FROZEN_SOURCE = OUT / 'chain_soc_20261107_01/source'
ERROR = re.compile(r'(?mi)^(Error-|Error:|Fatal:|FATAL|Assertion failed|\s*\$fatal)')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    for name, digest in pins.items():
        if sha(name) != digest:
            raise ValueError('Pinned input/image drift: ' + name)


def copy_pin(source, destination, pins, expected=None):
    digest = sha(source)
    if expected is not None and digest != expected:
        raise ValueError('Accepted input drift: ' + str(source))
    if str(source) in pins and pins[str(source)] != digest:
        raise ValueError('Conflicting pin: ' + str(source))
    pins[str(source)] = digest
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    if sha(destination) != digest:
        raise ValueError('Snapshot race: ' + str(source))
    destination.chmod(0o444)
    pins[str(destination)] = digest


def frozen_filelist(text, accepted):
    """Keep the accepted filelist verbatim; admit only previously frozen inputs."""
    selected, directories = {}, {}
    for line in text.splitlines():
        if line.startswith('+define+'):
            continue
        if line.startswith('+incdir+'):
            directory = Path(line[len('+incdir+'):])
            if not directory.is_relative_to(FROZEN_SOURCE):
                raise ValueError('Non-frozen include directory: ' + str(directory))
            files = sorted(str(p) for p in directory.rglob('*') if p.is_file())
            if not files:
                raise ValueError('Empty include directory: ' + str(directory))
            directories[str(directory)] = files
        elif line.startswith('/'):
            path = Path(line)
            if not (path.is_relative_to(FROZEN_SOURCE) or path == ACCEPTED/'inputs/vmfpu.sv'):
                raise ValueError('Non-frozen compiler source: ' + line)
            files = [line]
        else:
            raise ValueError('Unsupported frozen filelist entry: ' + line)
        for name in files:
            if name not in accepted:
                raise ValueError('Unpinned compiler source/header: ' + name)
            selected[name] = accepted[name]
    verify(selected)
    return selected, directories


def verify_directories(directories):
    for name, expected in directories.items():
        actual = sorted(str(p) for p in Path(name).rglob('*') if p.is_file())
        if actual != expected:
            raise ValueError('Frozen include inventory changed: ' + name)


def load_module(path):
    spec = importlib.util.spec_from_file_location('cluster_corpus_frozen', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def validate_corpus(inputs):
    """Independently bind every regrouped body to the accepted SoftFloat corpus."""
    manifest = json.loads((inputs/'corpus.json').read_text())
    generator = load_module(inputs/'corpus.py')
    metadata = json.loads((generator.BASE/'vectors/vectors.json').read_text())
    original = generator.BASE/'vectors/vectors.txt'
    if sha(original) != generator.VECTOR_SHA:
        raise ValueError('Original independent-SoftFloat corpus drift')
    records = generator.records(original.read_text(), metadata['cases_by_id'])
    groups = generator.selections()
    if manifest['cases'] != len(groups) or len(manifest['groups']) != len(groups):
        raise ValueError('Corpus group count mismatch')
    wanted_text = [f'50565531 {len(groups)}\n' for _ in range(4)]
    lanes, group_rows = [], []
    for idx, names in enumerate(groups):
        group_flags = 0
        first = records[names[0]]['header']
        for lane, name in enumerate(names):
            row = records[name]
            header = row['header'][:]
            header[0] = str(idx)
            if header[1:5] != first[1:5] or int(header[5]) != 0:
                raise ValueError('Unequal shape/non-normal group')
            wanted_text[lane] += ' '.join(header)+'\n'+'\n'.join(row['body'])+'\n'
            seeds, packets, ops, commits = map(int, header[8:12])
            flags = int(header[12], 16)
            group_flags |= flags
            lanes.append(dict(id=idx, lane=lane, seeds=seeds, packets=packets,
                              issued=ops, returned=ops, writes=commits, acks=commits, flags=flags))
        group = dict(id=idx, source_names=names, elements=int(first[1]), heads=int(first[2]),
                     tokens=int(first[3]), rm=int(first[4]), flags=group_flags)
        if manifest['groups'][idx] != group:
            raise ValueError('Corpus metadata mismatch')
        group_rows.append(dict(id=idx, flags=group_flags))
    for lane in range(4):
        if (inputs/f'lane{lane}.txt').read_text() != wanted_text[lane]:
            raise ValueError('Regrouped body changed: lane ' + str(lane))
    return dict(cases=len(groups), lanes=lanes, groups=group_rows,
                real_groups=manifest['real_groups'], real_lane_cases=manifest['real_lane_cases'])


def parse_rows(text, prefix, keys):
    rows = []
    for raw in re.findall(r'^'+re.escape(prefix)+r' (.*)$', text, re.M):
        pairs = re.findall(r'(\w+)=(\d+)', raw)
        if (len(pairs) != len(keys) or set(k for k, _ in pairs) != set(keys) or
                ' '.join(k+'='+v for k, v in pairs) != raw):
            raise ValueError('Malformed/duplicate fields: ' + prefix)
        rows.append({key: int(value) for key, value in pairs})
    return rows


def check_log(text, expected, shared):
    if ERROR.search(text):
        raise ValueError('Simulator error/fatal')
    lanes = parse_rows(text, 'PV_CLUSTER_FP_LANE',
                      ('id', 'lane', 'seeds', 'packets', 'issued', 'returned', 'writes', 'acks', 'flags'))
    groups = parse_rows(text, 'PV_CLUSTER_FP_CASE', ('id', 'flags'))
    if lanes != expected['lanes'] or groups != expected['groups']:
        raise ValueError('Missing/duplicate/out-of-order or incorrect numerical records')
    totals = parse_rows(text, 'PV_CLUSTER_FP_PASS',
                       ('cases', 'issued', 'writes', 'late', 'same', 'excess', 'max16',
                        'skew', 'done_stall', 'debt_terminal'))
    if len(totals) != 1:
        raise ValueError('Missing/duplicate terminal PASS')
    total = totals[0]
    if (total['cases'] != expected['cases'] or total['issued'] != sum(r['issued'] for r in lanes) or
            total['writes'] != sum(r['writes'] for r in lanes) or min(total.values()) <= 0):
        raise ValueError('Incorrect total accounting/coverage')
    stalls = parse_rows(text, 'PV_CLUSTER_FP_STALL', ('lane', 'request', 'write'))
    if len(stalls) != 4 or [r['lane'] for r in stalls] != list(range(4)) or any(
            min(r['request'], r['write']) <= 0 for r in stalls):
        raise ValueError('Missing per-lane asymmetric stalls')
    configs = parse_rows(text, 'VMFPU_ADAPTER_CONFIG', ('shared_fma', 'checker_pipe_label'))
    if configs != [dict(shared_fma=shared, checker_pipe_label=3)]*4:
        raise ValueError('Incorrect production adapter configuration count')
    owner_keys = ('native_done', 'acquires', 'releases', 'native_stalls', 'private_stalls',
                  'native_accepted', 'native_cancelled', 'private_issued', 'private_returned',
                  'private_cancelled', 'acquire_collisions', 'miter_cycles', 'native_grant_stalls',
                  'native_flag_events', 'reset_owned', 'native_fma', 'native_mul', 'native_div', 'native_max')
    owners = parse_rows(text, 'VMFPU_OWNER_COVERAGE', owner_keys)
    if len(owners) != 4:
        raise ValueError('Missing/duplicate native adapter summaries')
    per_lane = [sum(r['issued'] for r in lanes if r['lane']==l) for l in range(4)]
    if len(set(per_lane)) != 1:
        raise ValueError('Unequal lane arithmetic counts')
    n = expected['cases']
    exact = dict(acquires=n, releases=n, native_accepted=5*n, native_done=5*n,
                 private_issued=per_lane[0], private_returned=per_lane[0],
                 native_cancelled=0, private_cancelled=0, reset_owned=0,
                 native_fma=n, native_mul=n, native_div=n, native_max=n,
                 native_flag_events=n, native_grant_stalls=15*n)
    for row in owners:
        if any(row[key] != value for key, value in exact.items()) or any(
                row[key] <= 0 for key in ('native_stalls', 'private_stalls', 'acquire_collisions', 'miter_cycles')):
            raise ValueError('Normal-only native ownership accounting mismatch')
    return dict(totals=total, lanes=lanes, groups=groups, stalls=stalls, owners=owners)


def prepare(out, corpus, shared):
    out.mkdir(exist_ok=False)
    inputs = out/'inputs'
    inputs.mkdir()
    pins = {}
    for base, prefix in ((ACCEPTED, 'vmfpu'), (CLUSTER, 'cluster')):
        receipt = json.loads((base/'report.json').read_text())
        if receipt['state'] != 'PASS':
            raise ValueError('Unaccepted input collection: ' + str(base))
        for name in ('report.json', 'source-pins.json'):
            expected = None if name == 'report.json' else receipt.get('artifacts', {}).get(str(base/name))
            copy_pin(base/name, inputs/(prefix+'-'+name), pins, expected)
    accepted = json.loads((inputs/'vmfpu-source-pins.json').read_text())
    receipt = json.loads((inputs/'vmfpu-report.json').read_text())
    filelist = ACCEPTED/'inputs/sources.f'
    copy_pin(filelist, inputs/'sources.f', pins, accepted[str(filelist)])
    selected, directories = frozen_filelist((inputs/'sources.f').read_text(), accepted)
    pins.update(selected)
    for name in ('adapter.sv', 'vmfpu_baseline.sv', 'akv_resident_pv_lane.sv'):
        source = ACCEPTED/'inputs'/name
        if receipt['artifacts'].get(str(source)) != accepted[str(source)]:
            raise ValueError('Accepted compiler input receipt conflict')
        copy_pin(source, inputs/name, pins, accepted[str(source)])
    for source, frozen in ((HERE.parent/'pv_vmfpu/adapter.sv', inputs/'adapter.sv'),
                           (ROOT/'hardware/src/lane/vmfpu.sv', ACCEPTED/'inputs/vmfpu.sv'),
                           (HERE.parent/'pv_unit/akv_resident_pv_lane.sv', inputs/'akv_resident_pv_lane.sv')):
        if sha(source) != sha(frozen):
            raise ValueError('Current/accepted RTL or adapter differs: ' + str(source))
        pins[str(source)] = sha(frozen)
    cluster_pins = json.loads((inputs/'cluster-source-pins.json').read_text())
    for relative in ('pv_group/akv_resident_pv_group.sv', 'pv_transport/resident_payload_fanout.sv',
                     'pv_cluster/akv_resident_pv_cluster.sv'):
        source = HERE.parent/relative
        copy_pin(source, inputs/source.name, pins, cluster_pins[str(source)])
    # Explicit owned list: never absorb the parent's in-progress design proposal.
    for name in ('run.py', 'test_run.py', 'tb.sv', 'README.md', 'corpus.py', 'test_corpus.py'):
        copy_pin(HERE/name, inputs/name, pins)
    copy_pin(corpus/'corpus.json', inputs/'corpus.json', pins)
    corpus_meta = json.loads((inputs/'corpus.json').read_text())
    verify(corpus_meta['pins'])
    for name, digest in corpus_meta['pins'].items():
        if name in pins and pins[name] != digest:
            raise ValueError('Corpus identity conflict: ' + name)
        pins[name] = digest
    for lane in range(4):
        path = corpus/f'lane{lane}.txt'
        copy_pin(path, inputs/path.name, pins, corpus_meta['pins'][str(path)])
    expected = validate_corpus(inputs)
    save(out/'expected.json', expected)
    pins[str(out/'expected.json')] = sha(out/'expected.json')
    vcs = shutil.which('vcs')
    if not vcs:
        raise ValueError('Host VCS missing')
    pins[str(Path(vcs).resolve())] = sha(vcs)
    branch = subprocess.check_output(['git', '-C', str(OUT.parents[1]), 'branch', '--show-current'], text=True).strip()
    if branch != 'ara_dsa_signoff_integration':
        raise ValueError('Wrong verification branch')
    save(out/'selection.json', dict(shared_fma=shared, vcs=vcs, include_directories=directories,
         compile_seconds=600, simulation_seconds=180, signoff_branch=branch,
         accepted_vmfpu=str(ACCEPTED), accepted_cluster=str(CLUSTER), corpus=str(corpus),
         dependency_policy='Verbatim accepted04 frozen filelist; strict source/header hashes',
         inherited_live_provenance_not_executed=True))
    pins[str(out/'selection.json')] = sha(out/'selection.json')
    verify(pins)
    save(out/'source-pins.json', pins)
    save(out/'source-pins-before.json', pins)
    save(out/'prepared.json', dict(state='PREPARED_NOT_EXECUTED', cases=expected['cases'],
                                  issued=sum(row['issued'] for row in expected['lanes'])))


def command(argv, work, log, seconds):
    with log.open('x') as stream:
        result = subprocess.run(['timeout', '--signal=TERM', '--kill-after=10s', str(seconds), *argv],
                                cwd=work, env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1'),
                                stdout=stream, stderr=subprocess.STDOUT)
    text = log.read_text(errors='replace')
    if result.returncode or ERROR.search(text):
        raise ValueError(f'Command failed rc={result.returncode}: {log}')
    return text


def execute(out):
    pins = json.loads((out/'source-pins.json').read_text())
    config = json.loads((out/'selection.json').read_text())
    inputs, work = out/'inputs', out/'shared0'
    shared = config['shared_fma']
    work = out/f'shared{shared}'
    report = dict(state='FAIL', scope='Four-lane numerical integration only; not SoC/FPGA/performance',
                  synthesis=False, production_final_ack=False, shared_fma=shared)
    try:
        verify(pins); verify_directories(config['include_directories'])
        expected = validate_corpus(inputs)
        if expected != json.loads((out/'expected.json').read_text()):
            raise ValueError('Prepared expectations changed')
        work.mkdir()
        argv = [config['vcs'], '-full64', '-sverilog', '-timescale=1ns/1ps', '-top',
                'resident_pv_cluster_fp_tb', '-j8', '-o', 'simv', '+define+SIMULATION',
                '+define+ARA_SHARED_SIMD_MUL', f'+define+RESIDENT_TEST_SHARED_FMA={shared}',
                '-f', str(inputs/'sources.f'), *[str(inputs/name) for name in (
                    'vmfpu_baseline.sv', 'akv_resident_pv_lane.sv', 'adapter.sv',
                    'akv_resident_pv_group.sv', 'resident_payload_fanout.sv',
                    'akv_resident_pv_cluster.sv', 'tb.sv')]]
        run = [str(work/'simv'), '-no_save', '+CORPUS='+str(inputs)]
        save(work/'commands.json', dict(compile=argv, run=run))
        print('PV_CLUSTER_FP_COMPILING '+str(out), flush=True)
        command(argv, work, work/'compile.log', config['compile_seconds'])
        verify(pins); verify_directories(config['include_directories'])
        image = {str(p): sha(p) for p in (work/'simv.daidir').rglob('*') if p.is_file()}
        image[str(work/'simv')] = sha(work/'simv')
        save(work/'image-pins.json', image)
        print('PV_CLUSTER_FP_RUNNING '+str(out), flush=True)
        text = command(run, work, work/'run.log', config['simulation_seconds'])
        checked = check_log(text, expected, shared)
        verify(pins); verify(image); verify_directories(config['include_directories'])
        save(out/'source-pins-after.json', pins)
        save(work/'image-pins-after.json', image)
        report.update(state='PASS', **checked, real_groups=expected['real_groups'],
                      real_lane_cases=expected['real_lane_cases'])
    except Exception as exc:
        report['error'] = str(exc)
        report['drift'] = [name for name, digest in pins.items()
                           if not Path(name).is_file() or sha(name) != digest]
    # The service stdout is still open when this receipt is emitted. Only hash
    # closed simulator logs and completed metadata, never the live worker log.
    report['artifacts'] = {str(p): sha(p) for folder in (out, work) if folder.is_dir()
                           for p in folder.iterdir() if p.is_file() and
                           (p.suffix == '.json' or (folder == work and p.suffix == '.log'))}
    save(out/'report.json', report)
    print('PV_CLUSTER_FP_'+report['state']+' '+str(out/'report.json'), flush=True)
    if 'error' in report:
        print(report['error'], flush=True)
    return int(report['state'] != 'PASS')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    parser.add_argument('--corpus', type=Path, default=CORPUS)
    parser.add_argument('--shared', type=int, choices=(0, 1), default=0)
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--execute-prepared', action='store_true')
    args = parser.parse_args()
    out = args.output.resolve()
    if out.parent != OUT or (args.prepare_only and args.execute_prepared):
        parser.error('Use a direct signoff output child and one execution mode')
    if args.execute_prepared:
        if Path(__file__).resolve() != out/'inputs/run.py':
            parser.error('Prepared execution must use its frozen runner')
        return execute(out)
    prepare(out, args.corpus.resolve(), args.shared)
    if args.prepare_only:
        print('PV_CLUSTER_FP_PREPARED '+str(out), flush=True)
        return 0
    # The executing worker is the frozen, pinned implementation, not the live script.
    os.execv(sys.executable, [sys.executable, '-B', str(out/'inputs/run.py'), str(out), '--execute-prepared'])


if __name__ == '__main__':
    raise SystemExit(main())
