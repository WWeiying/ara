#!/usr/bin/env python3
"""Exact source-derived capability query census; all work/numerical checks retained."""
import argparse
import ast
from collections import Counter
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
BASE_SHA = '13f0f2299550d7e91f19f17811dd2d77f952495cf8ad11d9075fe7d34466dfcd'
if hashlib.sha256((HERE / 'check_v3.py').read_bytes()).hexdigest() != BASE_SHA:
    raise ValueError('Sealed V3 checker drift')
spec = importlib.util.spec_from_file_location('info_census_sealed_check_v3', HERE / 'check_v3.py')
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
c, q, SOURCE, QBS_CHECK_SHA = base.c, base.q, base.SOURCE, base.QBS_CHECK_SHA
FIXTURES = {'perf': 'acc6fe98601eefb5a58301ab33918c9640de144c72e6468244c462e049b2543d',
            'functional': 'b8f5e7e319c1e43b757c07b1dd18db7a814224a053825ea4945e59f8d3b14bd7'}
QUERY_SOURCES = {
    'main.c': '70986ea55fae91fd55b455d30f64c8c6c9136e1e1e5ada683295e4af235cdeaf',
    'sdk/software/akv/src/akv_v2_native_riscv.c': '69832cfc9bfcc20aa17b6c57085041fc03ceae77020dd4bc81901590c10d1dfd',
    'sdk/software/akv/src/akv_runtime.c': '5d7512c654ab76c8e0dfb7cc3ee571c3ea0fc74d0e3308af00888577c9f734ba',
    'sdk/software/akv/experimental/paired_heads/native_selection.h':
        'd92291bda4ec4ccb94980c0d30d8da321216f0c3cf89c92822729b65d5c77693'}


def candidate_reaches_query(rows, dimension):
    # Frozen main supplies only PAIR_HEADS=1, and the CPU supplies vlenb=128.
    return 2 <= rows <= 8 and dimension in (64, 96, 128) and not (rows == 6 and dimension == 128)


def info_per_index(fixture, trial):
    shape = fixture['oracle']['cases'][fixture['trials'][trial]['case']]['case']
    heads, rows = shape['heads'], shape.get('rows', shape['heads'])
    c.require(rows > 0 and heads > 0 and heads % rows == 0, 'Invalid source query group shape')
    return 1 + (heads // rows) * int(candidate_reaches_query(rows, shape['dimension']))


def expected_info(fixture, trial):
    return Counter({i: info_per_index(fixture, trial) for i in range(4)})


def info_total(kind):
    path = c.OUT / c.FIRMWARE[kind][0] / 'fixture.json'
    c.require(c.sha(path) == FIXTURES[kind], 'Frozen fixture query census changed')
    fixture = c.read(path)
    return 4 * sum(info_per_index(fixture, t) for t in range(len(fixture['trials'])))


def rewrite_one_expression(module, name, before, after):
    """Replace one reviewed expression in a hash-bound frozen function, in memory."""
    tree = ast.parse(Path(module.__file__).read_text())
    functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == name]
    c.require(len(functions) == 1, 'Frozen function identity changed')
    wanted, replacement = ast.parse(before, mode='eval').body, ast.parse(after, mode='eval').body
    class Change(ast.NodeTransformer):
        count = 0
        def visit(self, node):
            if ast.dump(node) == ast.dump(wanted):
                self.count += 1
                return ast.copy_location(replacement, node)
            return super().visit(node)
    change = Change()
    function = change.visit(functions[0])
    c.require(change.count == 1, 'Frozen expression missing or duplicated')
    unit = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
    exec(compile(unit, str(HERE / 'check_v4.py') + ':' + name, 'exec'), module.__dict__)
    return getattr(module, name)


c._source_expected_info = expected_info
rewrite_one_expression(c, 'stage4_architecture', 'Counter({i: 1 for i in range(4)})',
                       '_source_expected_info(fixture, trial)')


def check(kind, log, trace):
    if kind != 'qbs':
        for name, digest in QUERY_SOURCES.items():
            c.require(c.sha(c.OUT / c.FIRMWARE[kind][0] / 'inputs' / name) == digest,
                      'Capability query source changed: ' + name)
    return base.check(kind, log, trace)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--kind', choices=('qbs', 'perf', 'functional'), required=True)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--trace', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.kind, args.log, args.trace), indent=2, sort_keys=True))
