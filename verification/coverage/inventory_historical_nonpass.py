"""Inventory recorded non-PASS outcomes; never infer RTL bugs or admission."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def collect(root):
    records, pins = [], {}
    for path in sorted(root.glob('*/all-outcomes.json')):
        data = path.read_bytes()
        rows = json.loads(data)
        if not isinstance(rows, list):
            raise ValueError('Expected outcome list: ' + str(path))
        pins[str(path.absolute())] = hashlib.sha256(data).hexdigest()
        for row in rows:
            status = row.get('status')
            if status in (None, 'PASS'):
                continue
            records.append(dict(name=row.get('name'), elf_sha256=row.get('elf_sha256'),
                                status=status, evidence=str(path.absolute())))
    # Old-image extensions store per-case outcomes in status.json instead.
    for path in sorted(root.glob('gap*-old-image-*/status.json')):
        data = path.read_bytes()
        state = json.loads(data)
        pins[str(path.absolute())] = hashlib.sha256(data).hexdigest()
        for name, row in state.get('cases', {}).items():
            if row.get('status') in (None, 'PASS'):
                continue
            records.append(dict(name=name, elf_sha256=None, status=row['status'],
                                reason=row.get('reason'), directory=row.get('directory'),
                                evidence=str(path.absolute())))
    grouped = {}
    for row in records:
        key = row['name'], row['elf_sha256']
        grouped.setdefault(key, []).append(row)
    return dict(status='HISTORICAL_NONPASS_RECORDS_NOT_UNRESOLVED_BUG_COUNT',
                scope=['one-level all-outcomes.json', 'gap*-old-image-*/status.json cases'],
                limitations=['Not every historical evidence schema is scanned.',
                             'Later PASS and image identity require separate reconciliation.',
                             'Missing ELF hashes do not establish binary identity.',
                             'TIMEOUT alone does not establish an RTL bug.'],
                record_count=len(records), grouped_name_elf_count=len(grouped),
                recorded_status_counts=dict(Counter(r['status'] for r in records)),
                groups=[dict(name=key[0], elf_sha256=key[1], records=rows)
                        for key, rows in grouped.items()], input_sha256=pins,
                coverage_inputs_changed=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Fresh output required')
    result = collect(args.root)
    for path, expected in result['input_sha256'].items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError('Input changed during inventory: ' + path)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
        stream.write('\n')
    print(json.dumps({k: result[k] for k in
                     ('status', 'record_count', 'grouped_name_elf_count', 'recorded_status_counts')}))


if __name__ == '__main__':
    main()
