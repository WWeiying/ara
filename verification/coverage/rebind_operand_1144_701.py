"""Recheck qualified native1144 against admitted701; no DVE application."""
import argparse
import hashlib
import json
from pathlib import Path
import re

from inventory_operand_debug import Design, ROOT
from closure_point_inventory import points


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    output = parser.parse_args().output.absolute()
    if output.parent != ROOT / 'verification/out' or output.exists():
        raise ValueError('Fresh direct output required')
    old = ROOT / 'verification/out/operand-native-static-qualification-690-20261006-01'
    manifest = json.loads((old / 'manifest.sha256.json').read_bytes())
    if sha(old / 'manifest.sha256.json') != '28b37e48ad7fad4b8663fb8cd39c0de758f122ef1d4bca0709286c86767004b0':
        raise ValueError('Original native qualification seal differs')
    if set(manifest) != {'qualification.json', 'qualified-records.json'}:
        raise ValueError('Unexpected qualification members')
    for name, expected in manifest.items():
        if sha(old / name) != expected:
            raise ValueError('Qualification record drift')
    qualification = json.loads((old / 'qualification.json').read_bytes())
    records = json.loads((old / 'qualified-records.json').read_bytes())['records']
    if qualification['status'] != 'NATIVE_STATIC_1144_QUALIFIED_FOR_EXACT_OLD_DESIGN_NOT_APPLIED':
        raise ValueError('Not qualified native evidence')
    pins = dict(qualification['pins'])
    for path in (old / 'manifest.sha256.json', old / 'qualification.json', old / 'qualified-records.json', Path(__file__)):
        pins[str(path)] = sha(path)
    base = ROOT / 'verification/out/gap94-offline-admitted-701-20261006-01'
    for name in ('combined-bits.json', 'status.json', 'combined-inputs.txt'):
        pins[str(base / name)] = sha(base / name)
    if any(sha(p) != h for p, h in pins.items()):
        raise ValueError('Qualified proof dependency drift')
    bitmap = json.loads((base / 'combined-bits.json').read_bytes())
    status = json.loads((base / 'status.json').read_bytes())
    listing = (base / 'combined-inputs.txt').read_text().splitlines()
    if status['status'] != 'PASS_RAW_UNION_HISTORICAL_ONLY' or status['aggregate_passed'] != 701:
        raise ValueError('Not admitted701')
    if bitmap['design'] != qualification['corpus_design'] or listing[1:] != bitmap['tests'] or len(set(listing)) != 702:
        raise ValueError('Design/population differs')
    design = Design(Path(listing[0]))
    for relative, expected in bitmap['design'].items():
        path = design.db / relative
        if sha(path) != expected:
            raise ValueError('Compiled shape drift')
        pins[str(path)] = expected
    definitions, inherited, seen = {}, set(), set()
    for item in records:
        scope = item['scope']
        record = bitmap['metrics']['branch'][scope]
        if scope not in definitions:
            definition = design.definition(scope, 'branch')
            if [design.hierarchy[scope].get('chksum'), definition.get('chksum')] != item['checksum']:
                raise ValueError('Compiled definition differs')
            definitions[scope] = {p['raw_index']: p for p in points('branch', definition, record['width'])}
        if record['checksum'] not in (None, item['checksum'][1]):
            raise ValueError('Latest metric checksum differs')
        if record['checksum'] is None:
            inherited.add(scope)
        index = item['raw_index']
        point = definitions[scope][index]
        spec, vector = re.fullmatch(r'Branch (\d+) \((\d+)\)', item['point']).groups()
        if (point['native_id'], point['vector'], point['attributes']['chksum']) != (spec, vector, item['spec_checksum']):
            raise ValueError('Exact native/raw coordinate differs')
        if (scope, index) in seen or int(record['bits'], 16) & (1 << (record['width'] - index - 1)):
            raise ValueError('Duplicate or hit contradicts structural proof')
        seen.add((scope, index))
    if len(seen) != 1144 or len(definitions) != 36:
        raise ValueError('Incomplete exact record population')
    if any(sha(p) != h for p, h in pins.items()):
        raise ValueError('Evidence changed during rebind')
    result = dict(status='NATIVE1144_REBOUND_TO_RAW701_NOT_APPLIED', tests=701,
                  records=records, target_count=1144, target_hits=0, pins=pins,
                  compiled_bound_null_checksum_scopes=sorted(inherited),
                  application_approval=False, official_percentages=False,
                  limits='Same compiled design only; full701 native application/protected audit still required')
    with output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in ('status', 'tests', 'target_count', 'target_hits')}))


if __name__ == '__main__':
    main()
