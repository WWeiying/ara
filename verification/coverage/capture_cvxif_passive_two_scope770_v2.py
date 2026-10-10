"""Exact readback successor; preserves frozen01 and all original gates."""
import argparse
import inspect
from pathlib import Path
import capture_cvxif_passive_two_scope770 as old


def prepare(out):
    source = inspect.getsource(old.prepare)
    old.require(source.count("'capture_cvxif_passive_two_scope770.tcl'") == 2, 'Exact Tcl replacement anchors')
    source = source.replace("'capture_cvxif_passive_two_scope770.tcl'", "'capture_cvxif_passive_two_scope770_v2.tcl'")
    anchor = '    contract(c)\n'
    old.require(source.count(anchor) == 1, 'Dependency insertion anchor')
    source = source.replace(anchor, '''    for p in (HERE/'capture_cvxif_passive_two_scope770.tcl',
              HERE/'capture_cvxif_passive_two_scope770_v2.py',
              HERE/'test_capture_cvxif_passive_two_scope770_v2.py'):
        pins[str(p)] = life.digest(p)
    contract(c)
''')
    namespace = dict(old.__dict__)
    exec(compile(source, str(Path(__file__)), 'exec'), namespace)
    namespace['prepare'](out)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','run','verify'))
    p.add_argument('--output',type=Path,required=True); p.add_argument('--seal')
    p.add_argument('--parent-reviewed',action='store_true')
    a=p.parse_args(); out=a.output.resolve()
    if a.mode=='prepare': prepare(out)
    elif a.mode=='run': old.run(out,a.seal,a.parent_reviewed)
    elif a.mode=='verify': old.verify(out,a.seal)
    else: old.check(out,a.seal); print('SEALED_CHECK_PASS_NO_EDA')
