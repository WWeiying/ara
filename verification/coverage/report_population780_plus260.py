"""One explicit780 report: unchanged approved policy plus qualified BTB132/QBS128.

No local captures or EDA at prepare/check. The legacy check's no-additions
field is adapted only in its private config view after this entry enforces the
exact additions; persisted configs/results always declare the additions.
"""
import argparse
from pathlib import Path
from types import FunctionType, SimpleNamespace

import report_current_population as prior
import capture_btb_bit0_132_v4 as btb
import qbs_hit128_native780 as qbs

stable, life, need, OUT = prior.stable, prior.life, prior.need, prior.OUT
HERE = Path(__file__).resolve().parent
SCHEMA = 'FORMAL780_QUALIFIED_BTB132_QBS128_BATCH_V1'
BASE = OUT / 'dtlb-ppn-swap-offline-admitted780-agent-20261008-01/admission-manifest.json'
BASE_SHA = '4b679eed5892200a4d166748d9ae504a31d5dddcb3cdbca0e1f3ec61cab2bb7b'
UNION_SHA = '2ad7caa3026c7acdd4832c259ad02c075dcad2133f8675b357fbbaf8cacca3e5'
FAMILIES = (
    ('BTB', OUT / 'btb-bit0-132-native-v4-prepared779-agent-20261008-01',
     'f6f0dfb8521e56c56fc561970a308ca34adef5e30986db649dab208e7b8fe117',
     '5af3d27f7c8ab90751abc9c471db28992c7bb31ec8174551d1c48200754ccd12',
     'BTB_BIT0_132_LOCAL_NATIVE_QUALIFIED_NOT_POPULATION_APPLIED', 132),
    ('QBS', OUT / 'qbs-hit128-native780-bank0-p2-slot1-row0-agent-20261008-01',
     'f2de6691f6e94a08061ae97b82aeee23c4779ebbe41aa8c06fb16e75182f21a3',
     '7864c19fd3f06b06a148ae39f5c8ed97f7b15aef3c61cfeaa51db0b41d420ed5',
     'QBS_BANK0_P2_SLOT1_ROW0_EXACT128_NATIVE_NOT_APPLIED', 128),
)


def physical(value):
    masks = {}
    for (scope, checks, name, kind, declaration, prefix, direction), mask in value[1].items():
        key = (scope, checks, name, prefix, direction)
        masks[key] = masks.get(key, 0) | mask
    return masks


def union_gate(base, additions):
    prior_value = stable.semantic(base)
    occupied = physical(prior_value)
    texts = [base]
    count = 0
    for text, expected in additions:
        value = stable.semantic(text)
        need(not value[0], 'Only precise partial Toggle directives may be added')
        targets = physical(value)
        need(sum(bin(v).count('1') for v in targets.values()) == expected,
             'Exact qualified direction count')
        for key, mask in targets.items():
            scope = key[0]
            need(not any(scope == r[0] or scope.startswith(r[0] + '.') for r in prior_value[0]),
                 'Opaque ancestor/whole-scope exclusion overlaps addition')
            need(not occupied.get(key, 0) & mask, 'Existing/cross-family exclusion overlap')
            occupied[key] = occupied.get(key, 0) | mask
        texts.append(text)
        count += expected
    need(count == 260, 'Exactly260 additional directions')
    text = '\n'.join(t.rstrip('\n') for t in texts) + '\n'
    need(stable.semantic_seal(stable.semantic(text)) == UNION_SHA,
         'Exact approved base plus260 native physical union')
    return text


def qualification(reader, family):
    name, directory, receipt_sha, config_sha, status, count = family
    receipt = reader.read(directory / 'capture-result.json', receipt_sha, True)
    config = reader.read(directory / 'config.json', config_sha, True)
    need(receipt['status'] == status and receipt['population_application'] is False,
         'Exact local qualification authority')
    pins = stable.merge(config['pins'], receipt['pins'])
    blobs = [reader.read(directory / filename, pins[str(directory / filename)]).decode('ascii')
             for filename in ('first.el', 'second.el')]
    if name == 'BTB':
        records = [btb.native_records(blob) for blob in blobs]
        need(records[0] == records[1] and len(records[0]) == 132 and
             not records[0] & btb.original.complement(config['inventory']),
             'BTB exact132/full8860 protected complement')
    else:
        for blob in blobs:
            qbs.parse_el(blob, config)
        need(len(qbs.primitive.bitset(config)) == 128,
             'QBS exact128/full typed protected complement')
    need(stable.semantic(blobs[0]) == stable.semantic(blobs[1]), 'Native semantic roundtrip')
    reader.finish(pins)
    return blobs[1], count, stable.merge(pins, {str(directory / 'capture-result.json'): receipt_sha,
                                            str(directory / 'config.json'): config_sha})


