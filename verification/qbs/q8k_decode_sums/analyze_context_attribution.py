#!/usr/bin/env python3
"""Join lookahead decisions to runtime tensor records without inferring speedup."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path


def fields(line):
    pairs = [word.split('=', 1) for word in line.split()[1:]]
    if any(len(pair) != 2 for pair in pairs):
        raise ValueError('Malformed trace record')
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError('Duplicate trace field')
    return result


def address(value):
    return 0 if value in ('(nil)', '0x0') else int(value, 16)


def analyze(text):
    mode = None
    identities, decisions = {}, []
    for line in text.splitlines():
        if line.startswith('Q8K_MODEL_BEGIN '):
            mode = int(fields(line)['enabled'])
            if mode not in (0, 1):
                raise ValueError('Unknown preparation mode')
        elif line.startswith('GGML_RISCV_QBS_LIFETIME '):
            if mode is None:
                raise ValueError('Unscoped tensor identity')
            row = fields(line)
            key = (mode, int(row['graph_epoch']), address(row['op_id']))
            if key in identities:
                raise ValueError('Repeated node identity in one graph epoch')
            identities[key] = row
        elif line.startswith('GGML_RISCV_QBS_CONTEXT_LOOKAHEAD '):
            if mode is None:
                raise ValueError('Unscoped lookahead')
            row = fields(line)
            if row['decision'] not in ('0', '1'):
                raise ValueError('Invalid decision')
            decisions.append((mode, row))
    if not decisions:
        raise ValueError('No attribution records')
    counts, examples = Counter(), {}
    joined = 0
    for mode, row in decisions:
        epoch = int(row['graph_epoch'])
        origin = identities.get((mode, epoch, address(row['current'])))
        examined = identities.get((mode, epoch, address(row['examined'])))
        if origin is not None:
            if address(origin['source_id']) != address(row['source']) or address(origin['source_data']) != address(row['source_data']):
                raise ValueError('Source identity drift')
            joined += 1
        source, write = address(row['source_data']), address(row['write_data'])
        source_bytes, write_bytes = int(row['source_bytes']), int(row['write_bytes'])
        if min(source_bytes, write_bytes) < 0:
            raise ValueError('Negative extent')
        overlap = bool(source and write and source_bytes and write_bytes and
                       write < source + source_bytes and source < write + write_bytes)
        consumer = origin['weight'] if origin is not None else '<not-quantized-or-unresolved>'
        key = (mode, row['reason'], row['decision'], consumer, row['op'], overlap)
        counts[key] += 1
        examples.setdefault(key, dict(current_index=int(row['current_index']),
            examined_index=int(row['examined_index']), graph_epoch=epoch,
            current_node=row['current'], examined_node=row['examined'],
            examined_weight=examined['weight'] if examined is not None else None,
            source_data=row['source_data'], source_bytes=source_bytes,
            write_data=row['write_data'], write_bytes=write_bytes))
    return dict(attribution_records=len(decisions), joined_quantized_nodes=joined,
        unresolved_records=len(decisions)-joined, performance_measured=False,
        note='Unresolved nodes can be context-reuse consumers with no quantization record. '
             'Range overlap is diagnostic, not authorization to bypass a barrier.',
        groups=[dict(mode=k[0], reason=k[1], decision=int(k[2]), weight=k[3],
                     examined_op=k[4], range_overlap=k[5], count=n, example=examples[k])
                for k, n in sorted(counts.items())])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--log', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    raw = args.log.read_bytes()
    raw = raw[:raw.rfind(b'\n')+1]
    result = analyze(raw.decode())
    result.update(source=str(args.log.resolve()), snapshot_sha256=hashlib.sha256(raw).hexdigest(),
                  scope='Diagnostic snapshot; functional/model acceptance is checked separately')
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'snapshot.log').write_bytes(raw)
    (args.output / 'result.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
