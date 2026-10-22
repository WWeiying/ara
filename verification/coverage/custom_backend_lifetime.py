"""Request-identity-bound custom backend lifetime checks, independent of CVX handshakes."""
import csv
from pathlib import Path


def require(ok, message):
    if not ok:
        raise ValueError(message)


def csv_rows(path):
    with Path(path).open(newline="") as stream:
        yield from csv.DictReader(stream)


def custom_write_lifetimes(vector_path, custom_starts):
    instructions = dict(custom_starts)
    groups, live, last = {}, {}, 0
    for row in csv_rows(vector_path):
        cycle = int(row['cycle'])
        require(cycle >= last, 'vector cycles regress')
        last = cycle
        seq = int(row['arch_seq'])
        if row['event'] == 'config':
            continue
        if seq not in instructions:
            require(int(row['insn'], 16) & 127 != 0x5b, 'unbound custom backend event')
            continue
        require(int(row['insn'], 16) == instructions[seq], 'custom vector identity differs')
        key = (seq, int(row['vid']))
        event = row['event']
        if event == 'alloc':
            require(key not in groups, 'duplicate custom backend allocation')
            require(not any(k[0] == seq for k in groups), 'extra custom backend group')
            require(key[1] not in live, 'custom VID reused before completion')
            live[key[1]] = seq
            groups[key] = dict(start=cycle, done=None,
                metadata=tuple(row[f] for f in ('use_vd', 'vd', 'eew', 'vl', 'vstart')))
        else:
            require(key in groups, 'custom vector event without allocation')
            group = groups[key]
            if event == 'done':
                require(group['done'] is None, 'duplicate custom backend completion')
                require(tuple(row[f] for f in ('use_vd', 'vd', 'eew', 'vl', 'vstart')) ==
                        group['metadata'], 'custom completion metadata differs')
                group['done'] = cycle
                del live[key[1]]
            elif event == 'write':
                # The monitor may print completion before the final same-cycle write.
                require(cycle >= group['start'] and
                        (group['done'] is None or cycle == group['done']),
                        'VRF write outside custom backend lifetime')
            else:
                require(False, 'unknown custom vector event')
    require({k[0] for k in groups} == set(instructions), 'custom backend allocation missing')
    require(all(g['done'] is not None for g in groups.values()),
            'custom backend completion missing')
