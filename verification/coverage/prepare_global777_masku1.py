"""Fresh777 prepare-only adapter of frozen776; no CVXIF addition, no EDA API."""
import argparse
import inspect
import json
from pathlib import Path
from types import FunctionType

import prepare_global776_masku1 as predecessor

life, need, prior = predecessor.life, predecessor.need, predecessor.prior
HERE = Path(__file__).resolve().parent
TCL = Path(__file__).with_suffix('.tcl')
SCHEMA = 'GLOBAL777_MASKU_PARENT1_BY_REFERENCE_PREPARE_V1'
BASE = life.OUT / 'akv-entropy-offline-admitted777-parent-20261007-01'
BASE_SHA = '39ad0375146e5a6d98f1ef0141030f95309e2a8409dc71f6d510b59631bc3d52'
PREP776 = life.OUT / 'global776-masku-parent1-prepared-agent-20261007-01'
PREP776_SHA = '0eaf9b6384e8aa94a8c132b76b02a346038d8a0973b46b9f74219063e79f543a'
FROZEN = {
    str(Path(predecessor.__file__).resolve()): '698bb97a6b9e09c0296d43fdf9cdc9fe6315de93b445608e8ffeaa79b243eae6',
    str(predecessor.TCL): '0cda1a5950cb25ae04f261939ee5ecff81f16aa4dd5a941c4a8f8b640a58b646',
    str(PREP776 / 'config.json'): PREP776_SHA,
    str(PREP776 / 'prepare-receipt.json'): 'beb4ee389be85a02b5e7339ce15dc68e46893abf072a2e9d24daf0dbeaf3dde0',
}


def private_function(function, replacements, extra):
    source = inspect.getsource(function)
    for old, new in replacements.items():
        need(source.count(old) == 1, 'Exact frozen population adapter anchor: ' + old)
        source = source.replace(old, new)
    namespace = dict(function.__globals__, **extra)
    exec(compile(source, __file__ + ':private-' + function.__name__, 'exec'), namespace)
    return namespace[function.__name__]


def hydrate(delta):
    need(delta['777_predecessor_config'] == str(PREP776 / 'config.json') and
         delta['777_predecessor_config_sha256'] == PREP776_SHA, 'Exact frozen776 predecessor')
    return private_function(predecessor.hydrate, {"delta['population'] == 776": "delta['population'] == 777"},
                            dict(SCHEMA=SCHEMA, __file__=__file__))(delta)


class ViewLife(predecessor.ViewLife):
    def read_bound(self, path, sha):
        data = life.read_bound(path, sha)
        if Path(path).name == 'config.json' and isinstance(data, dict) and data.get('schema') == SCHEMA:
            return hydrate(data)
        return data


def chain_gate(a, b, single, count, old_ledger, ledger):
    prior.population(a, b, single, count)
    need(len(ledger) == len(set(ledger)) == count + 1 and ledger[:-1] == old_ledger and
         ledger == [old_ledger[0], *b['tests']], 'Exact unique admitted prefix/ledger')


def chain(pins):
    old = life.read_bound(predecessor.OLD / 'config.json', predecessor.OLD_SHA)
    previous = life.read_bound(prior.BASE / 'combined-bits.json',
                               old['pins'][str(prior.BASE / 'combined-bits.json')])
    ledger = old['input_ledger']
    parent, parent_sha = prior.BASE, prior.BASE_SHA
    for base, seal, count in [(predecessor.BASE, predecessor.BASE_SHA, 776), (BASE, BASE_SHA, 777)]:
        manifest = life.read_bound(base / 'admission-manifest.json', seal)
        need(manifest['coverage_admitted'] is True and manifest['baseline'] == str(parent) and
             manifest['baseline_seal'] == parent_sha, 'Exact775->776->777 admitted chain')
        pins.update(prior.prior.merge(pins, manifest['input_pins'], manifest['output_pins'],
                                       {str(base / 'admission-manifest.json'): seal}))
        combined = life.read_bound(base / 'combined-bits.json', pins[str(base / 'combined-bits.json')])
        single = life.read_bound(base / 'single-bits.json', pins[str(base / 'single-bits.json')])
        new_ledger = (base / 'combined-inputs.txt').read_text().splitlines()
        chain_gate(previous, combined, single, count, ledger, new_ledger)
        status = life.read_bound(base / 'status.json', pins[str(base / 'status.json')])
        need(status['aggregate_passed'] == count and status['coverage_admitted'] is True and
             status['full_OR_metric_instances'] == 6162, 'Complete formal terminal PASS')
        previous, ledger, parent, parent_sha = combined, new_ledger, base, seal
    return ledger


