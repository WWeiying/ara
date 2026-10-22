"""Offline runner API closure; original full qualification and outputs stay intact."""
import argparse
import ast
import inspect
from pathlib import Path
from types import FunctionType, SimpleNamespace

import collect_scalar_c910_pattern795 as original

life,require=original.life,original.require
COLLECTOR_SHA='ad563ec73cd629dc83fc9520c1d73152d200c125438b6bf8942becc4d28af799'
RUNNER_SHA='abd97044ca2cbf0de2aef755f909ebc193fbd08af87fb636b5eacaf6c7660bb8'
INHERITED_SHA='cb4a6b8f0e57693090909c150ad0adb2447b474dfb25686edd711ff0dd53d751'
EXPECTED_API={
    'verify','PRE','PRE_SHA','NAME','reused.lifecycle.converter.CONVERTER',
    'exact_fields','BUDGET','ELF','IMAGE_SHA',
}


def runner_references(function):
    tree=ast.parse(inspect.getsource(function));parents={child:node for node in ast.walk(tree) for child in ast.iter_child_nodes(node)}
    paths=set()
    for node in ast.walk(tree):
        if not isinstance(node,ast.Attribute) or isinstance(parents.get(node),ast.Attribute):continue
        parts=[];value=node
        while isinstance(value,ast.Attribute):parts.append(value.attr);value=value.value
        if isinstance(value,ast.Name) and value.id=='runner':paths.add('.'.join(reversed(parts)))
    return paths


def private_runner():
    for module,sha in ((original,COLLECTOR_SHA),(original.runner,RUNNER_SHA),(original.frozen,INHERITED_SHA)):
        require(life.digest(Path(module.__file__))==sha,'Frozen inherited qualification source')
    # These are the actual full collector and terminal consumer functions, not a hand-written stand-in.
    api=runner_references(original.frozen.collect)|runner_references(original.frozen.original.terminal_gate)
    require(api==EXPECTED_API,'Full inherited runner dependency inventory differs')
    proxy=SimpleNamespace(**vars(original.runner))
    require(not hasattr(proxy,'reused'),'Only the documented missing API may be supplied')
    proxy.reused=original.runner.old.reused
    for path in sorted(api):
        value=proxy
        for name in path.split('.'):value=getattr(value,name)
    converter=proxy.reused.lifecycle.converter
    require(life.digest(converter.CONVERTER)==converter.CONVERTER_SHA,'Exact frozen converter identity')
    return proxy


def authority():
    files=(Path(__file__).resolve(),Path(__file__).with_name('test_collect_scalar_c910_pattern795_v2.py').resolve())
    return {str(p):life.digest(p) for p in files}


def collect(run,out,seal):
    proxy=private_runner();pins=authority();life.check(pins)
    FunctionType(original.collect.__code__,dict(original.collect.__globals__,runner=proxy))(run,out,seal)
    core=out/'qualification.json';core_sha=life.digest(core);q=life.read_bound(core,core_sha)
    require(q['status']=='FULL_SCALAR_C910_NORMAL224_NATIVE_QUALIFIED_NOT_ADMITTED'
        and q['baseline']==795 and q['coverage_admitted'] is False,'Complete original qualification required')
    life.check(q['input_pins']);life.check(q['output_pins']);life.check(pins)
    # Exclusive separate publication: never rewrite the original qualification JSON.
    receipt=dict(status='FULL_NORMAL224_RUNNER_API_CLOSURE_NOT_ADMITTED',core_qualification=str(core),
        core_sha256=core_sha,original_collector_sha256=COLLECTOR_SHA,original_runner_sha256=RUNNER_SHA,
        inherited_collector_sha256=INHERITED_SHA,runner_api=sorted(EXPECTED_API),
        supplied_api='reused = frozen runner.old.reused',input_pins=pins,
        coverage_admitted=False,new_simulation=False,original_gates_omitted=[])
    life.save(out/'runner-api-closure.json',receipt)
    print('RUNNER_API_CLOSURE_NOT_ADMITTED',life.digest(out/'runner-api-closure.json'))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--prepared-seal',required=True)
    a=p.parse_args();collect(a.run.resolve(),a.output.resolve(),a.prepared_seal)
