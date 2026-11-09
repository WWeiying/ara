"""Strict successful-PV work/write checks for the experimental SoC image.

This supplements, not replaces, CPU/AXI protocol and numerical checks. It is
deliberately limited to the prepared-EW16 source wrapper: an unexpected layout
maintenance allocation is rejected, not silently grouped with the PV command.
"""
import csv
import hashlib
import re
from pathlib import Path


def require(condition, message):
    if not condition:
        raise ValueError(message)


def instruction(vd=0, vs2=8, rs1=10):
    require(vd in range(0, 29, 4) and vs2 in range(0, 25, 8) and rs1 in range(32),
            'Invalid PV register encoding')
    require(vd+4 <= vs2 or vs2+8 <= vd, 'PV reserved groups overlap')
    return (2 << 25) | (vs2 << 20) | (rs1 << 15) | (7 << 12) | (vd << 7) | 0x5b


def geometry(shape):
    dimension, heads, tokens = (shape[k] for k in ('dimension', 'heads', 'tokens'))
    require(dimension in (64, 96, 128) and heads in (1, 2) and tokens in range(1, 65),
            'Invalid expected PV shape')
    vd, vs2, rs1 = (shape.get(k, d) for k, d in (('vd', 0), ('vs2', 8), ('rs1', 10)))
    insn = instruction(vd, vs2, rs1)
    words = dimension//16
    control = tokens-1 | (heads-1) << 6 | {64: 0, 128: 1, 96: 2}[dimension] << 7
    slots = {vd*4+head*8+word for head in range(heads) for word in range(words)}
    return dict(shape, vd=vd, vs2=vs2, instruction=insn, words=words,
                control=control, slots=slots, writes=4*words*heads,
                fma_per_lane=words*heads*tokens)


def _fields(line, prefix, names):
    words = line[len(prefix):].split()
    require(len(words) == len(names), 'Missing/extra '+prefix+' fields')
    result = {}
    for word in words:
        require(re.fullmatch(r'[a-z_]+=[0-9]+', word) is not None,
                'Malformed '+prefix+' field')
        name, value = word.split('=')
        require(name not in result, 'Duplicate '+prefix+' field')
        result[name] = int(value)
    require(set(result) == set(names), 'Unexpected '+prefix+' fields')
    return result


PERF = ('seq vid control tokens words heads cycles error flags source_words seed_words '
        'coefficients value_words result_words final_acks row_reads').split()
LANE = 'lane vid tokens elements heads issued returned writes flags error'.split()


