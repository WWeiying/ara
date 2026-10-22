"""Explicit admitted781-or-successor population, one qualified9700-direction batch.

Reuse the frozen780 thin entry and unchanged five-stage Tcl/lifecycle. Never
launch EDA at prepare/check, and never change the earlier780 report directory.
"""
import argparse
from pathlib import Path
from types import FunctionType

import report_population780_plus260 as frozen
import qbs_hit9440_native780 as large

prior, stable, life, need, OUT = frozen.prior, frozen.stable, frozen.life, frozen.need, frozen.OUT
HERE = Path(__file__).resolve().parent
BASE = OUT / 'akv-tile-range-admitted781-parent-20261008-01/admission-manifest.json'
BASE_SHA = '720511a144576a95fee244a675635c96104b249c0f99ab3d6b8e0249de77f900'
SCHEMA = 'EXPLICIT_781_OR_SUCCESSOR_QUALIFIED9700_BATCH_V1'
LARGE = ('QBS9440', OUT / 'qbs-hit9440-native780-agent-20261008-01',
         '2995f02feb9f81bdbda9fa5974c10aea86114da61052d389c18b55fb8840ca6e',
         '7a8d223671bf09439ee4b80ba83fb0ca0ec713958e55ca72bdbd83883d276797',
         'QBS_NEW688_OBJECTS9440_DIRECTIONS_NATIVE_NOT_APPLIED', 9440)
FAMILIES = (*frozen.FAMILIES, LARGE)
UNION_SHA = '5299507b7d996cc6a1831b5034e4b6832502ff822f75842e7bee3af588421bb4'


def complement(config):
    need(len(config['instances']) == 2 and config['qualified128_included'] is False
         and config['HOLD_included'] is False, 'Only two-bank new9440 scope')
    total = retained = objects = non_targets = 0
    for instance in config['instances']:
        signals = instance['signals']
        nodes = [*instance['protected'], *[dict(s['shape'], tag='vectornode') for s in signals]]
        names = [n['name'] for n in nodes]
        need(len(names) == len(set(names)) == 3193, 'Complete unique compiled bank complement')
        width = 0
        for node in nodes:
            need(node['tag'] in ('node', 'vectornode'), 'No array flattening')
            width += 1 if node['tag'] == 'node' else abs(int(node['left']) - int(node['right'])) + 1
        need(width * 2 == 66340, 'Exact complete typed bank width')
        expected_retained = {}
        for signal in signals:
            shape, bits = signal['shape'], signal['bits']
            need(signal['name'] == shape['name'] and signal['scalar'] is False
                 and shape['portnode'] == '0' and shape['line_num'] in ('269', '355', '381')
                 and int(shape['left']) == signal['left'] in (15, 31)
                 and int(shape['right']) == signal['right'] == 0
                 and len(bits) == len(set(bits)) and all(type(b) is int and 0 <= b <= signal['left'] for b in bits),
                 'Exact partial source hit vector')
            expected_retained[signal['name']] = sorted(set(range(signal['left'] + 1)) - set(bits))
            need(expected_retained[signal['name']], 'Whole hit field forbidden')
        need(instance['retained_target_signal_bits'] == expected_retained, 'Every retained target-vector bit')
        retained += sum(map(len, expected_retained.values()))
        total += width * 2
        objects += len(signals)
        non_targets += len(instance['protected'])
    need(objects == 688 and non_targets == 5698 and retained == 13456
         and len(large.primitive.bitset(config)) == 9440
         and total - 9440 == config['protected_direction_count'] == 123240
         and config['protected_target_vector_bits'] == retained, 'Exact9440/123240 direction partition')


def qualification(reader, family):
    if family != LARGE:
        return frozen.qualification(reader, family)
    name, directory, sha, config_sha, status, count = family
    receipt = reader.read(directory / 'capture-result.json', sha, True)
    config = reader.read(directory / 'config.json', config_sha, True)
    need(receipt['status'] == status and receipt['population_application'] is False
         and receipt['semantic_reload'] is True and receipt['global_final_empty'] is True
         and receipt['all_non_targets_protected'] is True and receipt['bit_directions'] == count
         and receipt['qualified128_included'] is False and receipt['HOLD_included'] is False
         and config['source_proof_sha256'] == receipt['source_proof_sha256'] == large.PROOF_SHA,
         'Exact qualified9440 authority, not HOLD or prior128')
    complement(config)
    pins = stable.merge(config['pins'], receipt['pins'])
    blobs = [reader.read(directory / name, pins[str(directory / name)]).decode('ascii')
             for name in ('first.el', 'second.el')]
    for blob in blobs:
        large.parse_el(blob, config)
    need(stable.semantic(blobs[0]) == stable.semantic(blobs[1]), 'Exact9440 native semantic roundtrip')
    reader.finish(pins)
    return blobs[1], count, stable.merge(pins, {str(directory / 'capture-result.json'): sha,
                                             str(directory / 'config.json'): config_sha})


