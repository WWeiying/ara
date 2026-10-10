"""Read-only raw FSM gap comparison; never an official percentage or waiver."""
import argparse
import hashlib
import json
from pathlib import Path

import rank_admitted_fsm_gaps746 as old

PRIORITY = old.life.OUT / 'formal760-fsm-priority-parent-20261007-01.json'


def bound(path, sha):
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != sha:
        raise ValueError('Input seal differs: ' + str(path))
    return json.loads(data)


def compare(priority, before746, before760, latest):
    if priority['status'] != 'FORMAL760_FSM_PRIORITY_DIAGNOSTIC_ONLY' or \
            priority['qualified_exclusion_identities'] != 155:
        raise ValueError('Wrong diagnostic/native baseline')
    for bitmap, population in ((before746, 746), (before760, 760)):
        if len(bitmap['tests']) != population or len(set(bitmap['tests'])) != population:
            raise ValueError('Wrong prior population')
    if len(latest['tests']) < 760 or len(set(latest['tests'])) != len(latest['tests']) or \
            latest['tests'][:760] != before760['tests'] or \
            before760['tests'][:746] != before746['tests']:
        raise ValueError('Not exact admitted prefix/unique population')
    if not before746['design'] == before760['design'] == latest['design']:
        raise ValueError('Compiled design differs')
    base, current = before760['metrics']['fsm'], latest['metrics']['fsm']
    if set(base) != set(current) or set(base) != set(before746['metrics']['fsm']):
        raise ValueError('FSM hierarchy differs')
    for scope, row in base.items():
        rows = [b['metrics']['fsm'][scope] for b in (before746, before760, latest)]
        if any((r['width'], r['checksum']) != (row['width'], row['checksum']) for r in rows):
            raise ValueError('FSM width/checksum differs: ' + scope)
        values = [int(r['bits'], 16) for r in rows]
        if any(v < 0 or v.bit_length() > row['width'] for v in values) or \
                values[0] & ~values[1] or values[1] & ~values[2]:
            raise ValueError('Bitmap overflow/lost hit: ' + scope)
    result = []
    for instance in priority['instances']:
        scope = instance['scope']
        rows = [b['metrics']['fsm'][scope] for b in (before746, before760, latest)]
        if instance['checksum'] != rows[1]['checksum']:
            raise ValueError('Priority compiled identity differs')
        bits = [format(int(r['bits'], 16), '0%db' % r['width']) for r in rows]
        missing = instance['missing']
        if len({x['raw_position'] for x in missing}) != len(missing) or \
                {x['raw_position'] for x in missing} != {i for i, b in enumerate(bits[1]) if b == '0'}:
            raise ValueError('Priority is not complete760 raw missing set')
        points = []
        for point in missing:
            position = point['raw_position']
            if bits[0][position] != '0':
                raise ValueError('760 missing point was already hit746')
            classification = ('NEW_RAW_HIT_AFTER760' if bits[2][position] == '1' else
                              'STILL_RAW_MISSING_NATIVE_QUALIFIED' if
                              point['already_native_qualified_exclusion'] else 'STILL_RAW_MISSING_NOT_QUALIFIED')
            points.append(dict(point, classification=classification))
        result.append(dict(scope=scope, checksum=instance['checksum'], points=points,
            already_hit746_positions=[i for i, b in enumerate(bits[0]) if b == '1'],
            new_hit746_to760_positions=[i for i, b in enumerate(bits[1])
                                       if b == '1' and bits[0][i] == '0']))
    return dict(status='POST760_RAW_FSM_HIERARCHY_COMPARISON_DIAGNOSTIC_ONLY',
        population=len(latest['tests']), native_qualification_population=745,
        qualified_exclusion_identities=155, official_percentages_recomputed=False,
        exclusions_applied=False, new_stimulus_approval=False, instances=result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--priority-seal', required=True)
    parser.add_argument('--bitmap', type=Path, required=True)
    parser.add_argument('--bitmap-seal', required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    output, bitmap = a.output.resolve(), a.bitmap.resolve()
    old.require(output.parent == old.life.OUT and not output.exists(), 'Fresh independent output only')
    priority = bound(PRIORITY, a.priority_seal)
    old.life.check(priority['pins'])
    paths = [Path(p) for p in priority['pins'] if p.endswith('/combined-bits.json')]
    old.require(len(paths) == 2, 'Expected exact746/760 source bitmaps')
    books = {len(json.loads(p.read_bytes())['tests']): p for p in paths}
    old.require(set(books) == {746, 760}, 'Different population source')
    result = compare(priority, bound(books[746], priority['pins'][str(books[746])]),
                     bound(books[760], priority['pins'][str(books[760])]), bound(bitmap, a.bitmap_seal))
    result['pins'] = dict(priority['pins'], **{str(PRIORITY): a.priority_seal,
        str(bitmap): a.bitmap_seal, str(Path(__file__).resolve()): old.life.digest(Path(__file__).resolve()),
        str(Path(__file__).with_name('test_compare_fsm_hierarchy_after760.py')):
            old.life.digest(Path(__file__).with_name('test_compare_fsm_hierarchy_after760.py'))})
    old.life.check(result['pins'])
    old.life.save(output, result)
    print(json.dumps(dict(output=str(output), seal=old.life.digest(output), population=result['population'])))


if __name__ == '__main__':
    main()
