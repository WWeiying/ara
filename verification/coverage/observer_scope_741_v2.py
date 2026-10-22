"""Exact serialization-only successor; frozen four-observer gates unchanged."""
import argparse
import hashlib
from pathlib import Path

SOURCE = Path(__file__).with_name('observer_scope_741.py')
SOURCE_SHA = '79c17f0f73db21a05f7eabce300e9e389b2c210d3da29f8128cf742d1cb95949'
REPLACEMENTS = (
    ("life.save(out / 'inputs.txt',", "common.save(out / 'inputs.txt',"),
    ("life.save(out / 'observer-plan.tcl',", "common.save(out / 'observer-plan.tcl',"),
    ("HERE / 'test_observer_scope_741.py', common.EXPORT):",
     "HERE / 'test_observer_scope_741.py', common.EXPORT,\n"
     "                 HERE / 'observer_scope_741_v2.py', HERE / 'test_observer_scope_741_v2.py'):"),
)


def namespace():
    data = SOURCE.read_bytes()
    if hashlib.sha256(data).hexdigest() != SOURCE_SHA:
        raise ValueError('Frozen observer predecessor drift')
    text = data.decode()
    for old, new in REPLACEMENTS:
        if text.count(old) != 1:
            raise ValueError('Serialization adapter is not exact')
        text = text.replace(old, new)
    scope = {'__name__': 'observer_scope_741_serialization_private', '__file__': str(SOURCE)}
    exec(compile(text, str(SOURCE), 'exec'), scope)
    return scope


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    a = p.parse_args()
    n = namespace()
    if a.mode == 'prepare':
        n['prepare'](a.output.absolute())
    else:
        n['require'](a.seal, 'Exact config seal required')
        n[a.mode](a.output.absolute(), a.seal)
