"""Isolate measured current-oracle replay trials; old-source equivalence is unproven."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from trace_masks import sha
from trace_fault import instrument, unit_shape, segment_shape, strided_shape
from audit_fault_controls import audit
from audit_slide import require


def isolate(source, trigger, fields=1, strided=False, zero=False):
    keys = ('unmapped', 'store', 'boundary', 'mode', 'split')
    require(not zero or strided, 'Zero stride requires strided layout')
    if strided and not zero:
        keys += ('gap',)
    require(set(trigger) == set(keys), 'Incomplete replay trigger')
    require(all(type(trigger[k]) is int for k in keys), 'Noninteger replay trigger')
    require(type(fields) is int and fields in range(1, 9), 'Invalid field count')
    require(trigger['unmapped'] in (0, 1) and trigger['store'] in (0, 1) and
            trigger['boundary'] in ((0,) if zero else (1, 3, 5)) and trigger['mode'] in range(4) and
            trigger['split'] in range(2 if fields > 1 else 1), 'Outside measured unit-stride replay domain')
    if strided and not zero:
        require(trigger['gap'] in (1, 3), 'Outside measured stride gaps')
    point = '        long address=call(222,0,8192,3,0x22,-1,0);'
    require(source.count(point) == 1, 'Replay loop structure changed')
    condition = ' && '.join(f'{"store_case" if k == "store" else k}=={trigger[k]}' for k in keys)
    return source.replace(point, '        if(!(' + condition + '))continue;\n' + point)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('controls', 'original-report', 'trace-report', 'out'):
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--cross', required=True)
    a = p.parse_args()
    checked = audit(a.controls, a.original_report, a.trace_report)
    rows = checked['cases']
    require(len(rows) == 3 and all(r['aggregate_original_symptom_matches'] for r in rows),
            'Three-way measured aggregate agreement missing')
    trace, = [r for r in rows if r['role'] == 'original_sequence_trace']
    selected = [t for t in trace['diagnostic']['trials'] if t['completed'] and t['errors'] > 0]
    require(selected and trace['diagnostic']['incomplete'] == 0, 'Incomplete trace')
    cm = json.loads((a.controls / 'manifest.json').read_text())
    parent, = [c for c in cm['cases'] if c['scenario_role'] == 'original_sequence_trace']
    baseline, = [c for c in cm['cases'] if c['scenario_role'] == 'current_oracle_control']
    layout = cm.get('diagnostic_layout')
    fields = 1
    strided = bool(layout and layout.get('strided'))
    zero = bool(layout and layout.get('zero_stride'))
    original_case = dict(parent, name=parent['original_name'])
    if layout:
        shape, fields = (strided_shape if strided else segment_shape)(layout, original_case)
    else:
        shape = unit_shape({}, original_case)
    sew, lmul, num, den, code = shape
    d0 = a.controls / parent['name']
    source = (d0 / 'baseline.c').read_text()
    a.out.mkdir(exist_ok=False)
    binaries = a.out / 'overlay/opt/ara-tests'; binaries.mkdir(parents=True)
    flags = [a.cross + 'gcc', '-Os', '-march=rv64gcv', '-mabi=lp64d', '-nostdlib', '-static',
             '-ffreestanding', '-fno-builtin', '-fno-stack-protector', '-fno-tree-vectorize',
             '-fno-tree-slp-vectorize', '-msmall-data-limit=0', '-Wl,--build-id=none', '-Wl,-s',
             '-Wall', '-Wextra', '-Werror', f'-DSEW={sew}', '-DTRACE_REPLAY=0', '-DNEGATIVE_RESTART=0',
             '-DINDEXED_REPLAY=0', f'-DINDEX_SEW={sew}', f'-DLMUL_NUM={num}', f'-DLMUL_DEN={den}',
             f'-DLMUL_CODE={code}', f'-DREPLAY_FIELDS={fields}']
    if strided:
        flags += ['-DSTRIDED_REPLAY=1', f'-DZERO_STRIDE={int(zero)}',
                  f'-DNEGATIVE_STRIDE={int(layout.get("negative_stride", False))}']
    rebuilt = a.out / 'baseline_rebuilt.elf'
    subprocess.run(flags + [str(d0 / 'baseline.c'), str(d0 / 'scenario.S'), '-o', str(rebuilt)], check=True)
    require(sha(rebuilt) == baseline['sha256'], 'Current baseline rebuild changed')
    manifest = dict(scope='Single measured current-oracle fault trials; original per-trial equivalence unproven',
                    original_failure_equivalence_proven=False, original_source_equivalence_confirmed=False,
                    board_reproduction_confirmed=False, controls_manifest_sha256=sha(a.controls / 'manifest.json'),
                    trace_report_sha256=sha(a.trace_report), reducer_sha256=sha(Path(__file__)), cases=[])
    if layout:
        manifest['diagnostic_layout'] = layout
    manifest['original_source_equivalence_confirmed'] = cm.get('original_source_equivalence_confirmed', False)
    shutil.copy2(a.trace_report, a.out / 'measured_report.json')
    shutil.copy2(d0 / 'baseline.c', a.out / 'baseline.c')
    for trial in selected:
        t = trial['trigger']
        name = f'rvv_small_fault_e{sew}_{lmul}_u{{}}_s{{}}_b{{}}_m{{}}'.format(t['unmapped'], t['store'], t['boundary'], t['mode'])
        if fields > 1:
            name = name.replace('rvv_small_fault_', f'rvv_small_fault_segment_nf{fields}_') + f'_f{t["split"]}'
        if strided:
            suffix = parent['original_name'].removeprefix('rvv_fault_replay_')
            name = 'rvv_small_fault_' + suffix + '_u{}_s{}_b{}_m{}_f{}'.format(
                t['unmapped'], t['store'], t['boundary'], t['mode'], t['split'])
            if not zero:
                name += f'_g{t["gap"]}'
        d = a.out / name; d.mkdir()
        (d / 'scenario.c').write_text(instrument(isolate(source, t, fields, strided, zero), strided))
        shutil.copy2(d0 / 'scenario.S', d / 'scenario.S')
        binary = binaries / name
        subprocess.run(flags + [str(d / 'scenario.c'), str(d / 'scenario.S'), '-o', str(binary)], check=True)
        with (d / 'scenario.dis').open('w') as stream:
            subprocess.run([a.cross + 'objdump', '-d', str(binary)], stdout=stream, check=True)
        manifest['cases'].append(dict(parent, name=name, sha256=sha(binary), configurations=1,
            scenario_role='single_current_oracle_trial', selected_trial=t, measured_trial=trial,
            current_baseline_sha256=baseline['sha256'], original_rebuild_byte_identical=False,
            scenario_sources={f: sha(d / f) for f in ('scenario.c', 'scenario.S')}))
    (a.out / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    with (a.out / 'overlay.cpio').open('wb') as stream:
        subprocess.run(['cpio', '-o', '-H', 'newc', '--owner=0:0'], cwd=a.out / 'overlay',
                       input=('opt\nopt/ara-tests\n' + ''.join('opt/ara-tests/' + c['name'] + '\n'
                              for c in manifest['cases'])).encode(), stdout=stream, check=True)
    print('MEASURED_CURRENT_ORACLE_TRIALS', len(selected))


if __name__ == '__main__':
    main()
