"""Exact historical735 eight-policy report successor. Prepare/check never launch DVE."""
import ast
import inspect
from pathlib import Path
from types import CodeType, FunctionType, SimpleNamespace

import eight_policy_epoch_732_report_v2 as report_base
import eight_policy_epoch_732_report as report_original
import eight_policy_epoch_732_wiring as wiring_base
import eight_policy_csv_fix_runtime_v2 as semantic

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_eight_policy_epoch_735_report.py')
TCL = SCRIPT.with_name('eight_policy_epoch_734_report.tcl')
PARENT_SCRIPT = SCRIPT.with_name('eight_policy_epoch_734_report.py')
PARENT_TEST = SCRIPT.with_name('test_eight_policy_epoch_734_report.py')
NATIVE_TCL = SCRIPT.with_name('native_exclusion_multiset_v2.tcl')
ADMISSION = report_original.OUT / 'readonly-csr-offline-admitted-735-parent-20261006-01'
SEAL = '4fb3c0219a791c9a669ad9403d97634042f57b423e0e94d7c65bdf57cfa59397'
SCHEMA = 'READONLY_CSR_HISTORICAL_ADMISSION_V1'
require = report_original.require


INTEGER_REBINDS = {
    ('source_context732.<genexpr>',1): 'identity constructor population',
    ('source_context732.SourceContext.source_binding',4): 'identity_population metadata',
    ('source_context732',20): 'source Context population',
    ('read_six',3): 'reader population guard',
    ('prepare',18): 'CSV population and plan population',
    ('prepare_reader_entry',6): 'existing fixed population guard',
    ('check',5): 'readiness population guard',
    ('run_reviewed',10): 'launch claim population',
    ('main',26): 'terminal population label',
    ('_check_context',1): 'mandatory source Context population',
}
STRING_REBINDS = {
    'workspace_llvm732','EIGHT_EPOCH_HISTORICAL732_REPORT_V1',
    'PREPARED_HISTORICAL732_EPOCH_CHECK_PASS_NO_DVE',
    'Only explicitly sealed formal732','Exact historical732 only',
    'Exact prepared historical732 fixed contract required',
    'Reviewed exact732 source Context required; never relabel729',
    'Exact732 six reader population/seal required','Actual732 workspace alias SHA differs',
    'Private732BaseContext','Private732IdentityContext',
}
REBIND_AUDIT = []


def rebound(code, prefix=None):
    """Retain frozen guard bodies, extending only explicit732 population labels to735."""
    values = []
    prefix = code.co_name if prefix is None else prefix
    for index,value in enumerate(code.co_consts):
        original=value
        role=None
        if isinstance(value, CodeType):
            value = rebound(value, prefix+'.'+value.co_name)
        elif type(value) is int and value == 732:
            require((prefix,index) in INTEGER_REBINDS,'Unreviewed732 constant: '+prefix+':'+str(index))
            role=INTEGER_REBINDS[(prefix,index)]
            value = 735
        elif type(value) is tuple and value == (730,731,732):
            require((prefix,index)==('source_context732',5),'Unreviewed schema key rebinding')
            value=(730,731,735)
            role='source Context schema addition; original732 schema retained separately'
        elif isinstance(value, str) and value in STRING_REBINDS:
            value = value.replace('732', '735')
            role='population/schema/diagnostic label only'
        if role is not None:
            REBIND_AUDIT.append(dict(function=prefix,slot=index,before=original,after=value,role=role,
                                     source_first_line=code.co_firstlineno))
        values.append(value)
    return code.replace(co_consts=tuple(values))


def clone735(module, **overrides):
    namespace = dict(vars(module), **overrides)
    for name, value in vars(module).items():
        if name not in overrides and isinstance(value, FunctionType) and value.__module__ == module.__name__:
            namespace[name] = FunctionType(rebound(value.__code__), namespace, name,
                                           value.__defaults__, value.__closure__)
    return SimpleNamespace(**namespace)


def extended_cc_proof(namespace):
    function = wiring_base.identity.cc_ancestry
    constants = function.__code__.co_consts
    require(sum(type(c) is int and c == 729 for c in constants) == 1 and
            sum(type(c) is int and c == 7 for c in constants) == 1,
            'Frozen ancestry guard boundary differs')
    code = function.__code__.replace(co_consts=tuple(
        735 if type(c) is int and c == 729 else 13 if type(c) is int and c == 7 else c
        for c in constants))
    REBIND_AUDIT.append(dict(function='cc_ancestry',before=[729,7],after=[735,13],
                             role='thirteen exact schema/status/count/prefix admissions735..723'))
    return FunctionType(code, namespace, function.__name__, function.__defaults__, function.__closure__)


schemas = dict(wiring_base.identity.SCHEMAS)
schemas.update({732:wiring_base.root732.SCHEMA,
                733:'STORE_FAULT_FLUSH_HISTORICAL_ADMISSION_V1',
                734:'GAP110_HISTORICAL734_SOFTWARE_NATIVE_ADMISSION_V1'})
