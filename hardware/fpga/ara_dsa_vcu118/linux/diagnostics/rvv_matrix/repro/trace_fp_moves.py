"""Trace the first original masked FP slide-up sequence without changing inputs."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import re
import sys
from trace_masks import sha, TOOLS
from reduce_fp_moves import single_trial
sys.path.insert(0, str(TOOLS))
from guest_watch import no_retirement
from fault_replay import LMULS
from audit_permute_stall import inspect


def shape_capacity(shape):
    match = re.fullmatch(r'e(16|32|64)_(mf[248]|m[1248])', shape)
    if match is None:
        raise ValueError('Unsupported FP shape')
    sew = int(match[1]); num, den, _ = LMULS[match[2]]
    if sew * den > 64 * num:
        raise ValueError('Reserved FP shape')
    return 1024 * num // (sew * den)


def measured_trial(report, trace_manifest, shape='e16_mf2'):
    capacity = shape_capacity(shape)
    name = 'rvv_trace_fp_move_restart_' + shape
    case, = [c for c in trace_manifest['cases'] if c['name'] == name]
    deployed, = [c for c in report['inputs']['cases'] if c['name'] == name]
    result, = [r for r in report['results'] if r['name'] == name]
    if deployed['sha256'] != case['sha256'] or result['status'] != 'stalled':
        raise ValueError('Trace ELF or terminal stall not verified')
    diagnosis = report['progress_diagnosis']
    if diagnosis['name'] != name or not diagnosis['stalled'] or not no_retirement(diagnosis['snapshots']):
        raise ValueError('Missing live no-retirement evidence')
    a, b = diagnosis['snapshots']
    if a['live']['run_id'] != b['live']['run_id']:
        raise ValueError('Snapshot run changed')
    line = result['output'].strip().splitlines()[-1]
    if not line.startswith('RVV_MOVE_BEGIN '):
        raise ValueError('Final record is not an unreturned call')
    tokens = line.split()[1:]
    if any(re.fullmatch(r'\w+=\d+', t) is None for t in tokens):
        raise ValueError('Malformed trial fields')
    fields = {k: int(v) for k, v in (t.split('=') for t in tokens)}
    required = {'seed', 'scalar', 'invalid_box', 'op', 'vl', 'mask', 'sticky', 'vstart', 'cap', 'completed'}
    if len(fields) != len(tokens) or fields.keys() != required:
        raise ValueError('Missing or duplicate trial fields')
    if any(fields[k] != v for k, v in dict(seed=0, scalar=0, invalid_box=0, op=2, cap=capacity).items()):
        raise ValueError('Outside the instrumented original tuple family')
    return fields


def instrument(source):
    point = '        unsigned long status=functions[op](a,&scalar_bits,output+1,vl,cap,mask,control,&scalar_result);'
    if source.count(point) != 1:
        raise ValueError('Original FP move call changed')
    # The saved original failure output reaches this tuple family, not its exact trial.
    condition = 'seed==0 && scalar==0 && invalid==0 && op==2'
    before = '''        if(CONDITION) {
            text("RVV_MOVE_BEGIN seed=");num(seed);text(" scalar=");num(scalar);
            text(" invalid_box=");num(invalid);text(" op=");num(op);
            text(" vl=");num(vl);text(" mask=");num(mode);
            text(" sticky=");num(sticky);text(" vstart=");num(start);
            text(" cap=");num(cap);text(" completed=");num(cases);text("\\n");
            if(syscall3(29,1,0x5409,1)) {
                text("RVV_MOVE_DRAIN_FAILED\\n");syscall3(94,2,0,0);for(;;){}
            }
        }
'''.replace('CONDITION', condition)
    after = '''
        if(CONDITION) {
            text("RVV_MOVE_RETURN completed=");num(cases);
            text(" status=");num(status);text("\\n");
        }'''.replace('CONDITION', condition)
    return source.replace(point, before + point + after)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('original', 'report', 'out'):
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--cross', required=True)
    p.add_argument('--shape', default='e16_mf2', help='Legal FP SEW/LMUL, for example e32_m2; board VLEN1024')
    p.add_argument('--trace-root', type=Path)
    p.add_argument('--trace-report', type=Path)
    a = p.parse_args()
    shape_capacity(a.shape)
    manifest = json.loads((a.original / 'manifest.json').read_text())
    raw = json.loads(a.report.read_text())
    report = raw.get('report', raw)
    sew = int(a.shape.split('_')[0][1:])
    original_name = 'rvv_fp_move_restart_' + a.shape
    parent, = [c for c in manifest['cases'] if c['name'] == original_name]
    deployed, = [c for c in report['inputs']['cases'] if c['name'] == original_name]
    result, = [r for r in report['results'] if r['name'] == original_name]
    if parent['sha256'] != deployed['sha256'] or result['status'] != 'stalled':
        raise ValueError('Missing original stalled ELF identity')
    selected = None
    if a.trace_root is not None or a.trace_report is not None:
        if a.trace_root is None or a.trace_report is None:
            raise ValueError('Both trace root and report are required')
        tm = json.loads((a.trace_root / 'manifest.json').read_text())
        if tm['original_report_sha256'] != sha(a.report):
            raise ValueError('Trace original report changed')
        tc, = tm['cases']
        if tc['original_elf_sha256'] != parent['sha256']:
            raise ValueError('Trace has a different original')
        if sha(a.trace_root / 'overlay/opt/ara-tests' / tc['name']) != tc['sha256']:
            raise ValueError('Local trace ELF changed')
        for file, digest in tc['scenario_sources'].items():
            if sha(a.trace_root / tc['name'] / file) != digest:
                raise ValueError('Trace source changed')
        tr = json.loads(a.trace_report.read_text()); tr = tr.get('report', tr)
        selected = measured_trial(tr, tm, a.shape)
    a.out.mkdir(exist_ok=False)
    name = 'rvv_trace_fp_move_' + ('single_' if selected else '') + 'restart_' + a.shape
    d = a.out / name
    d.mkdir()
    for f in ('inputs.h', 'operations.h'):
        shutil.copy2(a.original / ('e' + str(sew)) / f, d / f)
    shutil.copy2(a.original / (original_name + '.S'), d / 'operations.S')
    source = TOOLS / 'fp_move_oracle.c'
    flags = [a.cross + 'gcc', '-Os', '-march=rv64gcv', '-mabi=lp64d',
             '-nostdlib', '-static', '-ffreestanding', '-fno-builtin',
             '-fno-stack-protector', '-fno-tree-vectorize', '-fno-tree-slp-vectorize',
             '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wl,-s',
             '-Wall', '-Wextra', '-Werror', '-DSEW=' + str(sew), '-DRESTART_MOVES=1',
             '-DDETAIL_MOVES=0', '-I' + str(d)]
    rebuilt = d / 'original_rebuilt.elf'
    subprocess.run(flags + [str(source), str(d / 'operations.S'), '-o', str(rebuilt)], check=True)
    if sha(rebuilt) != parent['sha256']:
        raise ValueError('Original ELF could not be rebuilt byte-identically')
    inspect(a.report, rebuilt, original_name, a.cross, False, '38805c57')
    code = single_trial(source.read_text(), selected) if selected else source.read_text()
    (d / 'scenario.c').write_text(instrument(code))
    binaries = a.out / 'overlay/opt/ara-tests'
    binaries.mkdir(parents=True)
    binary = binaries / name
    subprocess.run(flags + [str(d / 'scenario.c'), str(d / 'operations.S'), '-o', str(binary)], check=True)
    with (d / 'scenario.dis').open('w') as stream:
        subprocess.run([a.cross + 'objdump', '-d', str(binary)], stdout=stream, check=True)
    m = dict(scope='Full original sequence, first seed/scalar/valid-box op2 call tracing only; timing changes',
             board_reproduction_confirmed=False, original_manifest_sha256=sha(a.original / 'manifest.json'),
             original_report_sha256=sha(a.report), reducer_sha256=sha(Path(__file__)),
             cases=[dict(parent, name=name, sha256=sha(binary), original_name=original_name,
                         original_elf_sha256=parent['sha256'], original_rebuild_byte_identical=True,
                         scenario_role='original_sequence_trace',
                         scenario_sources={f: sha(d / f) for f in ('scenario.c', 'operations.S', 'operations.h', 'inputs.h')})])
    if selected:
        m.update(scope='One measured stalled FP move trial; board reproduction not yet confirmed',
                 trace_report_sha256=sha(a.trace_report), trace_manifest_sha256=sha(a.trace_root / 'manifest.json'))
        m['cases'][0].update(configurations=1, scenario_role='single_original_trial', selected_trial=selected)
    (a.out / 'manifest.json').write_text(json.dumps(m, indent=2) + '\n')
    with (a.out / 'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio', '-o', '-H', 'newc', '--owner=0:0'], cwd=a.out / 'overlay',
                       input=('opt\nopt/ara-tests\nopt/ara-tests/' + name + '\n').encode(), stdout=stream, check=True)
    print('ORIGINAL_REBUILD_IDENTICAL; TRACE_READY')


if __name__ == '__main__':
    main()
