"""Narrow no-whole-scope guard; preserves sealed local01 helper/config."""
import argparse
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import cvxif_padding_native776 as base

life, require = base.life, base.require


def parse_el(text, c):
    checks, scope, directives = False, False, 0
    for line in map(str.strip, text.splitlines()):
        if not line or line.startswith(('//','ANNOTATION:')): continue
        if line.startswith('CHECKSUM:'):
            require(not checks or scope and directives > 0, 'Empty/unowned native scope block')
            checks, scope, directives = True, False, 0
        elif line.startswith('INSTANCE:'):
            require(checks and not scope, 'Missing/duplicate native scope header')
            scope = True
        else:
            require(scope, 'Unowned native directive'); directives += 1
    require(checks and scope and directives > 0, 'Whole-scope empty block forbidden')
    return base.parse_el(text, c)


def clone(fn, **extra):
    return FunctionType(fn.__code__, {**vars(base), '__file__': __file__, 'parse_el': parse_el,
                                      'check': check, **extra})


def check(out, seal):
    c = clone(base.check)(out, seal)
    require(c.get('no_whole_scope_native_blocks') is True, 'No-whole-scope guard not sealed')
    for file in (Path(__file__).resolve(), Path(__file__).with_name('test_cvxif_padding_native776_v2.py').resolve()):
        require(c['pins'].get(str(file)) == life.digest(file), 'V2 parser/test pin')
    return c


def prepare(out, service_unit=None):
    def save(path, value):
        if Path(path) == out/'config.json':
            value = dict(value, no_whole_scope_native_blocks=True, pins=dict(value['pins']))
            for file in (Path(__file__).resolve(), Path(__file__).with_name('test_cvxif_padding_native776_v2.py').resolve()):
                value['pins'][str(file)] = life.digest(file)
        return life.save(path, value)
    private = SimpleNamespace(**{**vars(life), 'save': save})
    clone(base.prepare, life=private)(out,service_unit)


def verify(out, seal):clone(base.verify)(out, seal)


def run(out, seal, authorization):clone(base.run, verify=verify)(out, seal, authorization)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('mode',choices=('prepare','check','el','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--file');p.add_argument('--parent-reviewed-seal');p.add_argument('--service-unit')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':prepare(out,a.service_unit)
    elif a.mode=='check':check(out,a.seal);print('PREPARED_V2_CHECK_PASS_NO_EDA')
    elif a.mode=='el':print(len(parse_el((out/a.file).read_text(),json.loads((out/'config.json').read_bytes()))))
    elif a.mode=='verify':verify(out,a.seal)
    else:run(out,a.seal,a.parent_reviewed_seal)
