#!/usr/bin/env python3
"""Count accepted offloads inside UART trial markers, not timed-region IPC."""
import argparse
from collections import Counter
import json
from pathlib import Path
import re


def analyze(lines):
    trials, active = [], None
    for line in lines:
        if line.startswith('QUANT_GROUPED_BEGIN '):
            fields = dict(re.findall(r'(\w+)=(\w+)', line))
            index = int(fields['trial'])
            if active is not None or index != len(trials) or index >= 4:
                raise ValueError('Invalid trial sequence')
            if int(fields['enabled']) != (0, 1, 1, 0)[index]:
                raise ValueError('Expected ABBA')
            active = Counter()
        elif line.startswith('QUANT_GROUPED_RESULT '):
            fields = dict(re.findall(r'(\w+)=(\w+)', line))
            if active is None or int(fields['trial']) != len(trials):
                raise ValueError('Unmatched result')
            if int(fields['errors']) or int(fields['differences']):
                raise ValueError('Failed trial')
            if not active:
                raise ValueError('No accepted offload trace')
            trials.append(dict(active))
            active = None
        elif active is not None and line.startswith('[ARA_CONTRACT_TRACE]'):
            match = re.search(r'req=1/1 fire=1 id=\d+ insn=([0-9a-fA-F]+)', line)
            if match is None:
                continue
            insn = int(match[1], 16)
            category = {0x07: 'vector_load', 0x27: 'vector_store',
                        0x57: 'vector_arithmetic_or_config'}.get(insn & 127, 'other_offload')
            active[category] += 1
            if insn in (0xa3055457, 0xb287d257):
                active[f'insn_{insn:08x}'] += 1
    if active is not None or len(trials) != 4:
        raise ValueError('Incomplete four-trial trace')
    return {'scope': 'UART BEGIN/RESULT windows include setup and result checking; not timed-region IPC',
            'scalar_instruction_count_available': False, 'trials': trials}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log', type=Path)
    args = parser.parse_args()
    with args.log.open() as source:
        print(json.dumps(analyze(source), indent=2))
