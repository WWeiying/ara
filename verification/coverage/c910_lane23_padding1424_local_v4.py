"""Strict canonical-JSON packet comparison; every frozen source/native gate retained."""
import argparse
import json
from pathlib import Path
from types import FunctionType

import c910_lane23_padding1424_local_v3 as old

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_c910_lane23_padding1424_local_v4.py')
PYTHON = Path('/usr/bin/python3').resolve()
PREDECESSORS = dict(old.PREDECESSORS)
PREDECESSORS.update({
    str(Path(old.__file__).resolve()): 'e92a0fe052c80db5e9f0c38765d1d844471428464aa7e44e6f40e9329544eea0',
    str(old.TEST): 'e0ad5ec87757c54c5409fdc1106a416d55e2a52739d45193bf43547c13126185',
})



def evidence():
    old.life.check(PREDECESSORS)
    proof = old.evidence()
    proof['pins'] = old.life.merge_pins(proof['pins'], PREDECESSORS)
    return proof


def source_packet_gate(saved, current):
    def canonical(value):
        return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=True, allow_nan=False)
    old.need(canonical(saved) == canonical(current), 'Exact canonical source packet including all writers')


def selection(c):
    text = ''.join('set mq_%s {%s}\n' % (k, c[k]) for k in ('design', 'vdb', 'test'))
    text += 'set mq_instances [list ' + ' '.join('[list {%s} [list %s]]' %
            (i['scope'], ' '.join('{%s}' % x for x in old.ptw.labels(i))) for i in c['instances']) + ']\n'
    return text + 'set tied_python {%s}\nset tied_helper {%s}\nset tied_seal $env(C1424_CONFIG_SEAL)\n' % (PYTHON, SCRIPT)


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
           old=old, PREDECESSORS=PREDECESSORS, PYTHON=PYTHON,
           SCHEMA='C910_LANE23_PADDING1424_LOCAL_V4_FIXED_PYTHON', evidence=evidence, check=check, selection=selection)
for name, fn in vars(old).items():
    if isinstance(fn, FunctionType) and fn.__module__ == old.__name__ and name not in ('evidence', 'check', 'selection'):
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