def union_gate(base, additions):
    old = stable.semantic(base)
    occupied = frozen.physical(old)
    texts = [base]
    need([count for text, count in additions] == [132, 128, 9440], 'Exact three qualified sets')
    for text, count in additions:
        value = stable.semantic(text)
        masks = frozen.physical(value)
        need(not value[0] and sum(bin(v).count('1') for v in masks.values()) == count,
             'Exact partial Toggle additions')
        for key, mask in masks.items():
            need(not occupied.get(key, 0) & mask and
                 not any(key[0] == r[0] or key[0].startswith(r[0] + '.') for r in old[0]),
                 'No old/third/whole-scope overlap')
            occupied[key] = occupied.get(key, 0) | mask
        texts.append(text)
    text = '\n'.join(t.rstrip('\n') for t in texts) + '\n'
    need(stable.semantic_seal(stable.semantic(text)) == UNION_SHA, 'Only approved base plus9700')
    return text


def approved(reader, manifest, seal):
    source, pins, text, bits, chain, activity = prior.approved(reader, manifest, seal)
    need((manifest == BASE and seal == BASE_SHA) or
         any(r['manifest'] == str(BASE) and r['seal'] == BASE_SHA and r['population'] == 781 for r in chain),
         'Exact formal781 ancestor; no population fork')
    count = len(bits['tests'])
    need(count >= 781 and len(source['input_ledger']) == count + 1
         and len(source['expected_selected']) == count, 'Explicit admitted population identities')
    additions = []
    for family in FAMILIES:
        native, size, extra = qualification(reader, family)
        pins = stable.merge(pins, extra)
        additions.append((native, size))
    return source, pins, union_gate(text, additions), bits, chain, activity


def dependencies():
    return stable.merge(frozen.dependencies(), {
        str(Path(__file__).resolve()): life.digest(Path(__file__).resolve()),
        str(HERE / 'test_report_population_plus9700.py'): life.digest(HERE / 'test_report_population_plus9700.py')})


def metadata():
    return dict(additional_direction_count=9700, local_qualifications=[
        dict(family=name, path=str(directory / 'capture-result.json'), sha256=sha,
             config_seal=config_sha, directions=count)
        for name, directory, sha, config_sha, status, count in FAMILIES],
        protection_basis='Exact global native union; BTB8860/QBS12866212/QBS9440123240 local complements; retained typed ports/arrays/control')


def context(manifest, seal):
    namespace = dict(frozen.prepare.__globals__, __file__=__file__, BASE=manifest, BASE_SHA=seal,
                     SCHEMA=SCHEMA, approved=approved, dependencies=dependencies, metadata=metadata)
    check = FunctionType(frozen.check.__code__, namespace)
    verify = FunctionType(frozen.verify.__code__, dict(namespace, check=check))
    run = FunctionType(frozen.run.__code__, dict(namespace, check=check, verify=verify))
    def prepare(out, unit):
        def save(path, value):
            if path == out / 'prepare-receipt.json':
                value = dict(value, status='EXPLICIT_POPULATION_PLUS9700_PREPARED_NOT_LAUNCHED')
            life.save(path, value)
        from types import SimpleNamespace
        local = dict(namespace, life=SimpleNamespace(**dict(vars(life), save=save)))
        return FunctionType(frozen.prepare.__code__, local)(out, unit)
    return prepare, check, verify, run


def runtime(out, seal):
    config = stable.Reader().read(out / 'config.json', seal, True)
    need(config['schema'] == SCHEMA, 'Exact9700 runtime entry')
    return context(Path(config['admission']['path']), config['admission']['sha256'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=('prepare', 'check', 'verify', 'run-reviewed'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--seal')
    parser.add_argument('--manifest', type=Path)
    parser.add_argument('--manifest-seal')
    parser.add_argument('--service-unit')
    parser.add_argument('--parent-reviewed-seal')
    args = parser.parse_args()
    out = args.output.resolve()
    if args.mode == 'prepare':
        need(args.service_unit and args.seal is None and args.parent_reviewed_seal is None,
             'Host-only prepare and explicit service')
        need(bool(args.manifest) == bool(args.manifest_seal), 'Manifest and seal must be supplied together')
        context(args.manifest.resolve() if args.manifest else BASE, args.manifest_seal or BASE_SHA)[0](out, args.service_unit)
    else:
        need(args.seal and args.manifest is None and args.manifest_seal is None and args.service_unit is None,
             'Runtime uses sealed explicit population, never latest discovery')
        functions = runtime(out, args.seal)
        if args.mode == 'check':
            functions[1](out, args.seal)
            print('EXPLICIT_POPULATION_PLUS9700_CHECK_PASS_NO_EDA', flush=True)
        elif args.mode == 'verify':
            functions[2](out, args.seal)
        else:
            functions[3](out, args.seal, args.parent_reviewed_seal)
