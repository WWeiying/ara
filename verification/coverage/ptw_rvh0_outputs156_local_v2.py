"""Only annotation serialization-order adaptation; predecessor remains frozen."""
import argparse
import json
from pathlib import Path
from types import FunctionType

import ptw_rvh0_outputs156_local as old

OLD_SHA = '2daf7c891fabe40b8c28c28a472ff5f1da53eecbd2cc156c416eb7669d727bdd'
FIRST = old.life.OUT/'ptw-rvh0-outputs156-local-prepared794-agent-20261008-01/first.el'
FIRST_SHA = '6fbecb8b8547c9b1de6894c5aae9e0a07e3e1cdadeb29cb2c7130f434ac055a9'
SCHEMA = 'PTW_RVH0_OUTPUTS156_LOCAL_V2_ANNOTATION_ORDER_ONLY'


def el_gate(text, c):
    # Exactly one checksum/instance pair is already enforced by the original
    # parser. Move only its sole annotation; never normalize any directive.
    lines = text.splitlines()
    checksum = instance = False
    annotation = None
    remaining = []
    for line in lines:
        if line.startswith('CHECKSUM:'):
            old.need(not checksum and not instance, 'Unique checksum block')
            checksum = True
        elif line.startswith('INSTANCE:'):
            old.need(checksum and not instance, 'Unique scope after checksum')
            instance = True
        elif line.startswith('ANNOTATION:'):
            old.need(instance and annotation is None and line == 'ANNOTATION: "'+old.ANNOTATION+'"',
                     'One exact annotation within the same scope')
            annotation = line
            continue
        remaining.append(line)
    old.need(annotation is not None, 'Required unique annotation')
    where = next((n+1 for n,l in enumerate(remaining) if l.startswith('INSTANCE:')), None)
    old.need(where is not None, 'Annotation scope missing')
    remaining.insert(where, annotation)
    return old.el_gate('\n'.join(remaining)+'\n', c)


def context():
    old.need(old.life.digest(old.__file__) == OLD_SHA, 'Frozen predecessor drift')
    env = dict(vars(old), __file__=__file__, SCHEMA=SCHEMA, el_gate=el_gate)
    for name, fn in vars(old).items():
        if isinstance(fn, FunctionType) and fn.__module__ == old.__name__ and name != 'el_gate':
            env[name] = FunctionType(fn.__code__, env, name, fn.__defaults__)
    return env


def prepare(out):
    env = context()
    old.need(out.parent == old.life.OUT and not out.exists(), 'Fresh successor directory only')
    proof = env['evidence']()
    template = old.life.read_bound(old.primitive.old.RUN/'config.json', old.primitive.old.SEAL)
    pins = old.life.merge_pins(proof['pins'], template['pins'])
    pins[str(old.primitive.old.RUN/'config.json')] = old.primitive.old.SEAL
    for module in list(old.sys.modules.values()):
        p = getattr(module, '__file__', None)
        if p and Path(p).resolve().parent == old.HERE:
            pins[str(Path(p).resolve())] = old.life.digest(p)
    pins.update(old.frozen.tcl_pins(old.TCL))
    for p, sha in [(FIRST, FIRST_SHA), (Path(old.__file__).resolve(), OLD_SHA)]:
        old.need(old.life.digest(p) == sha, 'Preserved failed source/EL drift')
        pins[str(p)] = sha
    test = Path(__file__).with_name('test_ptw_rvh0_outputs156_local_v2.py')
    pins[str(test)] = old.life.digest(test)
    previous_test = old.HERE/'test_ptw_rvh0_outputs156_local.py'
    pins[str(previous_test)] = old.life.digest(previous_test)
    c = dict(schema=SCHEMA, output=str(out), population_application=False, automatic_retry=False,
             timeout_seconds=900, instances=[proof['instance']], fields=12, directions=156,
             protected_objects=137, pins=pins, **{k:template[k] for k in ('identity','design','vdb','test')})
    el = env['candidate'](c['instances']); el_gate(el,c)
    old.need(el_gate(FIRST.read_text(),c) == el_gate(el,c), 'Actual saved native exact156 identity')
    text = env['selection'](c); host = env['host_hook'](c,text,el)
    old.life.check(pins)
    out.mkdir()
    for name,value in [('source-proof.json',proof),('host-evidence.json',host)]:
        old.life.save(out/name,value);pins[str(out/name)] = old.life.digest(out/name)
    for name,data in [('candidate.el',el),('selection.tcl',text),('native-bind.tcl',old.TCL.read_text())]:
        with (out/name).open('x') as f: f.write(data)
        pins[str(out/name)] = old.life.digest(out/name)
        if name.endswith('.tcl'):old.primitive.check_generated_tcl.check(out/name)
    old.life.save(out/'config.json',c)
    return dict(output=str(out),seal=old.life.digest(out/'config.json'),EDA_started=False)


def check(out,seal):
    env = context(); c = env['check'](out,seal)
    old.need(c['pins'].get(str(FIRST)) == FIRST_SHA and
             c['pins'].get(str(Path(old.__file__).resolve())) == OLD_SHA,
             'Preserved failed predecessor provenance')
    for p in (Path(__file__).resolve(),Path(__file__).with_name('test_ptw_rvh0_outputs156_local_v2.py')):
        old.need(c['pins'].get(str(p)) == old.life.digest(p), 'Successor source/test pin')
    return c


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','check','before','first','second','verify','run'))
    p.add_argument('--output',type=Path,required=True);p.add_argument('--seal');p.add_argument('--parent-reviewed-seal')
    a=p.parse_args();out=a.output.resolve()
    if a.mode=='prepare':print(json.dumps(prepare(out)),flush=True)
    else:
        c=check(out,a.seal);env=context();env['check']=check
        if a.mode=='before':env['before_gate'](out,c)
        elif a.mode in ('first','second'):el_gate((out/(a.mode+'.el')).read_text(),c)
        elif a.mode=='verify':env['verify'](out,a.seal)
        elif a.mode=='run':env['run'](out,a.seal,a.parent_reviewed_seal)
        print(a.mode+'_PASS')
