#!/usr/bin/env python3
"""Select nine direct calls per width before any scalar fixture execution."""
from pathlib import Path
import shutil
import sys

sys.dont_write_bytecode = True
from prepare_build import HERE, INTEGRATION, PINS, build, save, sha
from prepare_matrix import assembly

POINTS = [(0, 0, 1, 0), (0, 1, 1, 0), (0, 2, 1, 0),
          (0, 1, 1, 1), (0, 1, 1, 2), (0, 1, 1, 3),
          (2, 2, 1, 0), (3, 2, 1, 5), (1, 2, 0, 4)]


def main():
    for name, digest in PINS.items():
        if sha(INTEGRATION / name) != digest:
            raise ValueError('helper drift: ' + name)
    out = HERE / 'prepared_smoke'
    out.mkdir(exist_ok=False)
    for name in ('startup.S', 'runtime.c', 'replay.ld'):
        shutil.copyfile(INTEGRATION / name, out / name)
    shutil.copyfile(HERE / 'capture.S', out / 'capture.S')
    source = (HERE / 'matrix.c').read_text()
    marker = 'int MATRIX_MAIN(void) {'
    if source.count(marker) != 1:
        raise ValueError('matrix main drift')
    body = marker + '\n    unsigned errors=0;\n'
    for op, kind, side, mode in POINTS:
        body += f'    errors+=run({op},{kind},{side},{mode});\n'
    body += ('    replay_text(errors?"SMOKE_FAIL sew=":"SMOKE_PASS sew="); number(SEW);\n'
             '    replay_text(" cases=9 errors="); number(errors); replay_text("\\n");\n'
             '    return errors!=0;\n}\n')
    selected = source.split(marker)[0] + body
    cases = []
    for sew in (16, 32, 64):
        name = f'smoke_e{sew}'
        directory = out / name
        (directory / 'original').mkdir(parents=True)
        (directory / 'case.c').write_text(selected)
        (directory / 'original/scenario.S').write_text(assembly(sew))
        cases.append(dict(id=name, sew=sew, control=0, defines=[f'MATRIX_MAIN={name}_main'],
                          pass_marker=f'SMOKE_PASS sew={sew} cases=9 errors=0'))
    provenance = dict(schema_version=1, cases=cases, vlen=1024, nr_lanes=4, points=POINTS,
                      source_sha256=sha(HERE / 'matrix.c'), integration_pins=PINS,
                      generator_sha256=sha(Path(__file__)),
                      scope='independent matrix subset, selection before execution; unchanged run()/oracle')
    provenance['files'] = {str(p.relative_to(out)): sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    save(out / 'provenance.json', provenance)
    build(out, provenance, True, HERE / 'spike_smoke')
    build(out, provenance, False, HERE / 'soc_smoke')


if __name__ == '__main__':
    main()
