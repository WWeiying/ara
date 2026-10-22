"""Grouped native EL parser successor; all original freeze artifacts stay intact."""
import argparse
import inspect as introspection
import json
from pathlib import Path
import re
from types import FunctionType

import masku_zero3_native796 as old

OLD_SHA = '77cb267b51e714bfbda25d182fa8154a99f9ad8227ac9ee9485bb79b5a7a7a77'
ORIGINAL_TEST = old.HERE / 'test_masku_zero3_native796.py'
ORIGINAL_TEST_SHA = 'a72834e80bbb1555190a44d99c834c873a37d795b9462e252e549f6aa5042833'
FIRST = old.OUT / 'ptw-rvh0-outputs156-local-v2-prepared794-agent-20261008-01/first.el'
FIRST_SHA = '6fbecb8b8547c9b1de6894c5aae9e0a07e3e1cdadeb29cb2c7130f434ac055a9'
FIRST_CONFIG = FIRST.parent / 'config.json'
FIRST_CONFIG_SHA = '250fb9ba8ce5159cb2c25b4f8846009f1b87cbddcc1837bd95b1435160d2926c'
SCHEMA = 'MASKU_ZERO3_NATIVE796_V2_GROUPED_EXACT_EL'
ENTRY = Path(__file__).with_suffix('.tcl')


def parse_records(text, scope, checksums, members, annotation):
    """An annotation anywhere in a block qualifies that block, not adjacent lines."""
    actual = {}
    checksum = instance = None
    block_members = []
    annotations = []
    blocks = 0

    def finish():
        nonlocal blocks
        old.need(checksum == checksums and instance == scope and block_members and annotations,
                 'Complete checksum/scope/object/annotation block required')
        old.need(all(a == annotation for a in annotations), 'Wrong per-object annotation')
        for name, declaration in block_members:
            old.need(name not in actual, 'Duplicate object/physical bits across native blocks')
            actual[name] = (scope, checksums, name, declaration, annotation)
        blocks += 1

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('//'):
            continue
        match = re.fullmatch(r'CHECKSUM:\s*"([^"\r\n]+)"', line)
        if match:
            if checksum is not None:
                finish()
            old.need(match[1] == checksums, 'Exact design/Toggle checksum only')
            checksum, instance = match[1], None
            block_members, annotations = [], []
            continue
        match = re.fullmatch(r'INSTANCE:\s*(\S+)', line)
        if match:
            old.need(checksum == checksums and instance is None and match[1] == scope,
                     'One exact instance per checksum block; no scopeextra')
            instance = match[1]
            continue
        match = re.fullmatch(r'ANNOTATION:\s*"([^"\r\n]*)"', line)
        if match:
            old.need(instance == scope and match[1] == annotation, 'Exact annotation within object scope')
            annotations.append(match[1])
            continue
        match = re.fullmatch(r'Toggle\s+(\S+)\s+"([^"\r\n]+)"', line)
        old.need(instance == scope and match is not None, 'Only full typed Toggle; no metric/partial/direction')
        name, declaration = match.groups()
        old.need(name in members and declaration == members[name], 'Exact object and full physical range')
        old.need(name not in {n for n, _ in block_members}, 'Duplicate object within block')
        block_members.append((name, declaration))
    old.need(checksum is not None, 'Missing native checksum block')
    finish()
    old.need(blocks > 0 and set(actual) == set(members), 'Exact complete target object set')
    return sorted(actual.values())


def records(text, c):
    inst = next(i for i in c['instances'] if i['scope'] == old.SCOPE)
    members = {n: 'logic %s[255:0]' % n for n in old.NAMES}
    return parse_records(text, old.SCOPE, '%s %s' % (inst['design_checksum'], inst['toggle_checksum']),
                         members, old.ANNOTATION)


def context():
    old.need(old.digest(old.__file__) == OLD_SHA and old.digest(FIRST) == FIRST_SHA and
             old.digest(FIRST_CONFIG) == FIRST_CONFIG_SHA and old.digest(ORIGINAL_TEST) == ORIGINAL_TEST_SHA,
             'Frozen predecessor/native serialization reference drift')
    env = dict(vars(old), __file__=__file__, ENTRY=ENTRY, records=records,
               SCHEMA=SCHEMA, FIRST=FIRST, FIRST_SHA=FIRST_SHA, OLD_SHA=OLD_SHA, old=old,
               FIRST_CONFIG=FIRST_CONFIG, FIRST_CONFIG_SHA=FIRST_CONFIG_SHA,
               ORIGINAL_TEST=ORIGINAL_TEST, ORIGINAL_TEST_SHA=ORIGINAL_TEST_SHA)
    for name, fn in vars(old).items():
        if isinstance(fn, FunctionType) and fn.__module__ == old.__name__ and name != 'records':
            code = fn.__code__.replace(co_consts=tuple(
                'test_masku_zero3_native796_v2.py' if v == 'test_masku_zero3_native796.py' else v
                for v in fn.__code__.co_consts))
            env[name] = FunctionType(code, env, name, fn.__defaults__, fn.__closure__)
    base_contract = env['contract']

    def contract(c):
        base_contract(c)
        old.need(c['records_parser_schema'] == SCHEMA and
                 c['pins'].get(str(Path(old.__file__).resolve())) == OLD_SHA and
                 c['pins'].get(str(FIRST)) == FIRST_SHA and
                 c['pins'].get(str(FIRST_CONFIG)) == FIRST_CONFIG_SHA and
                 c['pins'].get(str(ORIGINAL_TEST)) == ORIGINAL_TEST_SHA, 'Exact v2 predecessor/native evidence pins')

    env['contract'] = contract
    source = introspection.getsource(old.prepare)
    anchors = {
        "HERE / 'test_masku_zero3_native796.py', DVE_EXE, DVE_ENTRY):":
            "HERE / 'test_masku_zero3_native796_v2.py', DVE_EXE, DVE_ENTRY, Path(old.__file__).resolve(), FIRST, FIRST_CONFIG, ORIGINAL_TEST):",
        "c = dict(status=": "c = dict(records_parser_schema=SCHEMA, status=",
    }
    for before, after in anchors.items():
        old.need(source.count(before) == 1, 'Exact predecessor prepare anchor')
        source = source.replace(before, after)
    exec(compile(source, __file__ + ':private-prepare', 'exec'), env)
    return env


_context = context()
for _name, _value in _context.items():
    if not _name.startswith('__') and _name not in ('records', 'old'):
        globals()[_name] = _value


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'verify-config', 'bind', 'inventory', 'el', 'selection', 'inspect'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--stage', choices=STAGES)
    parser.add_argument('--index', type=int)
    args = parser.parse_args()
    out = args.output.absolute()
    if args.mode == 'prepare':
        prepare(out)
    else:
        need(args.seal, 'Exact successor seal')
        c = verify(out, args.seal)
        if args.mode == 'bind': bind(out, c)
        elif args.mode == 'inventory': inventory(out, c, args.stage, args.index)
        elif args.mode == 'el': check_el(out, c, args.stage)
        elif args.mode == 'selection': bound_selection(out)
        elif args.mode == 'inspect': inspect(out, args.seal)
    print(json.dumps(dict(mode=args.mode, output=str(out), config_sha256=digest(out / 'config.json'),
                         records_parser_schema=SCHEMA)))
