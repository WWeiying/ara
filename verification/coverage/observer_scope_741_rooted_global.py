"""Frozen Rooted predecessor plus only Tcl globals and successor dependency pins."""
import argparse
import hashlib
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'observer_scope_741_rooted.py'
SOURCE_SHA = '92c9a209a50c1488da0bb8520637dc5ba7c9c083dc7ca62dd4a359ef342b47a1'
TCL = HERE / 'observer_scope_741_rooted.tcl'
TCL_SHA = '970dab7cd363f0d64531dc97f079b044c75310784879a533b9dd8b40bab660ae'


def namespace():
    if hashlib.sha256(SOURCE.read_bytes()).hexdigest() != SOURCE_SHA or hashlib.sha256(TCL.read_bytes()).hexdigest() != TCL_SHA:
        raise ValueError('Frozen observer Rooted predecessor drift')
    before = TCL.read_text().splitlines()[1:]
    after = (HERE / 'observer_scope_741_rooted_global.tcl').read_text().splitlines()[1:]
    expected = [line.replace('global env observer_scopes', 'global env observer_scopes p740_scopes p740_root_names') for line in before]
    if after != expected:
        raise ValueError('Only the explicit Tcl globals may change')
    text = SOURCE.read_text()
    old = 'observer_scope_741_rooted.tcl'
    if text.count(old) != 2 or text.count("PREVIOUS / 'result.json',") != 1:
        raise ValueError('Exact successor wiring differs')
    text = text.replace(old, 'observer_scope_741_rooted_global.tcl')
    text = text.replace("PREVIOUS / 'result.json',", "PREVIOUS / 'result.json',\n"
        "             HERE / 'observer_scope_741_rooted.tcl',\n"
        "             HERE / 'observer_scope_741_rooted_global.py',\n"
        "             HERE / 'test_observer_scope_741_rooted_global.py',")
    scope = {'__name__': 'observer_rooted_global_private', '__file__': str(SOURCE)}
    exec(compile(text, str(SOURCE), 'exec'), scope)
    return scope


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'run', 'verify'))
    p.add_argument('--output', required=True, type=Path)
    p.add_argument('--seal')
    a = p.parse_args()
    n = namespace()
    if a.mode == 'prepare':
        n['prepare'](a.output.absolute())
    else:
        n['require'](a.seal, 'Exact prepared seal required')
        n[a.mode](a.output.absolute(), a.seal)
