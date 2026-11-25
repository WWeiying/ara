#!/usr/bin/env python3
"""Audit the two captured FFN inputs; this is not an operator benchmark."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

DEFAULT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
CAPTURES = {
    'decode': ('e2e_decode_capture_20261106_01', 1,
               'REAL_QWEN3_DECODE_CAPTURED_NOT_BENCHMARKED',
               'd4fa6452622611321f7320df8a0a01f245852d1a7944289032a6a24b147f3c56',
               'd55e84abd22b1ff3618a0fd15b9ec04d0a5d72da5683315c1633a4b45c33c574'),
    'prefill': ('e2e_ffn_capture_20261106_02', 4,
                'REAL_QWEN3_FFN_CAPTURED_NOT_BENCHMARKED',
                'a620f3785622e4d3715640f291fd1dc7111cf2c9e9cd442183f97ed037819c18',
                'e4a6c91d4a388f8e5e48714d396e7b4a947c4fb809caf5575445d7b8b07de78f'),
}
WEIGHTS = {
    'ffn_gate': 'd1439d152e05cc683e0437173f6a7678500f0521d7d4e87f14777caae7ca1962',
    'ffn_up': 'b64a974a91ad53777590cf936b848da2bf8bea3a2d9fc52a035532ba7cd073c7',
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def audit(root, name):
    dirname, rows, state, activation_hash, pins_hash = CAPTURES[name]
    directory = root / dirname
    result = json.loads((directory / 'result.json').read_text())
    require(result['state'] == state and result['post_pins_match'] is True and
            result['performance_measured'] is False, 'capture status')
    require(result['activation']['rows'] == rows and
            'ffn_norm-0' in result['activation']['sources'], 'activation metadata')
    require(result['source_pins_sha256'] == pins_hash and
            sha((directory / 'source-pins.json').read_bytes()) == pins_hash, 'source pins drift')
    activation = (directory / 'ffn_norm-0_f32.bin').read_bytes()
    require(len(activation) == rows * 2048 * 4 and sha(activation) == activation_hash,
            'activation size or digest')
    require(all(math.isfinite(x[0]) for x in struct.iter_unpack('<f', activation)),
            'nonfinite activation')
    weights = {}
    for operator, expected_hash in WEIGHTS.items():
        entries = [w for w in result['weights'] if w['tensor'] == f'blk.0.{operator}.weight']
        require(len(entries) == 1, operator + ' metadata count')
        w = entries[0]
        require((w['type'], w['k'], w['full_n'], w['captured_n'], w['file'], w['sha256']) ==
                ('Q4_K', 2048, 6144, 128, operator + '.bin', expected_hash), operator + ' metadata')
        data = (directory / w['file']).read_bytes()
        require(len(data) == 128 * 8 * 144 and sha(data) == expected_hash, operator + ' bytes')
        weights[operator] = sha(data)
    require(weights['ffn_gate'] != weights['ffn_up'], 'identical weights')
    return {'directory': str(directory), 'rows': rows, 'k': 2048, 'captured_n': 128,
            'full_n': 6144, 'activation_sha256': sha(activation), 'weights': weights}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=DEFAULT)
    args = parser.parse_args()
    result = {name: audit(args.root, name) for name in CAPTURES}
    result['scope'] = 'Capture integrity only; no gold generation, command execution, reuse or timing verified'
    result['m1_selection'] = 'decode, first and only row, both captured weight slices, K2048 N128'
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
