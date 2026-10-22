"""JSON-container-only successor. Frozen source/EL/native gates are unchanged."""
import argparse
import json
from pathlib import Path
from types import FunctionType

import c910_lane23_padding1424_local as old

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_c910_lane23_padding1424_local_v2.py')
PREDECESSORS = {
    str(Path(old.__file__).resolve()): '111f2ddb34c7b91be13ce67877ce8790902df9dceca350b47c1a95e9981bdbd7',
    str(old.TCL): 'ae210f71526234ba5e0100b56a59d47f964b4281c3f9f95eb4e86faefbab926e',
    str(old.TEST): 'e3f90a04cbb47a5536139df996327f3aa05fce8e105699ba79acc9a31924ae5c',
}


def canonical_evidence():
    old.life.check(PREDECESSORS)
    proof = json.loads(json.dumps(old.evidence()))
    proof['pins'] = old.life.merge_pins(proof['pins'], PREDECESSORS)
    return proof


env = dict(vars(old), __name__=__name__, __file__=str(SCRIPT), SCRIPT=SCRIPT, TEST=TEST,
           SCHEMA='C910_LANE23_PADDING1424_LOCAL_V2_JSON_CONTAINERS_ONLY', evidence=canonical_evidence)
for name, fn in vars(old).items():
    if isinstance(fn, FunctionType) and fn.__module__ == old.__name__ and name != 'evidence':
        env[name] = FunctionType(fn.__code__, env, name, fn.__defaults__)
for name, value in env.items():
    if not name.startswith('__'):
        globals()[name] = value


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=('prepare', 'check', 'inventory', 'el', 'verify'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--seal')
    p.add_argument('--stage', choices=STAGES)
    p.add_argument('--file', choices=('first.el', 'second.el'))
    a = p.parse_args()
    out = a.output.resolve()
    if a.mode == 'prepare':
        need(a.seal is None, 'Prepare is not launch approval')
        result = prepare(out)
    else:
        c = check(out, a.seal)
        if a.mode == 'inventory':
            inventory(out, c, a.stage)
        elif a.mode == 'el':
            need(a.file is not None, 'Explicit native export')
            el_gate((out / a.file).read_text(), c)
        result = verify(out, a.seal) if a.mode == 'verify' else dict(status=a.mode + '_PASS_NO_LAUNCH')
    print(json.dumps(result, indent=2), flush=True)