def performance(text, shapes):
    expected = [geometry(s) for s in shapes]
    records, lanes = [], {}
    for line in text.splitlines():
        if line.startswith('[RESIDENT_PV_LANE]'):
            r = _fields(line, '[RESIDENT_PV_LANE]', LANE)
            require(r['lane'] in range(4) and r['lane'] not in lanes,
                    'Duplicate/out-of-range PV lane completion')
            lanes[r['lane']] = r
        elif line.startswith('[RESIDENT_PV_PERF]'):
            r = _fields(line, '[RESIDENT_PV_PERF]', PERF)
            i = len(records)
            require(i < len(expected) and r['seq'] == i+1, 'Unexpected PV terminal sequence')
            s = expected[i]
            require(r['vid'] in range(8) and r['error'] == 0 and r['flags'] in range(32)
                    and r['cycles'] > 0, 'PV terminal failure/invalid status')
            for key in ('control', 'tokens', 'words', 'heads'):
                require(r[key] == s[key], 'PV terminal shape mismatch: '+key)
            counts = dict(source_words=96, seed_words=s['writes'], coefficients=4*s['tokens'],
                          value_words=4*s['tokens']*s['words'], result_words=s['writes'],
                          final_acks=s['writes'], row_reads=s['tokens']*s['words'])
            require(all(r[k] == v for k, v in counts.items()), 'PV payload/write work mismatch')
            require(set(lanes) == set(range(4)), 'Missing four-lane PV terminal evidence')
            flags = 0
            for lane in lanes.values():
                want = dict(vid=r['vid'], tokens=s['tokens'], elements=s['dimension']//4,
                            heads=s['heads'], issued=s['fma_per_lane'],
                            returned=s['fma_per_lane'], writes=s['writes']//4, error=0)
                require(all(lane[k] == v for k, v in want.items()) and lane['flags'] in range(32),
                        'PV lane shape/accepted/returned/write mismatch')
                flags |= lane['flags']
            require(flags == r['flags'], 'Command-local flags do not match lane union')
            records.append(dict(r, lanes=[lanes[l] for l in range(4)]))
            lanes = {}
        elif line.startswith('[RESIDENT_PV_'):
            raise ValueError('Unknown/malformed PV probe')
    require(len(records) == len(expected) and not lanes, 'Incomplete/extra PV completion probes')
    return records


def vector_writes(path, shapes):
    expected = [geometry(s) for s in shapes]
    required = set('cycle event arch_seq vid lane source insn use_vd vd eew vl vstart '
                   'addr be wdata nr_lanes vlen_bits'.split())
    configs, previous, allocated, live = 0, -1, [], None
    with Path(path).open(newline='') as stream:
        reader = csv.DictReader(stream)
        require(reader.fieldnames is not None and required <= set(reader.fieldnames),
                'Missing vector trace columns')
        for row in reader:
            require(None not in row and all(v is not None for v in row.values()), 'Malformed vector row')
            cycle = int(row['cycle'])
            require(cycle >= previous and (row['nr_lanes'], row['vlen_bits']) == ('4', '1024'),
                    'Vector cycle/configuration drift')
            previous = cycle
            event, insn = row['event'], int(row['insn'], 16)
            if event == 'config':
                require(configs == 0 and cycle == 0 and not allocated, 'Unexpected vector epoch')
                configs += 1
                continue
            require(configs == 1 and event in ('alloc', 'write', 'done'), 'Unknown event/reset epoch')
            if insn & 0x707f != 0x705b or insn >> 25 != 2:
                continue
            if event == 'alloc':
                require(live is None and len(allocated) < len(expected), 'Overlapping/extra PV allocation')
                s = expected[len(allocated)]
                require(insn == s['instruction'], 'PV encoding/register/rs1 mismatch')
                live = dict(arch_seq=int(row['arch_seq']), vid=int(row['vid']),
                            begin=cycle, writes={}, geometry=s)
                require(live['vid'] in range(8) and live['arch_seq'] > 0, 'Invalid PV allocation identity')
            else:
                require(live is not None and int(row['arch_seq']) == live['arch_seq'] and
                        int(row['vid']) == live['vid'] and insn == live['geometry']['instruction'],
                        'Unowned/misattributed PV write or completion')
            s = live['geometry']
            require(tuple(int(row[k]) for k in ('use_vd', 'vd', 'eew', 'vl', 'vstart')) ==
                    (1, s['vd'], 1, 256, 0), 'PV allocation/write metadata is not the internal contract')
            if event == 'write':
                lane, addr = int(row['lane']), int(row['addr'])
                require(lane in range(4) and addr in s['slots'] and int(row['source']) == 4
                        and int(row['be'], 16) == 255, 'PV write outside active result or normal LDU port')
                require(re.fullmatch(r'[0-9a-fA-F]{16}', row['wdata']) is not None,
                        'Unknown PV result data')
                key = (lane, addr)
                require(key not in live['writes'], 'Duplicate architectural PV write')
                live['writes'][key] = (cycle, row['wdata'])
            elif event == 'done':
                require(set(live['writes']) == {(l, a) for l in range(4) for a in s['slots']},
                        'PV completed before all actual VRF writes')
                require(all(c <= cycle for c, _ in live['writes'].values()), 'Write after PV completion')
                allocated.append(dict(arch_seq=live['arch_seq'], vid=live['vid'],
                                      allocation_cycle=live['begin'], completion_cycle=cycle,
                                      writes=len(live['writes']), instruction=f'{insn:08x}'))
                live = None
    require(configs == 1 and live is None and len(allocated) == len(expected),
            'Missing PV allocation/completion/write evidence')
    return allocated


def check_successful_pv(vector_path, text, shapes):
    require(bool(shapes), 'Expected successful PV work must not be empty')
    perf, vectors = performance(text, shapes), vector_writes(vector_path, shapes)
    for p, v in zip(perf, vectors):
        require(p['vid'] == v['vid'] and p['result_words'] == v['writes'],
                'Performance probes and actual write trace disagree')
    return dict(schema='resident-pv-successful-work-v1', commands=len(shapes),
                pv_terminals=perf, actual_vector_writes=vectors,
                fma_microoperations=sum(4*geometry(s)['fma_per_lane'] for s in shapes),
                vector_sha256=hashlib.sha256(Path(vector_path).read_bytes()).hexdigest(),
                numerical_checked=False, protocol_checked=False,
                scope='Prepared EW16 source, successful commands only; full output/CSR checked separately')
