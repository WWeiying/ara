"""One MIN_SCALE slot15 measurement; AUX-slot15 was rejected before simulation."""
import argparse
import ast
import inspect
import textwrap
from pathlib import Path
from types import FunctionType, SimpleNamespace

import run_qbs_affine_aux_slot15 as template

life, require = template.life, template.require
BASE, BASE_SHA, PRE, PRE_SHA, SCOPE = template.BASE,template.BASE_SHA,template.PRE,template.PRE_SHA,template.SCOPE
focused = template.focused
STAGES = {'min_scale': (3,284)}
PROOF = life.OUT/'qbs-remaining15-fsm-native-shape-parent-20261007-01.json'


def configuration(stage):
    require(stage == 'min_scale','Only MIN_SCALE slot15 authorized')
    c = template.configuration('aux')
    c['ext_value'] = 3
    return c


def selection(stage):
    c = configuration(stage)
    return ('set ext_target {'+c['ext_target']+'}\nset ext_value 3\nset ext_guard {'+
            c['ext_guard']+'}\nset ext_dump_objects {'+' '.join(c['ext_dump_objects'])+'}\n')


def command(stage,out):
    configuration(stage)
    return [v.replace('qbs_affine_slot0_min_scale_external_reset','qbs_affine_slot15_min_scale_external_reset')
            for v in template.old.command(stage,out)]


def prepared_function(namespace):
    tree = ast.parse(textwrap.dedent(inspect.getsource(template.prepare)))
    edits = {279:(284,2),'aux':('min_scale',3),
             'qbs_affine_slot15_aux':('qbs_affine_slot15_min_scale',1),
             'test_run_qbs_affine_aux_slot15.py':('test_run_qbs_affine_min_slot15.py',1),
             'Exact slot15 raw279 must still be zero':('Exact slot15 MIN raw284 must still be zero',1)}
    for value,(replacement,count) in edits.items():
        sites = [n for n in ast.walk(tree) if isinstance(n,ast.Constant) and type(n.value) is type(value) and n.value == value]
        require(len(sites) == count,'Exact preparation adapter source drift: '+str(value))
        for site in sites: site.value = replacement
    exec(compile(ast.fix_missing_locations(tree),__file__,'exec'),namespace)
    return namespace['prepare']


def prepare(out):
    proof_sha = life.digest(PROOF)
    proof = life.read_bound(PROOF,proof_sha)
    require(proof['status'] == 'FORMAL760_COMPILED_FSM_REMAINING15_MIN_SCALE_ONLY' and proof['population'] == 760 and
            proof['gaps']['scope'] == SCOPE and proof['gaps']['checksum'] == '3794445597' and
            [r['raw_position'] for r in proof['gaps']['missing']] == [18*i+14 for i in range(1,16)] and
            all(r['kind'] == 'Transition' and r['name'] == 'FP_MIN_SCALE_MULTIPLY->FP_DOT_CONVERT' and
                not r['already_native_qualified_exclusion'] for r in proof['gaps']['missing']), 'Exact parent compiled proof required')
    dependencies = dict(proof['pins'],**{str(PROOF):proof_sha})
    for path in (Path(template.__file__).resolve(),Path(__file__).resolve(),
                 Path(__file__).with_name('test_run_qbs_affine_min_slot15.py')):
        dependencies[str(path)] = life.digest(path)
    def check(pins): return life.check(life.merge_pins(pins,dependencies))
    def save(path,value):
        if path.name.endswith('.prepared.json'):
            value = dict(value,pins=life.merge_pins(value['pins'],dependencies))
        life.save(path,value)
    private = SimpleNamespace(**dict(vars(life),check=check,save=save))
    ns = dict(template.prepare.__globals__,configuration=configuration,selection=selection,command=command,
              life=private,__file__=__file__)
    prepared_function(ns)(out)


def backend():
    ns = dict(vars(template.old),configuration=configuration,selection=selection,command=command,
              BASE=BASE,BASE_SHA=BASE_SHA,STAGES=STAGES)
    for name in ('markers','run'):
        ns[name] = FunctionType(getattr(template.old,name).__code__,ns,name)
    return SimpleNamespace(**ns)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=('prepare','run'))
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--seal')
    a = p.parse_args()
    if a.mode == 'prepare': prepare(a.output.resolve())
    else:
        require(a.seal,'Prepared seal required')
        backend().run('min_scale',a.output.resolve(),a.seal)
