"""Strict canonical-JSON packet comparison; every frozen source/native gate retained."""
import argparse
import json
from pathlib import Path
from types import FunctionType

import c910_lane23_padding1424_local as old

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_c910_lane23_padding1424_local_v3.py')
PREDECESSORS = {
    str(Path(old.__file__).resolve()): '111f2ddb34c7b91be13ce67877ce8790902df9dceca350b47c1a95e9981bdbd7',
    str(old.TCL): 'ae210f71526234ba5e0100b56a59d47f964b4281c3f9f95eb4e86faefbab926e',
    str(old.TEST): 'e3f90a04cbb47a5536139df996327f3aa05fce8e105699ba79acc9a31924ae5c',
}


def evidence():
    old.life.check(PREDECESSORS)
    proof = old.evidence()
    proof['pins'] = old.life.merge_pins(proof['pins'], PREDECESSORS)
    return proof


def source_packet_gate(saved, current):
    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    old.need(canonical(saved) == canonical(current), 'Exact canonical source packet including all writers')


def check(out, seal):
    c = life.read_bound(out / 'config.json', seal)
    life.check(c['pins'])
    need(c['schema'] == SCHEMA and c['output'] == str(out) and c['directions'] == 1424 and
         c['timeout_seconds'] == 900 and c['population_application'] is False and
         c['automatic_retry'] is False and c['initial_X_qualified'] is False, 'Closed local contract')
    proof = evidence()
    need(all(c[k] == proof[k] for k in ('instances', 'design', 'vdb', 'test')), 'Source/typed/sample replay')
    source_packet_gate(json.loads((out / 'source-proof.json').read_bytes()), proof)
    origin = ptw.primitive.old.RUN / 'config.json'
    template = life.read_bound(origin, ptw.primitive.old.SEAL)
    need(c['identity'] == template['identity'], 'Sealed native executable roles')
    required = life.merge_pins(proof['pins'], template['pins'])
    required[str(origin)] = ptw.primitive.old.SEAL
    required.update(ptw.frozen.tcl_pins(TCL))
    need(all(c['pins'].get(p) == sha for p, sha in required.items()), 'Complete required dependency pins')
    for p in (SCRIPT, TEST, TCL):
        need(c['pins'].get(str(p)) == life.digest(p), 'Required source/test/Tcl pin')
    need((out / 'selection.tcl').read_text() == selection(c) and
         (out / 'native-bind.tcl').read_text() == TCL.read_text(), 'Exact native driver')
    el_gate((out / 'candidate.el').read_text(), c)
    return c


env = dict(vars(old), __name__=__name__, __file__=str(SCRIPT), SCRIPT=SCRIPT, TEST=TEST,
           SCHEMA='C910_LANE23_PADDING1424_LOCAL_V3_STRICT_CANONICAL_JSON', evidence=evidence, check=check)
for name, fn in vars(old).items():
    if isinstance(fn, FunctionType) and fn.__module__ == old.__name__ and name not in ('evidence', 'check'):
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
