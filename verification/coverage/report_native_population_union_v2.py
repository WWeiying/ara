"""Scope-name-only successor using the actual sealed DVE hierarchy labels."""
import argparse
import inspect
from pathlib import Path
from types import FunctionType

import report_native_population_union as predecessor

life, require = predecessor.life, predecessor.require
PREDECESSOR_SHA = '953e9baf65470c73e6db78748d9979bdc9cf7f07e1706ab7beec766a77554c21'


def root_name(scope):
    q = life.read_bound(predecessor.BASE / 'qualification.json', predecessor.BASE_SHA)
    path = predecessor.BASE / 'summary.csv.partial'
    require(str(path) in q['output_pins'], 'Actual hierarchy source not sealed')
    life.check({str(path): q['output_pins'][str(path)]})
    stack, found = [], []
    for row in predecessor.frozen.prior.dict_rows(path):
        depth = int(row['Depth'])
        require(depth >= 0 and depth <= len(stack), 'Skipped actual hierarchy depth')
        stack = stack[:depth] + [row['Name']]
        if '.'.join(stack) == scope:
            found.append(row['Name'])
    require(len(found) == 1, 'Actual selectable root absent/ambiguous: ' + scope)
    return found[0]


def namespace():
    path = Path(predecessor.__file__).resolve()
    life.check({str(path): PREDECESSOR_SHA})
    ns = dict(vars(predecessor), __file__=__file__, root_name=root_name)
    body = inspect.getsource(predecessor.prepare)
    old = "root = dict(scope=i['scope'], name=i['scope'].split('.')[-1])"
    require(body.count(old) == 1, 'Exact root-label adapter anchor differs')
    body = body.replace(old, "root = dict(scope=i['scope'], name=root_name(i['scope']))")
    anchor = '    if fma_out:\n        dependencies.extend('
    require(body.count(anchor) == 1, 'Exact dependency adapter anchor differs')
    body = body.replace(anchor, "    dependencies.extend([HERE / 'report_native_population_union.py',\n"
        "                         HERE / 'test_report_native_population_union_v2.py'])\n" + anchor)
    exec(compile(body, __file__, 'exec'), ns)
    for name in ('check', 'verify', 'run'):
        fn = getattr(predecessor, name)
        ns[name] = FunctionType(fn.__code__, ns)
    return ns


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'verify', 'run'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--manifest', type=Path)
    p.add_argument('--manifest-seal')
    p.add_argument('--fma-output', type=Path)
    p.add_argument('--fma-seal')
    p.add_argument('--runtime-ready', action='store_true')
    a = p.parse_args(); out = a.output.resolve(); ns = namespace()
    if a.mode == 'prepare':
        require(a.manifest and a.manifest_seal, 'Formal manifest/seal required')
        ns['prepare'](out, a.manifest.resolve(), a.manifest_seal,
                      a.fma_output.resolve() if a.fma_output else None, a.fma_seal, a.runtime_ready)
    else:
        require(a.seal, 'Exact config seal required')
        ns[a.mode](out, a.seal)
        if a.mode == 'check':
            print('SEALED_POPULATION_V2_UNION_CHECK_PASS_NO_DVE')
