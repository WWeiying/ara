#!/usr/bin/env python3
"""Require the complete, disjoint 464-case FP16 matrix in actual PASS logs."""
import argparse
import hashlib
import json
from pathlib import Path
import re


def audit(campaign):
    observed = set()
    details = []
    for shard in range(32):
        name = 'extra-rvv-repair_fp16_int8_s' + str(shard)
        record = json.loads((campaign / 'outcomes' / (name + '.json')).read_text())
        if record['status'] != 'PASS' or not record['passed_only']:
            raise ValueError(f'{name}: not a complete audited PASS')
        paths = [p for p in record['files'] if p.endswith('/console.log')]
        if len(paths) != 1:
            raise ValueError('expected one console')
        data = Path(paths[0]).read_bytes()
        if hashlib.sha256(data).hexdigest() != record['files'][paths[0]]:
            raise ValueError('console changed')
        text = data.decode(errors='replace')
        masks = re.findall(r'^vfncvt_int8_ids:([ 0-9a-f]+)$', text, re.M)
        counts = re.findall(r'^vfncvt_int8: (\d+) cases, VLEN=(\d+)$', text, re.M)
        totals = re.findall(r'^vfncvt_int8_checks: ordinals=(\d+) bytes=(\d+) active=(\d+) csr=(\d+)$', text, re.M)
        if len(masks) != 1 or len(counts) != 1 or len(totals) != 1:
            raise ValueError(f'{name}: missing or repeated matrix summary')
        bits = [int(word, 16) for word in masks[0].split()]
        ids = {64 * word + bit for word, value in enumerate(bits)
               for bit in range(64) if value & (1 << bit)}
        expected = {i for i in range(464) if i % 32 == shard}
        if ids != expected or ids & observed or int(counts[0][0]) != len(ids):
            raise ValueError(f'{name}: case-set mismatch')
        if int(counts[0][1]) != 1024 or int(totals[0][0]) != 464 or int(totals[0][3]) != 3 * len(ids):
            raise ValueError(f'{name}: incomplete CSR checks or wrong geometry')
        observed |= ids
        details.append({'shard': shard, 'cases': len(ids), 'console': paths[0]})
    if observed != set(range(464)):
        raise ValueError('incomplete matrix union')
    return {'status': 'PASS', 'cases': len(observed), 'shards': details}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--campaign', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    result = audit(args.campaign)
    with args.output.open('x') as stream:
        json.dump(result, stream, indent=2)
    print('FP16 executed union: PASS, 464 cases, 32 disjoint shards')