def inherited_check(out, seal):
    function = private_function(predecessor.inherited_check, {
        '"c[\'population\']==776"': '"c[\'population\']==777"',
        "==776,'Actual776 full population'": "==777,'Actual777 full population'"},
        dict(SCHEMA=SCHEMA, BASE=BASE, BASE_SHA=BASE_SHA, ViewLife=ViewLife, __file__=__file__))
    return function(out, seal)


def check(out, seal):
    delta = life.read_bound(out / 'config.json', seal)
    c = hydrate(delta)
    need(c['output'] == str(out) and c['successor_entry'] == str(Path(__file__).resolve()) and
         c['admission'] == dict(manifest=str(BASE / 'admission-manifest.json'), seal=BASE_SHA,
                               population=777, exact776prefix=True, full6162_OR=True), 'Exact777 consumer')
    need(c['host_prepare_is_not_native_qualification'] is True and c['parent_launch_approval_required'] is True,
         'Prepare cannot claim global native qualification')
    life.check(c['pins'])
    pins = {}; ledger = chain(pins)
    need(ledger == c['input_ledger'] and all(c['pins'].get(p) == h for p, h in pins.items()), 'Complete pinned777 chain')
    previous = life.read_bound(PREP776 / 'config.json', PREP776_SHA)
    allowed = {'schema', 'output', 'population', 'successor_entry', 'admission', 'input_ledger',
               'expected_selected', 'pins', 'masku_raw776'}
    need(all(delta.get(k) == value for k, value in previous.items() if k not in allowed),
         'Frozen776 MASKU/EL/source/protected scope changed')
    native, _ = predecessor.masku(c)
    need(c['unexpanded_MASKU_child_objects'] == predecessor.unexpanded_objects(native), 'No candidate expansion')
    need((out / 'combined.el').read_bytes() == (PREP776 / 'combined.el').read_bytes() and
         (out / 'selection.tcl').read_bytes() == (PREP776 / 'selection.tcl').read_bytes(),
         'Retained exact EL/observer hooks; no unqualified CVXIF addition')
    need(predecessor.records((out / 'combined.el').read_text(), c) == c['expected_union'], 'Complete retained+MASKU EL')
    inherited_check(out, seal)
    return c


def snapshot(data, out):
    function = private_function(predecessor.snapshot, {'population=776': 'population=777',
        'formal776_manifest_seal=BASE_SHA': 'formal777_manifest_seal=BASE_SHA'},
        dict(ViewLife=ViewLife, BASE_SHA=BASE_SHA))
    function(data, out)
    data['formal776_predecessor_manifest_seal'] = predecessor.BASE_SHA
    data['CVXIF_local_pending_not_added_by_this_successor'] = True


def namespace():
    ns = predecessor.namespace()
    ns.update(life=ViewLife(), check=check, snapshot_stdout=snapshot, TCL=TCL, __file__=__file__)
    ns['verify'] = FunctionType(ns['verify'].__code__, ns)
    return ns


