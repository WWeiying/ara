"""735 host preparation with two explicitly sealed734 tool-catalog authorities."""
from pathlib import Path
from types import FunctionType, SimpleNamespace

import eight_policy_epoch_735_report as prior

SCRIPT = Path(__file__).resolve()
TEST = SCRIPT.with_name('test_eight_policy_epoch_735_report_v2.py')
OUT = prior.report.OUT
ROOT = OUT / 'eight-policy-semantic-735-agent-20261006-02'
PLAN = 'epoch-readiness-735-v2-plan.json'
require = prior.require
ORIGIN = OUT / 'gap110-offline-admitted-734-parent-20261006-01'
ORIGIN_SEAL = '388c041fc323289521358ee2ef08bad6367cbb3b93fe3adabf6527d0a4847261'
ORIGIN_BOOK_SEAL = '1c435b304f17e54179a6ccadde8e1e757c0475404e2a4403752993a97491f53a'
CATALOG = {
    '/lib64/libgcc_s.so.1': '7565f226204bf69d12a259489f722159f91d4e55109848e67b9e0f8deddb1c98',
    '/usr/bin/python3': '63520974d589373fbc041a60f199c4d7ad4fae96727da8fda4a5d21455f6acef',
}


def clone(namespace, **overrides):
    """Clone only functions sharing this private reader namespace."""
    values = dict(vars(namespace), **overrides)
    for name, value in vars(namespace).items():
        if name not in overrides and isinstance(value, FunctionType) and value.__globals__.get(name) is value:
            values[name] = FunctionType(value.__code__, values, name, value.__defaults__, value.__closure__)
    return SimpleNamespace(**values)


def catalog_authority(context, reader):
    proof = context.cc_proof()
    nodes = [n for n in proof['chain'] if n['population'] == 734]
    require(len(nodes) == 1 and nodes[0]['admission'] == str(ORIGIN) and
            nodes[0]['manifest_sha256'] == ORIGIN_SEAL and
            nodes[0]['ledger_sha256'] == ORIGIN_BOOK_SEAL,
            'Exact734 catalog ancestry absent')
    pins = {}
    manifest, ledger = reader.sealed_ledger(ORIGIN, ORIGIN_SEAL, pins)
    require(manifest['schema'] == 'GAP110_HISTORICAL734_SOFTWARE_NATIVE_ADMISSION_V1' and
            manifest['output_pins'][str(ORIGIN / 'evidence-pins.json')] == ORIGIN_BOOK_SEAL,
            'Catalog ancestor manifest/book differs')
    require(all(ledger.get(path) == expected for path, expected in CATALOG.items()),
            'Sealed734 tool catalog differs')
    return {path: ledger[path] for path in CATALOG}, pins


def source_context(owner):
    original = prior.wiring.source_context732(owner)
    reader = prior.wiring_base.clone(prior.wiring.identity, Path=owner.Path, json=owner.json,
                                     frozen=owner.frozen)

    class CatalogContext(type(original)):
        def ledger(self):
            ledger = dict(super().ledger())
            inherited, authority_pins = catalog_authority(self, reader)
            for path, expected in inherited.items():
                require(ledger.get(path, expected) == expected, 'Current/ancestor catalog conflict')
                ledger[path] = expected
            self.catalog_authority_pins = authority_pins
            return ledger

        def source_binding(self, pins):
            result = super().source_binding(pins)
            for path, expected in self.catalog_authority_pins.items():
                self.pin(pins, path, expected)
            result['inherited734_tool_catalog'] = {
                'admission': str(ORIGIN), 'manifest_sha256': ORIGIN_SEAL,
                'ledger_sha256': ORIGIN_BOOK_SEAL, 'expected_pins': dict(CATALOG),
                'claimed_as735_top_level': False, 'historical_alias_invocation_claim': False,
            }
            return result

    return CatalogContext(prior.ADMISSION, prior.SEAL, 735)


wiring = clone(prior.wiring, source_context732=source_context, SCRIPT=SCRIPT, TEST=TEST)


def dependencies():
    return tuple(dict.fromkeys((*prior.dependencies(), SCRIPT, TEST)))


report = clone(prior.report, wiring=wiring, SCRIPT=SCRIPT, TEST=TEST, ROOT=ROOT, PLAN=PLAN,
               dependencies=dependencies)


def family():
    builder = report.Builder()
    frozen = prior.wiring_base.clone(wiring.population.frozen, sha=builder.sha,
                                     pin=builder.pin, load_sealed=builder.load_sealed)
    six = SimpleNamespace(**dict(vars(wiring.population), read_config=report.read_six))
    eight = prior.wiring_base.clone(wiring.eight, six=six, frozen=frozen)
    shared = prior.wiring_base.clone(wiring.fixed.shared, frozen=frozen)
    fixed = prior.wiring_base.clone(wiring.fixed, eight=eight, six=six, frozen=frozen, shared=shared,
                                    SCRIPT=SCRIPT, TEST=TEST, TCL=prior.TCL,
                                    dependencies=dependencies, payloads=prior.payloads)
    return prior.install_semantic(fixed)


def save(path, value):
    if path.name == PLAN:
        old = prior.report_base.restrict_roles.__globals__['prior']
        local = prior.wiring_base.clone(old, wiring=wiring, family=family)
        restrict = FunctionType(prior.report_base.restrict_roles.__code__,
            dict(prior.report_base.restrict_roles.__globals__, prior=local), 'restrict_roles')
        value = restrict(value)
    prior.report_original.save(path, value)


def rebind_private_reader():
    # Original Wiring methods carry their original private global namespace.
    globals_ = dict(prior.wiring_namespace, source_context732=source_context)
    methods = {name: FunctionType(value.__code__, globals_, name, value.__defaults__, value.__closure__)
               for name, value in vars(prior.PrivateWiring).items() if isinstance(value, FunctionType)}
    parent = type('Catalog735PrivateWiring', (prior.PrivateWiring,), methods)

    class Wiring(parent):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fixed = prior.wiring_base.clone(self.fixed, SCRIPT=SCRIPT, TEST=TEST, TCL=prior.TCL,
                dependencies=dependencies, payloads=prior.payloads)
            prior.install_semantic(self.fixed)

    wiring.Wiring = Wiring
    for function in vars(report).values():
        if isinstance(function, FunctionType) and function.__globals__.get(function.__name__) is function:
            function.__globals__.update(family=family, save=save)
    report.family = family
    report.save = save


rebind_private_reader()


def main():
    import argparse
    import json
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check', 'verify'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    args = parser.parse_args()
    output = args.output.absolute()
    if args.mode == 'prepare':
        require(args.seal is None, 'Fresh prepare has no external seal')
        result = dict(status='PREPARED_NO_DVE', population=735, seal=report.prepare(output))
    else:
        require(args.seal, 'Explicit readiness seal required')
        result = report.check(output, args.seal, args.mode == 'verify')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
