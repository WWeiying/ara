"""Exact typed-array syntax successor using the observed cast168 native fixture."""
import argparse
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('cast168_typed_private_entry', HERE/'capture_cast168_native_entry.py')
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)
base, v2, life, require = entry.base, entry.v2, entry.life, entry.require
ORIGIN = life.OUT/'fpnew-cast-fp-shared168-native745-agent-20261007-03'
ORIGIN_SHA = 'e3374fca5893ec80e3bb3392956b6c6a9e9a066c60b6da6ded429f4653c0449c'
FIRST_SHA = 'd3d2d17ee15dde5502a06f787990a1d108b9fa627ff6d3bf2caf8781e33f9145'
DIMENSIONS = r'(?:\[-?\d+:-?\d+\])+'


def normalize(text):
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith('Toggle '):
            m = re.fullmatch(r'Toggle (\w+) "logic (.+)"', line)
            require(m is not None, 'Exact whole-object logic declaration required')
            name, declaration = m.groups()
            suffix = re.fullmatch(r'(\w+)('+DIMENSIONS+r')', declaration)
            prefix = re.fullmatch(r'('+DIMENSIONS+r')(\w+)', declaration)
            require(suffix is not None or prefix is not None, 'Exact typed multidimensional syntax')
            declared, dims = suffix.groups() if suffix else tuple(reversed(prefix.groups()))
            require(declared == name, 'Typed declaration/object name differs')
            line = 'Toggle %s "logic %s%s"' % (name, declared, dims)
        lines.append(line)
    return '\n'.join(lines)+'\n'


def parse_el(text, c, native_meta=None):
    # Only move the complete ordered dimension sequence. Frozen parser still
    # enforces every object, scope, checksum, dimension and whole-object gate.
    return v2.parse_el(normalize(text), c, native_meta)


class Route:
    def __truediv__(self, name):
        return HERE/({'capture_cast168_native.tcl': 'capture_cast168_native_entry.tcl',
                      'test_capture_cast168_native.py': 'test_cast168_native_typed.py'}.get(name, name))


base.HERE = Route()
base.__file__ = str(Path(__file__).resolve())
base.parse_el = parse_el


def fixture():
    c = life.read_bound(ORIGIN/'config.json', ORIGIN_SHA)
    life.check(c['pins'])
    require(life.digest(ORIGIN/'first.el') == FIRST_SHA, 'Actual first EL drift')
    meta = {}
    for index, instance in enumerate(c['instances']):
        before = v2.inventory(ORIGIN, c, 'before', index)
        require(before == v2.inventory(ORIGIN, c, 'selected', index), 'Actual protected inventory drift')
        names = {row[2]: row[1] for row in before}
        for target in instance['targets']:
            meta[instance['scope'], target['name']] = names[target['native_name']]
    records = parse_el((ORIGIN/'first.el').read_text(), c, meta)
    require(len(records) == 168 and
            all((ORIGIN/name).read_bytes() == b'' for name in ('initial-empty.el', 'cleanup-empty.el')),
            'Actual168/cleanup evidence')
    return c, meta, records


def prepare(out):
    fixture()
    deps = {str(ORIGIN/'config.json'): ORIGIN_SHA, str(ORIGIN/'first.el'): FIRST_SHA}
    for p in [HERE/'capture_cast168_native_entry.py', HERE/'test_cast168_native_entry_adapter.py',
              ORIGIN/'initial-empty.el', ORIGIN/'cleanup-empty.el',
              *ORIGIN.glob('native_before_*.tsv'), *ORIGIN.glob('native_selected_*.tsv')]:
        deps[str(p)] = life.digest(p)
    save = life.save
    def bound_save(path, data):
        if path == out/'config.json':
            data = dict(data)
            data['pins'] = life.merge_pins(data['pins'], deps)
            data['typed_profile'] = 'EXACT_LOGIC_NAME_RANGES_OR_RANGES_NAME_ORDERED_FULL_DIMENSIONS'
            data['actual_typed_fixture'] = str(ORIGIN/'first.el')
            life.check(data['pins'])
        save(path, data)
    life.save = bound_save
    try:
        entry.prepare(out)
    finally:
        life.save = save


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run', 'inspect', 'el', 'inventory'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal'); p.add_argument('--file')
    p.add_argument('--stage'); p.add_argument('--index', type=int)
    a = p.parse_args(); out = a.output.resolve()
    if a.mode == 'prepare':
        prepare(out)
    elif a.mode in ('el', 'inventory'):
        c = json.loads((out/'config.json').read_bytes())
        if a.mode == 'el':
            require(a.file in ('first.el', 'second.el'), 'EL filename')
            print(len(parse_el((out/a.file).read_text(), c)))
        else:
            print(len(v2.inventory(out, c, a.stage, a.index)))
    else:
        require(a.seal, 'Exact seal')
        (base.run if a.mode == 'run' else v2.inspect)(out, a.seal)