def approved(reader, manifest, seal):
    need(manifest == BASE and seal == BASE_SHA, 'Only explicit formal780 population')
    source, pins, text, bits, chain, activity = prior.approved(reader, manifest, seal)
    need(len(bits['tests']) == 780 and len(source['input_ledger']) == 781 and
         len(source['expected_selected']) == 780, 'Exact780 tests plus design')
    additions = []
    for family in FAMILIES:
        native, count, extra = qualification(reader, family)
        pins = stable.merge(pins, extra)
        additions.append((native, count))
    return source, pins, union_gate(text, additions), bits, chain, activity


def dependencies():
    return stable.merge(prior.dependencies(), {
        str(Path(__file__).resolve()): life.digest(Path(__file__).resolve()),
        str(HERE / 'test_report_population780_plus260.py'):
            life.digest(HERE / 'test_report_population780_plus260.py')})


def metadata():
    return dict(additional_direction_count=260, local_qualifications=[
        dict(family=name, path=str(directory / 'capture-result.json'), sha256=sha,
             config_seal=config_sha, directions=count)
        for name, directory, sha, config_sha, status, count in FAMILIES],
        protection_basis='Exact complete global native union; local sealed full complements; no aggregate vector flag claim')


def prepare(out, unit):
    def save(path, value):
        if path == out / 'config.json':
            value = dict(value, new_exclusions_added=True, **metadata())
        elif path == out / 'prepare-receipt.json':
            value = dict(value, status='FORMAL780_PLUS260_PREPARED_NOT_LAUNCHED', **metadata())
        life.save(path, value)
    namespace = dict(prior.prepare.__globals__, approved=approved, dependencies=dependencies,
                     SCHEMA=SCHEMA, __file__=__file__, life=SimpleNamespace(**dict(vars(life), save=save)))
    return FunctionType(prior.prepare.__code__, namespace)(out, BASE, BASE_SHA, unit)


def check(out, seal):
    config = stable.Reader().read(out / 'config.json', seal, True)
    need(config['schema'] == SCHEMA and config['new_exclusions_added'] is True and
         all(config.get(k) == v for k, v in metadata().items()), 'Exact explicit260 batch contract')

    class LegacyView(stable.Reader):
        def read(self, path, sha, parse=False):
            value = super().read(path, sha, parse)
            if Path(path) == out / 'config.json' and parse:
                need(sha == seal and value == config, 'Only exact config contract view')
                return dict(value, new_exclusions_added=False)
            return value

    namespace = dict(prior.check.__globals__, approved=approved, dependencies=dependencies,
                     SCHEMA=SCHEMA, __file__=__file__,
                     stable=SimpleNamespace(**dict(vars(stable), Reader=LegacyView)))
    FunctionType(prior.check.__code__, namespace)(out, seal)
    return config


def verify(out, seal):
    # The original result already seals the explicit config and every input,
    # including both local receipts. Preserve its readonly repeat behavior.
    return FunctionType(prior.verify.__code__, dict(prior.verify.__globals__, check=check))(out, seal)


def run(out, seal, reviewed):
    return FunctionType(stable.run.__code__, dict(stable.run.__globals__, check=check, verify=verify))(out, seal, reviewed)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check', 'verify', 'run-reviewed'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--service-unit')
    parser.add_argument('--parent-reviewed-seal')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.mode == 'prepare':
        need(args.service_unit and args.seal is None, 'Explicit service; fixed780 authority')
        prepare(out, args.service_unit)
    else:
        need(args.seal and args.service_unit is None, 'Sealed runtime only')
        if args.mode == 'check':
            check(out, args.seal)
            print('FORMAL780_PLUS260_CHECK_PASS_NO_EDA', flush=True)
        elif args.mode == 'verify':
            verify(out, args.seal)
        else:
            run(out, args.seal, args.parent_reviewed_seal)
