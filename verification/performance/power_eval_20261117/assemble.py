#!/usr/bin/env python3
"""Select already audited firmware, without modifying original cases or pins."""
import argparse
import importlib.util
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
OPERATORS = ROOT / 'verification/performance/operator_eval_20261115'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--attention', type=Path)
    p.add_argument('--attention-akv', type=Path)
    p.add_argument('--attention-rvv', type=Path)
    p.add_argument('--q8-successor', type=Path)
    a = p.parse_args()
    output = a.output.resolve()
    if output.exists() or output.parent != OUT:
        raise ValueError('Fresh owned output required')
    spec = importlib.util.spec_from_file_location('power_precheck', HERE / 'precheck.py')
    worker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(worker)
    projection = OUT / 'operator_projection_real_prepare_20261115_release_01'
    records = json.loads((projection / 'manifest.json').read_text())['cases']
    cases = [c for c in records if c['id'] in (
        'qwen3_real_decode_attn_q_m1_n64_native', 'qwen3_real_decode_attn_q_m1_n64_rvv_x32')]
    if len(cases) != 2:
        raise ValueError('Missing real decode pair')
    for mode in ('native', 'x32'):
        build = OUT / ('operator_qbs_prepare_20261115_q4_m4_' + mode + '_01')
        manifest = json.loads((build / 'manifest.json').read_text())['cases']
        if len(manifest) != 1:
            raise ValueError('M4 manifest')
        c = manifest[0]
        c['checker'] = ['/usr/bin/python3', '-B', str(OPERATORS / 'qbs/check_vcsr_v3.py'),
                        '--fresh', '--build', str(build), '--log', '{log}',
                        '--commit', '{run}/commit.csv', '--output', '{result}']
        cases.append(c)
    legacy = OUT / 'power_legacy_q8_prepare_20261117_01'
    legacy_cases = json.loads((legacy / 'manifest.json').read_text())['cases']
    if a.q8_successor:
        modern = json.loads(a.q8_successor.resolve().read_text())['cases']
        if len(modern) != 1 or modern[0]['id'] != 'legacy_q8_qbs_sdk_v2_successor':
            raise ValueError('Expected reviewed descriptor-v2 Q8 successor')
        legacy_cases = [c for c in legacy_cases if c['id'] == 'legacy_q8_rvv'] + modern
    cases += legacy_cases
    separate_attention = bool(a.attention_akv or a.attention_rvv)
    if separate_attention:
        if not (a.attention_akv and a.attention_rvv) or a.attention:
            raise ValueError('Supply both separate Attention manifests, without combined manifest')
        for path in (a.attention_akv, a.attention_rvv):
            record = json.loads(path.resolve().read_text())['cases']
            if len(record) != 1:
                raise ValueError('Single-mode Attention required')
            cases += record
    if a.attention:
        attention = json.loads(a.attention.resolve().read_text())
        cases += attention['cases']
    expected = 8 if a.attention or separate_attention else 6
    if len(cases) != expected:
        raise ValueError('Unexpected pair count')
    pins = {}
    for c in cases:
        source_pins = Path(c['source_pins'])
        worker.verify(json.loads(source_pins.read_text()))
        if worker.sha(c['elf']) != c['elf_sha256']:
            raise ValueError('ELF changed')
        pins[str(source_pins)] = worker.sha(source_pins)
    output.mkdir()
    for side in ('native', 'rvv'):
        selected = [c for c in cases if
                    ('rvv' in c['id']) == (side == 'rvv')]
        if len(selected) != expected // 2:
            raise ValueError('Pair side classification')
        worker.save(output / (side + '.json'), dict(
            scope=f'{expected // 2} representative power-program RTL prechecks, ' + side,
            cases=selected, gate_simulation_started=False))
    worker.save(output / 'input-inventory.json', pins)
    print(output)


if __name__ == '__main__':
    main()