def prepare(out):
    need(out.parent == life.OUT and not out.exists(), 'Fresh independent777 prepare-only output')
    life.check(FROZEN)
    old = life.read_bound(PREP776 / 'config.json', PREP776_SHA)
    receipt = json.loads((PREP776 / 'prepare-receipt.json').read_bytes())
    need(receipt['config_seal'] == PREP776_SHA and receipt['status'] == 'GLOBAL776_MASKU1_PREPARED_CHECK_PASS_NO_EDA'
         and receipt['EDA_launched'] is False, 'Existing sealed776 preparation')
    pins = prior.prior.merge(old['pins'], FROZEN)
    ledger = chain(pins)
    # Add only AKV's actual777 data to the already-pinned exact776 scoped union.
    files = list((Path(ledger[-1]) / 'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
    need(len(files) == 1 and str(files[0]) in pins, 'Unique manifest-bound actual777 sample')
    typed = predecessor.strict.qualification.typed
    scope = predecessor.strict.qualification.source.SCOPE
    rows, sha = typed.rows(files[0], [scope]); need(sha == pins[str(files[0])], 'Actual777 Toggle pin')
    merged = typed.union({scope: old['masku_raw776']['union']}, rows)[scope]
    need(format(int(merged['bits'], 16), '0%db' % merged['width'])[3422:3934] == '0' * 512,
         '777 target observed/startup activity: HOLD')
    config = dict(old, schema=SCHEMA, output=str(out), population=777, successor_entry=str(Path(__file__).resolve()),
        admission=dict(manifest=str(BASE / 'admission-manifest.json'), seal=BASE_SHA, population=777,
                       exact776prefix=True, full6162_OR=True), input_ledger=ledger,
        expected_selected=[str(Path(db).with_suffix('') / p.name) for db in ledger
                           for p in sorted((Path(db) / 'snps/coverage/db/testdata').glob('*')) if p.is_dir()],
        masku_raw776=dict(sample=str(files[0]), union=merged, missing_slots=512,
                         positions=list(range(3422, 3934)), denominator_claim=False,
                         actual_population=777, capture_prefix_reused='masku776'),
        **{'777_predecessor_config': str(PREP776 / 'config.json'), '777_predecessor_config_sha256': PREP776_SHA})
    deps = [Path(__file__).resolve(), TCL, HERE / 'test_prepare_global777_masku1.py']
    pins.update({str(p): life.digest(p) for p in deps}); config['pins'] = pins
    life.check(hydrate(config)['pins']); out.mkdir()
    for name in ('combined.el', 'selection.tcl'):
        (out / name).write_bytes((PREP776 / name).read_bytes()); pins[str(out / name)] = life.digest(out / name)
    (out / 'inputs.txt').write_text('\n'.join(ledger) + '\n'); pins[str(out / 'inputs.txt')] = life.digest(out / 'inputs.txt')
    life.save(out / 'config.json', config)
    seal = life.digest(out / 'config.json'); check(out, seal)
    receipt = dict(status='GLOBAL777_MASKU1_PREPARED_CHECK_PASS_NO_EDA', config_seal=seal,
        formal777_manifest_sha256=BASE_SHA, predecessor776_config_sha256=PREP776_SHA,
        targets=1, protected=986, scopes=26, fresh_inventory_files_required=130,
        EL_and_observers_unchanged_from776=True, CVXIF_pending_not_added=True,
        EDA_launched=False, native_qualification_of_global=False, official_percentage=None)
    life.save(out / 'prepare-receipt.json', receipt)
    print(json.dumps(dict(output=str(out), config_seal=seal,
                         prepare_receipt_seal=life.digest(out / 'prepare-receipt.json'), status=receipt['status'])))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check', 'verify'))
    parser.add_argument('--output', type=Path, required=True); parser.add_argument('--seal')
    args = parser.parse_args(); out = args.output.resolve()
    if args.mode == 'prepare': prepare(out)
    else:
        need(args.seal, 'Exact prepared777 seal')
        if args.mode == 'check': check(out, args.seal); print('GLOBAL777_MASKU1_CHECK_PASS_NO_EDA')
        else: namespace()['verify'](out, args.seal)
