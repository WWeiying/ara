"""Offline manifest-order closure; only the exact sealed actual read is translated."""
import argparse
import builtins
import json
from pathlib import Path
from types import FunctionType, SimpleNamespace

import collect_akv_entropy as original

RUN = original.life.OUT/'akv-entropy-old-image775-parent-20261007-01'
PREPARED_SHA = '96c4dc17891d08ed191d1426aee04b61508570079bd0622d44b140a0842db487'
ACTUAL_SHA = '94dd5c6f0d4d748cb3e5204b6f646989eba3abced9f9fae16a70c6c45da929d2'
OUTPUT = original.life.OUT/'akv-entropy-qualified-manifest-parent-20261007-01'
ORIGINAL_SHA = 'a443d18fb3c90f6572e9ef2090ba35a38bab77771bb82468fc27e5487d901faf'
WRAPPER = Path(__file__).resolve()
ADAPTER_PINS = {str(p):original.fixture.sha(p) for p in
                (WRAPPER,WRAPPER.with_name('test_collect_akv_entropy_manifest.py'))}


def qualification_contract(record,output,manifest):
    original.require(record.get('status') == 'AKV_ENTROPY_NATIVE_INDEPENDENT_QUALIFIED_NOT_ADMITTED' and
                     type(record.get('baseline_tests')) is int and record['baseline_tests'] == 775 and
                     record.get('native_Spike_comparison') is False and
                     record.get('software_adapter_not_native') is True and
                     type(record.get('scalar_model_skips')) is int and record['scalar_model_skips'] == 0 and
                     record.get('coverage_admitted') is False, 'Wrong/incomplete original qualification')
    inputs,outputs = record['input_pins'],record['output_pins']
    original.require(inputs.get(str(RUN/'manifest.json')) == ACTUAL_SHA and
                     all(inputs.get(p) == h for p,h in manifest['pins'].items()),
                     'Qualification omitted/conflicts with executed manifest pins')
    names = {'conversion-command.json','conversion.log','entropy-ranges.vcd','scalar.json','lifecycle.json',
             'vector.json','ranges.json','perf.json','contract.json','single-inputs.txt','single-bits.json',
             'combined-bits-diagnostic.json','raw-delta.json','toggle-gain775.json'}
    original.require(set(outputs) == {str(output/name) for name in names}, 'Foreign/incomplete qualification outputs')
    return original.life.merge_pins(inputs,outputs)


def semantic_equal(left,right):
    # JSON booleans and numbers are not interchangeable, unlike Python equality.
    return json.dumps(left,sort_keys=True,separators=(',',':')) == json.dumps(right,sort_keys=True,separators=(',',':'))


def manifest_gate():
    prepared = original.life.read_bound(RUN.with_name(RUN.name+'.prepared.json'),PREPARED_SHA)
    actual = original.life.read_bound(RUN/'manifest.json',ACTUAL_SHA)
    original.require(semantic_equal(actual,prepared), 'Actual/prepared complete typed semantics differ')
    original.life.check(actual['pins'])
    return actual


def private_life():
    def read_bound(path,expected):
        if str(path) == str(RUN/'manifest.json') and expected == PREPARED_SHA:
            manifest_gate()
            return original.life.read_bound(path,ACTUAL_SHA)
        return original.life.read_bound(path,expected)
    return SimpleNamespace(**dict(vars(original.life),read_bound=read_bound))


def original_dependencies(dependencies):
    dependencies = dict(dependencies)
    own = str(WRAPPER)
    original.require(dependencies.get(own) == ADAPTER_PINS[own], 'Missing/changed exact wrapper dependency')
    del dependencies[own]
    return dependencies


def private_runner():
    import run_akv_entropy as runner
    def dependency_pins():
        return original_dependencies(runner.dependency_pins())
    prepare = FunctionType(runner.prepare.__code__,dict(runner.prepare.__globals__,dependency_pins=dependency_pins),
                           argdefs=runner.prepare.__defaults__)
    return SimpleNamespace(**dict(vars(runner),prepare=prepare))


def private_import(name,globals=None,locals=None,fromlist=(),level=0):
    if name == 'run_akv_entropy' and level == 0:
        return private_runner()
    return builtins.__import__(name,globals,locals,fromlist,level)


def closure_receipt(output):
    output = Path(output).absolute()
    original.require(output == OUTPUT and output.resolve() == output and
                     not (output/'failure.json').exists(), 'Wrong/failed closure directory')
    manifest = manifest_gate()
    qualification = output/'qualification.json'
    original.require(qualification.is_file() and not qualification.is_symlink(), 'No completed original qualification')
    seal = original.fixture.sha(qualification)
    record = original.life.read_bound(qualification,seal)
    pins = qualification_contract(record,output,manifest)
    sources = [Path(__file__).resolve(),Path(__file__).with_name('test_collect_akv_entropy_manifest.py').resolve()]
    anchors = dict(ADAPTER_PINS)
    anchors.update({str(RUN/'manifest.json'):ACTUAL_SHA,
                    str(RUN.with_name(RUN.name+'.prepared.json')):PREPARED_SHA,
                    str(qualification):seal,str(Path(original.__file__).resolve()):ORIGINAL_SHA})
    pins = original.life.merge_pins(pins,anchors)
    original.life.check(pins)
    receipt = output/'manifest-order-closure.json'
    original.life.save(receipt,dict(status='ORIGINAL_FULL_COLLECT_PASS_MANIFEST_ORDER_CLOSURE',
        original_qualification=str(qualification),original_qualification_sha256=seal,
        prepared_sha256=PREPARED_SHA,actual_manifest_sha256=ACTUAL_SHA,
        wrapper_sha256=anchors[str(sources[0])],tests_sha256=anchors[str(sources[1])],
        original_input_pins=record['input_pins'],original_output_pins=record['output_pins'],
        input_pins=pins,coverage_admitted=False,EDA_launched=False))
    original.life.check(pins)
    return receipt


def collect(output=OUTPUT):
    output = Path(output).absolute()
    original.require(output == OUTPUT and not output.exists(), 'Unique fresh closure output required')
    manifest_gate()
    original.life.check(ADAPTER_PINS)
    private_builtins = dict(vars(builtins),__import__=private_import)
    implementation = FunctionType(original.collect.__code__,dict(original.collect.__globals__,
        life=private_life(),__builtins__=private_builtins))
    implementation(RUN,PREPARED_SHA,output)
    closure_receipt(output)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=OUTPUT)
    args = parser.parse_args()
    collect(args.output)
