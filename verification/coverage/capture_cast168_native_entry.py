"""Absolute-entry successor; frozen cast168 compatibility and gates unchanged."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('cast168_entry_private_v2', HERE/'capture_cast168_native_v2.py')
v2 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(v2)
base, life, require = v2.base, v2.life, v2.require
PRIOR = life.OUT/'fpnew-cast-fp-shared168-native745-agent-20261007-02'
PRIOR_SHA = '80de7439d31cf1dd2fe43d78ea4b2d924a097a1f120a0bde94887f983e6847ee'
RECEIPT = life.OUT/'fpnew-cast168-native745-entry-hold-review-agent-20261007-02.json'
RECEIPT_SHA = 'af439bbc2309104121269a8966b7a54157d46e764bc604dd39b33b13e28a729c'


class Route:
    def __truediv__(self, name):
        return HERE/({'capture_cast168_native.tcl': 'capture_cast168_native_entry.tcl',
                      'test_capture_cast168_native.py': 'test_cast168_native_entry_adapter.py'}.get(name, name))


base.HERE = Route()
base.__file__ = str(Path(__file__).resolve())


def prepare(out):
    prior = life.read_bound(PRIOR/'config.json', PRIOR_SHA)
    require(len(prior['pins']) == 141, 'Exact frozen predecessor pin count')
    life.check(prior['pins'])
    life.read_bound(RECEIPT, RECEIPT_SHA)
    deps = {str(PRIOR/'config.json'): PRIOR_SHA, str(RECEIPT): RECEIPT_SHA}
    for name in ('capture_cast168_native_v2.py', 'capture_cast168_native_v2.tcl',
                 'test_capture_cast168_native_v2.py', 'test_cast168_dve_entry.py'):
        p = HERE/name
        deps[str(p)] = life.digest(p)
    save = life.save
    def bound_save(path, data):
        if path == out/'config.json':
            data = dict(data)
            data['pins'] = life.merge_pins(data['pins'], deps)
            data['entry_profile'] = 'ABSOLUTE_FROZEN_SOURCE_NO_INFO_SCRIPT_CONTEXT'
            data['entry_context_HOLD'] = str(PRIOR)
            life.check(data['pins'])
        save(path, data)
    life.save = bound_save
    try:
        v2.prepare(out)
    finally:
        life.save = save
    c = json.loads((out/'config.json').read_bytes())
    print(json.dumps(dict(seal=life.digest(out/'config.json'), actual_pins=len(c['pins']))), flush=True)


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
            print(len(v2.parse_el((out/a.file).read_text(), c)))
        else:
            print(len(v2.inventory(out, c, a.stage, a.index)))
    else:
        require(a.seal, 'Exact seal')
        (base.run if a.mode == 'run' else v2.inspect)(out, a.seal)
