#!/usr/bin/env python3
"""Frozen-image QBS short-block attribution and paired regression."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--simv', type=Path, required=True)
    p.add_argument('--capture', type=Path, required=True)
    p.add_argument('--controls', type=Path, required=True)
    p.add_argument('--compare', type=Path)
    a = p.parse_args()
    out = a.output.resolve()
    out.mkdir(parents=True, exist_ok=False)
    simv = a.simv.resolve(strict=True)
    sources = list((ROOT / 'hardware/src/vlsu/qbs').glob('*.sv'))
    sources += [ROOT / 'verification/qbs/qbs_engine_tb.sv',
                ROOT / 'verification/qbs/qbs_command_vectors.c',
                ROOT / 'hardware/include/qbs_pkg.sv', Path(__file__)]
    hashes = {str(f.relative_to(ROOT)): digest(f) for f in sources}
    image = [simv, *sorted((simv.parent / 'simv.daidir').rglob('*.so'))]
    if len(image) < 2:
        raise ValueError('Missing simulator shared libraries')
    image_hashes = {str(f): digest(f) for f in image}
    state = dict(state='running', sources=hashes, image=image_hashes, cases={})

    def save():
        tmp = out / 'status.json.partial'
        tmp.write_text(json.dumps(state, indent=2) + '\n')
        tmp.replace(out / 'status.json')

    def command(argv, cwd, log):
        with log.open('w') as stream:
            subprocess.run(argv, cwd=cwd, stdout=stream,
                           stderr=subprocess.STDOUT, timeout=240, check=True)

    try:
        cases = [('suite', ROOT / 'verification/qbs/qbs_command_vectors.txt', 0),
                 ('suite_gap2', ROOT / 'verification/qbs/qbs_command_vectors.txt', 2)]
        for m in (1, 4, 8):
            name = f'q8_m{m}'
            directory = out / name
            directory.mkdir()
            capture = a.capture / ('decode' if m == 1 else 'prefill') / 'operators/blk_0_attn_q_weight'
            weight = json.loads((capture / 'weight_q8_0.json').read_text())
            k, n = weight['shape'][:2]
            for filename in ('weight_q8_0.bin', 'activation_f32.bin', 'output_f32.bin',
                             'weight_q8_0.json', 'activation_f32.json', 'output_f32.json'):
                state.setdefault('capture_hashes', {})[str(capture / filename)] = digest(capture / filename)
            vector = directory / 'input.vectors'
            command([str(ROOT / 'verification/qbs/qbs_command_vectors'), str(vector),
                     '--real', 'q8_0', str(capture), str(n), str(k), '0', str(m),
                     '0', str(16 if m == 8 else 32)], ROOT, directory / 'reference.log')
            cases.append((name, vector, 0))
        for name in ('q4_K_decode_m1n32', 'q6_K_decode_m1n32',
                     'q4_m4n32', 'q6_m4n32', 'q4_m8n16', 'q6_m8n16'):
            cases.append((name, a.controls / name / 'input.vectors', 0))
        save()
        for name, vector, gap in cases:
            directory = out / name
            directory.mkdir(exist_ok=True)
            copy = directory / 'input.vectors'
            if vector.resolve() != copy.resolve():
                copy.write_bytes(vector.read_bytes())
            state['current'] = name
            save()
            argv = [str(simv), '-l', 'run.log', '+QBS_COMMAND_VECTOR_FILE=' + str(copy),
                    f'+QBS_RESPONSE_GAP={gap}', '+QBS_FP_PROBE']
            if not name.startswith('suite'):
                argv += ['+QBS_FUNCTIONAL_ONLY', '+QBS_FP_TRACE=' + str(directory / 'fp.csv')]
            command(argv, directory, directory / 'console.log')
            log = (directory / 'run.log').read_text()
            if 'QBS engine PASS:' not in log or re.search(r'Fatal:|Error:', log):
                raise ValueError(f'No clean PASS: {name}')
            rows = {i: dict(cycles=int(c)) for i, c in re.findall(
                r'QBS end-to-end case (\d+) PASS .* cycles=(\d+)', log)}
            if not rows:
                raise ValueError(f'No checked cases: {name}')
            for kind, expression in (
                    ('probe', r'QBS FP probe case=(\d+) (.*)'),
                    ('traffic', r'QBS traffic case=(\d+) (.*)')):
                for i, values in re.findall(expression, log):
                    rows[i][kind] = {k: int(v) for k, v in re.findall(r'(\w+)=(\d+)', values)}
            state['cases'][name] = dict(vector_sha256=digest(copy), rows=rows, status='PASS')
            save()
            print(name, rows, flush=True)
        if a.compare:
            previous = json.loads((a.compare / 'status.json').read_text())
            assert previous['state'] == 'passed'
            assert previous['cases'].keys() == state['cases'].keys()
            comparison = {}
            for name, old in previous['cases'].items():
                new = state['cases'][name]
                assert old['vector_sha256'] == new['vector_sha256'], name
                assert old['rows'].keys() == new['rows'].keys(), name
                comparison[name] = {}
                for i, before in old['rows'].items():
                    after = new['rows'][i]
                    for key in ('weight', 'activation', 'payload', 'ranges', 'dot'):
                        if 'traffic' in before:
                            assert before['traffic'][key] == after['traffic'][key], (name, key)
                    comparison[name][i] = dict(before=before['cycles'], after=after['cycles'])
            state['comparison'] = comparison
        assert all(digest(f) == hashes[str(f.relative_to(ROOT))] for f in sources)
        assert all(digest(Path(f)) == h for f, h in image_hashes.items())
        assert all(digest(Path(f)) == h for f, h in state['capture_hashes'].items())
        state['state'] = 'passed'
    except Exception as error:
        state.update(state='failed', error=repr(error))
        raise
    finally:
        save()


if __name__ == '__main__':
    main()
