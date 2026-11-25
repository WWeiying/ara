#!/usr/bin/env python3
"""Successor host layout audit; never modifies a prepared/sealed build."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

sys.dont_write_bytecode = True
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit_layout(profile, rows, kb, original, packed):
    # Independent field order from the C block_*x32 ABI, not the packer's table.
    if profile == 1:
        block_bytes = 144
        fields = ((0,2,2),(2,2,2),(4,12,1),(16,128,1))
    elif profile == 2:
        block_bytes = 210
        fields = ((208,2,2),(192,16,1),(0,128,1),(128,64,1))
    else:
        raise ValueError('Unqualified x32 profile')
    if rows % 32 or len(original) != rows*kb*block_bytes or len(packed) != len(original):
        raise ValueError('x32 dimensions')
    cursor = 0
    recovered = bytearray(len(original))
    for group in range(rows//32):
        for block in range(kb):
            for offset,size,width in fields:
                for item in range(size//width):
                    for lane in range(32):
                        dst = ((group*32+lane)*kb+block)*block_bytes+offset+item*width
                        recovered[dst:dst+width] = packed[cursor:cursor+width]
                        cursor += width
    if cursor != len(packed) or recovered != original:
        raise ValueError('x32 ABI does not recover every original weight byte')
    return dict(profile=profile, rows=rows,k_blocks=kb, bytes_checked=len(original),
                packed_sha256=hashlib.sha256(packed).hexdigest(),
                recovered_original_bit_exact=True)


def audit(directory):
    directory = Path(directory).resolve()
    build_path = directory / 'build.json'
    build = json.loads(build_path.read_text())
    pins_path = Path(build['source_pins'])
    if digest(pins_path) != build['source_pins_sha256']:
        raise ValueError('Build pin inventory changed')
    pins = json.loads(pins_path.read_text())
    for path,sha in pins.items():
        if digest(path) != sha:
            raise ValueError('Prepared input changed: '+path)
    if digest(build['elf']) != build['elf_sha256']:
        raise ValueError('Prepared ELF changed')
    case = build['case']
    data = directory / 'data'
    result = audit_layout(case['profile'],case['n'],8,
                          (data/'weights_row.bin').read_bytes(),(data/'weights_x32.bin').read_bytes())
    source = next(Path(p) for p in pins if p.endswith('/apps/llama_q4k_repack_bench/repack_kernels.c'))
    packed_header = source.with_name('repack_kernels.h')
    result.update(build=str(build_path), build_sha256=digest(build_path),
        elf_sha256=build['elf_sha256'],baseline_kind=case['baseline_kind'],
        primary_eligible=case['primary_eligible'],
        kernel_sha256=digest(source), kernel_header_sha256=digest(packed_header),
        numerical_check='Run-time independent qbs_ref tolerance check still required; host layout audit is not RVV execution')
    inherited = {**pins,str(build_path):digest(build_path),str(pins_path):digest(pins_path)}
    return result,inherited


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build', action='append', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    out = a.output.resolve()
    if out.parent != OUT or not re.fullmatch(r'operator_qbs_prepare_20261115_[A-Za-z0-9_]+',out.name) or out.exists():
        raise ValueError('Fresh owned output required')
    out.mkdir()
    pins = {str(Path(__file__).resolve()):digest(__file__)}
    results = []
    for build in a.build:
        result,inherited = audit(build)
        results.append(result)
        for path,sha in inherited.items():
            if path in pins and pins[path] != sha:
                raise ValueError('Inconsistent inherited identity')
            pins[path] = sha
    for path,sha in pins.items():
        if digest(path) != sha:
            raise ValueError('Host-audit input drift: '+path)
    (out/'source-pins.json').write_text(json.dumps(pins,indent=2,sort_keys=True)+'\n')
    report = dict(state='HOST_LAYOUT_AUDIT_PASS_NOT_EXECUTED',rtl_executed=False,
                  performance_measured=False,builds=results,
                  source_pins_sha256=digest(out/'source-pins.json'))
    (out/'report.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
    print(str(out/'report.json'))


if __name__ == '__main__':
    main()
