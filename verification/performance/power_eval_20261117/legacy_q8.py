#!/usr/bin/env python3
"""Freeze/check original Qwen2.5 Q8_0 specimens; no source regeneration."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent / 'ara_dsa_signoff_integration/verification/out'


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def prepare(output):
    require(output.parent == OUT and not output.exists(), 'Fresh signoff output required')
    output.mkdir()
    pair, cases = {}, []
    for mode in ('rvv', 'qbs'):
        name = 'llama_qwen25_q8_0_decode_attn_q_' + mode
        source = ROOT / 'apps' / name / 'generated'
        meta = json.loads((source / 'provenance.json').read_text())
        require((meta['k'], meta['rows'], meta['inputs']) == (896, 256, 1), 'Legacy shape')
        work = output / mode
        work.mkdir()
        shutil.copyfile(ROOT / 'apps/bin' / name, work / 'operator.elf')
        elf = (work / 'operator.elf').read_bytes()
        require(elf[:6] == b'\x7fELF\x02\x01', 'Not RV64 little-endian ELF')
        require(struct.unpack_from('<H', elf, 18)[0] == 243, 'Not RISC-V')
        phoff = struct.unpack_from('<Q', elf, 32)[0]
        phsize, phnum = struct.unpack_from('<HH', elf, 54)
        for i in range(phnum):
            ptype, _, _, va, _, filesz, memsz, _ = struct.unpack_from('<IIQQQQQQ', elf, phoff+i*phsize)
            if ptype == 1:
                require(0x80000000 <= va <= va+memsz <= 0x80100000 and filesz <= memsz,
                        'ELF does not fit mapped 1 MiB L2')
        for filename, entry in meta['tensors'].items():
            p = source / filename
            require(sha(p) == entry['sha256'] and p.stat().st_size == entry['bytes'], 'Capture drift')
            shutil.copyfile(p, work / filename)
            if filename in ('activation_f32.bin', 'embedded_weight.bin', 'golden_f32.bin'):
                require(p.read_bytes() in elf, 'Specimen lacks exact captured bytes: ' + filename)
        shutil.copyfile(source / 'provenance.json', work / 'provenance.json')
        shutil.copyfile(__file__, work / 'legacy_q8.py')
        pins = {str(p): sha(p) for p in work.iterdir() if p.is_file()}
        (work / 'source-pins.json').write_text(json.dumps(pins, indent=2)+'\n')
        pair[mode] = {n: sha(work/n) for n in ('activation_f32.bin', 'source_weight.bin', 'golden_f32.bin')}
        cases.append(dict(id='legacy_q8_' + mode, category='projection',
            elf=str(work/'operator.elf'), elf_sha256=sha(work/'operator.elf'),
            source_pins=str(work/'source-pins.json'), timeout_seconds=10800,
            plusargs=['+QBS_PERF'] if mode == 'qbs' else [],
            checker=['/usr/bin/python3', '-B', str(work/'legacy_q8.py'), 'check', '--output',
                     '{result}', '--build', str(work), '--log', '{log}', '--mode', mode]))
    require(pair['rvv'] == pair['qbs'], 'Legacy pair input/reference mismatch')
    (output/'manifest.json').write_text(json.dumps(dict(scope='Original Qwen2.5 Q8_0 specimens',
                                                       cases=cases, paired_data_sha256=pair), indent=2)+'\n')


def check(build, log, output, mode):
    pins = json.loads((build/'source-pins.json').read_text())
    for p, expected in pins.items():
        require(sha(p) == expected, 'Frozen legacy input changed')
    text = log.read_text()
    case = 'q8_0_decode_attn_q_' + mode
    prefix = 'QBS_REAL_BENCH' if mode == 'qbs' else 'REAL_BENCH'
    lines = re.findall(r'^'+prefix+r' case='+case+r' .+$', text, re.M)
    require(len(lines) == 1 and text.count('Core Test *** SUCCESS ***') == 1, 'Missing/duplicate completion')
    fields = {}
    for token in lines[0].split()[1:]:
        key, val = token.split('=', 1)
        require(key not in fields, 'Duplicate benchmark field')
        fields[key] = val
    require(fields['result'] == 'PASS' and fields['mismatches'] == '0', 'Target numerical check failed')
    require(all(fields[k] == v for k, v in dict(k='896', rows='256', inputs='1', outputs='256').items()),
            'Workload shape mismatch')
    require(int(fields['compute_cycles']) > 0 and int(fields['matmul_cycles']) > 0, 'Missing compute ROI')
    require(not re.search(r'(?mi)^\s*(?:Error[-:]|Fatal:)|Assertion failed|\bFAILED\b', text), 'Simulation error')
    for key in ('max_abs_bits', 'max_rel_bits'):
        value = struct.unpack('<f', struct.pack('<I', int(fields[key], 0)))[0]
        require(value >= 0 and value < float('inf'), 'Nonfinite error metric')
    if mode == 'qbs':
        for key in ('qbs_status', 'execution_status'):
            if key in fields:
                require(fields[key] == '0', 'QBS status')
    require(not output.exists(), 'Do not overwrite previous result')
    output.write_text(json.dumps(dict(state='PASS', benchmark=fields, log_sha256=sha(log),
        contract='Legacy ELF checks all 256 outputs against embedded model golden with original tolerance; not bit-exact ordered QBS reference',
        scalar_model_reference_sha256=pins[str(build/'golden_f32.bin')]), indent=2)+'\n')


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('action', choices=('prepare', 'check'))
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--build', type=Path)
    p.add_argument('--log', type=Path)
    p.add_argument('--mode', choices=('rvv', 'qbs'))
    a = p.parse_args()
    if a.action == 'prepare':
        prepare(a.output.resolve())
    else:
        check(a.build.resolve(), a.log.resolve(), a.output.resolve(), a.mode)


if __name__ == '__main__':
    main()