identity = wiring_base.clone(wiring_base.identity, SCHEMAS=schemas)
root735 = SimpleNamespace(ADMISSION=ADMISSION, SEAL=SEAL, SCHEMA=SCHEMA)
wiring = clone735(wiring_base, root732=root735, identity=identity,
                  SCRIPT=SCRIPT, TEST=TEST, extended_cc_proof=extended_cc_proof)


def payloads(base):
    result = wiring_base.fixed.payloads(base)
    raw = wiring_base.eight.TCL.read_bytes()
    old = b'eight_initialize; qbsapp_session'
    require(raw.count(old) == 1, 'Frozen eight entry install boundary differs')
    result['eight-session-v2.tcl'] = raw.replace(old, b'eight_initialize; nem_install; qbsapp_session')
    result['native-exclusion-multiset-v2.tcl'] = NATIVE_TCL.read_bytes()
    return result


def dependencies():
    return tuple(dict.fromkeys((*report_original.dependencies(),
        Path(report_base.__file__).resolve(), Path(report_base.__file__).with_name('test_eight_policy_epoch_732_report_v2.py'),
        SCRIPT, TEST, TCL, NATIVE_TCL, PARENT_SCRIPT, PARENT_TEST, semantic.Path(semantic.__file__).resolve(),
        semantic.Path(semantic.__file__).with_name('test_eight_policy_csv_fix_runtime_v2.py'),
        *wiring_base.fixed.dependencies())))


def install_semantic(backend):
    successor = wiring_base.clone(semantic, prior=backend, Path=backend.eight.Path)
    # Both seals are required. All original native/state/report/error gates remain.
    backend.verify = successor.verify
    return backend


report = clone735(report_original, wiring=wiring, SCRIPT=SCRIPT, TEST=TEST,
                  ROOT=report_original.OUT/'eight-policy-semantic-735-agent-20261006-01',
                  PLAN='epoch-readiness-735-plan.json', dependencies=dependencies)


def family():
    builder = report.Builder()
    frozen = wiring_base.clone(wiring.population.frozen, sha=builder.sha,
                               pin=builder.pin, load_sealed=builder.load_sealed)
    six = SimpleNamespace(**dict(vars(wiring.population), read_config=report.read_six))
    eight = wiring_base.clone(wiring.eight, six=six, frozen=frozen)
    shared = wiring_base.clone(wiring.fixed.shared, frozen=frozen)
    fixed = wiring_base.clone(wiring.fixed, eight=eight, six=six, frozen=frozen, shared=shared,
                              SCRIPT=SCRIPT, TEST=TEST, TCL=TCL,
                              dependencies=dependencies, payloads=payloads)
    return install_semantic(fixed)


report.family = family
# Cloned functions use the private namespace, not SimpleNamespace attributes.
for function in vars(report).values():
    if isinstance(function, FunctionType) and function.__module__ == report_original.__name__:
        function.__globals__['family'] = family


wiring_namespace = wiring.source_context732.__globals__
attrs = {name:FunctionType(rebound(value.__code__), wiring_namespace, name,
                           value.__defaults__, value.__closure__)
         for name,value in vars(wiring_base.Wiring).items() if isinstance(value,FunctionType)}
PrivateWiring = type('Private735Wiring', (wiring_base.Wiring,), attrs)


class Wiring(PrivateWiring):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fixed = wiring_base.clone(self.fixed, SCRIPT=SCRIPT, TEST=TEST, TCL=TCL,
                                        dependencies=dependencies, payloads=payloads)
        install_semantic(self.fixed)


wiring.Wiring = Wiring
wiring_namespace['Wiring'] = Wiring


def save(path, value):
    # Preserve every hash obligation; large historical JSON is not gratuitously parsed.
    if path.name == report.PLAN:
        prior = report_base.restrict_roles.__globals__['prior']
        local = wiring_base.clone(prior, wiring=wiring, family=family)
        restrict = FunctionType(report_base.restrict_roles.__code__,
            dict(report_base.restrict_roles.__globals__, prior=local), 'restrict_roles')
        value = restrict(value)
    report_original.save(path, value)


report.save = save
for function in vars(report).values():
    if isinstance(function, FunctionType) and function.__module__ == report_original.__name__:
        function.__globals__['save'] = save


def prepare(output):
    output = Path(output).absolute()
    seal = report.prepare(output)
    return seal


def check(output, seal, generated=False):
    return report.check(Path(output).absolute(), seal, generated)


def main():
    import argparse
    import json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare','check','verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args=parser.parse_args()
    if args.mode=='prepare':
        require(args.seal is None,'No seal on fresh prepare')
        result=dict(status='PREPARED_NO_DVE',seal=prepare(args.output),population=735)
    else:
        require(args.seal,'Explicit readiness seal required')
        result=check(args.output,args.seal,args.mode=='verify')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    main()

