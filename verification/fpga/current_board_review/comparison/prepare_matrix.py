#!/usr/bin/env python3
"""Build bounded directed probes and a separately named original-fixture derivative."""
import json
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
from prepare_build import HERE, INTEGRATION, PINS, build, replace_once, save, sha


def assembly(sew):
    lines = ['.text', '.global cmp', 'cmp:',
             f'vsetvli t0,a5,e{sew},m8,tu,mu',
             f'vle{sew}.v v8,(a1)', f'vle{sew}.v v16,(a2)',
             'vlm.v v24,(a3)', 'vlm.v v0,(a6)',
             f'vsetvli t0,a4,e{sew},m8,tu,mu',
             'srli t0,a0,3', 'andi t0,t0,1', 'csrw fflags,t0',
             'csrw vstart,a7', 'andi t0,a0,4', 'andi a0,a0,3',
             'bnez t0,unmasked']
    for unmasked in (False, True):
        prefix = 'u' if unmasked else 'm'
        if unmasked:
            lines += ['unmasked:']
        for op in range(3):
            lines += [f'li t0,{op}', f'beq a0,t0,{prefix}{op}']
        lines += [f'j {prefix}3']
        for op, mnemonic in enumerate(('vmfeq', 'vmfne', 'vmflt', 'vmfle')):
            lines += [f'{prefix}{op}:', f'{mnemonic}.vv v24,v8,v16' + ('' if unmasked else ',v0.t'), 'j done']
    lines += ['done:', 'csrr a0,vstart', 'csrr t0,fflags', 'slli t0,t0,32', 'or a0,a0,t0',
              f'vsetvli t0,a5,e{sew},m8,tu,mu', 'vsm.v v24,(a3)', 'ret',
              '.global inspect', 'inspect:', f'vse{sew}.v v8,(a0)',
              f'vse{sew}.v v16,(a1)', 'vsm.v v0,(a2)', 'ret']
    return '\n'.join(lines) + '\n'


def main():
    for name, digest in PINS.items():
        if sha(INTEGRATION / name) != digest:
            raise ValueError('integration helper drift: ' + name)
    old = HERE / 'prepared'
    previous = json.loads((old / 'provenance.json').read_text())
    for name, digest in previous['files'].items():
        if sha(old / name) != digest:
            raise ValueError('baseline prepared source drift: ' + name)
    out = HERE / 'prepared_matrix'
    out.mkdir(exist_ok=False)
    for name in ('startup.S', 'runtime.c', 'replay.ld', 'capture.S'):
        shutil.copyfile(old / name, out / name)
    name = 'prefix_quiet_tail'
    original = out / name / 'original'
    shutil.copytree(old / 'prestart_snan/original', original)
    source = (old / 'prestart_snan/case.c').read_text().replace('prestart_snan', name)
    source = replace_once(source, 'a[i]=inputs[mapped(lhs_index(seed,i))];',
                          'a[i]=inputs[i==15 ? 14 : mapped(lhs_index(seed,i))];')
    source = replace_once(source, 'ai=mapped(ai);bi=mapped(bi);',
                          'ai=i==15 ? 14 : mapped(ai);bi=mapped(bi);')
    (out / name / 'case.c').write_text(source)
    audit = replace_once((old / 'audit.h').read_text(),
                         'unsigned ai = mapped(lhs_index(0, i)), bi = mapped(rhs_index(0, i, op));',
                         'unsigned ai = i==15 ? 14 : mapped(lhs_index(0, i)), bi = mapped(rhs_index(0, i, op));')
    (out / 'audit.h').write_text(audit)
    records = [dict(id=name, control=0, defines=['RESTART_COMPARISONS=1'],
                    source='prepared/prestart_snan', source_provenance_sha256=sha(old / 'provenance.json'),
                    scope='derivative: ONLY v8[15] sNaN 0x7c55 -> qNaN 0x7e55, oracle adjusted independently; v16[5] unchanged')]
    for sew in (16, 32, 64):
        name = f'matrix_e{sew}'
        original = out / name / 'original'
        original.mkdir(parents=True)
        shutil.copyfile(HERE / 'matrix.c', out / name / 'case.c')
        (original / 'scenario.S').write_text(assembly(sew))
        count = 102 if sew == 16 else 100
        records.append(dict(id=name, sew=sew, control=0, defines=[f'MATRIX_MAIN={name}_main'],
                            pass_marker=f'MATRIX_PASS sew={sew} cases={count} errors=0',
                            scope='new independent directed probes, NOT original-source tests'))
    provenance = dict(schema_version=1, cases=records, vlen=1024, nr_lanes=4,
                      generator_sha256=sha(Path(__file__)), builder_sha256=sha(HERE / 'prepare_build.py'),
                      integration_pins=PINS, original_provenance_sha256=sha(old / 'provenance.json'))
    provenance['files'] = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    save(out / 'provenance.json', provenance)
    build(out, provenance, True, HERE / 'spike_matrix')
    build(out, provenance, False, HERE / 'soc_matrix')


if __name__ == '__main__':
    main()
