#!/usr/bin/env python3
"""Read-only six-shape acceptance audit; writes only a new owned report directory."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
OLD = Path('/home/wangwy/fpga_runs/current_board_integration_final04/campaign')
NEW = HERE / 'final04_successor01'
SHAPES = [(16, 2, 2), (32, 2, 2), (64, 2, 2), (32, 4, 4), (64, 4, 4), (64, 8, 8)]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text())


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument('--out', type=Path, required=True)
    args = cli.parse_args()
    out = args.out.resolve()
    assert out.is_relative_to(HERE) and out != HERE and not out.exists()
    terminal = read(NEW / 'status.json')
    assert terminal['status'] == 'PASS' and terminal['returncode'] == 0 and terminal['pins_unchanged']
    for path, digest in read(NEW / 'plan.json')['pins'].items():
        assert sha(Path(path)) == digest, path
    ledger = read(OLD / 'image/image.json')
    for path, digest in ledger['files'].items():
        assert sha(Path(path)) == digest, path
    programs = read(HERE / 'matrix01/soc/programs.json')['programs']
    pins, findings = {}, []
    for index, (sew, regs, factor) in enumerate(SHAPES):
        name = f'extension_e{sew}_m{regs}_vf{factor}'
        run = OLD / 'extension-matrix' if index < 3 else NEW / 'replay'
        result = next(r for r in read(run / 'summary.json') if r['name'] == name)
        assert result['status'] == 'PASS' and result['returncode'] == 0
        test = run / 'tests' / name
        inputs = read(test / 'inputs.json')
        assert inputs['simv']['image_sha256'] == ledger['files']
        expected_sha = programs[name]['sha256']
        assert sha(test / 'input.elf') == inputs['binary']['sha256'] == expected_sha
        assert sha(OLD / 'extension-matrix/tests' / name / 'input.elf') == expected_sha
        text = (test / 'console.log').read_text()
        trials = [int(t) for t in re.findall(r'^EXTENSION_TRIAL (\d+)$', text, re.M)]
        assert trials == list(range(24)), (name, trials)
        for marker in programs[name]['pass_markers']:
            assert text.count(marker) == 1, (name, marker)
        assert 'Core Test *** SUCCESS *** (tohost = 0)' in text
        assert not re.search(r'EXTENSION_MATRIX_FAIL|BOARD_CASE_FAIL|\bSKIP\b|Fatal:|\bMISMATCH\b', text)
        stores = []
        with (test / 'commit_trace.csv').open() as stream:
            for row in csv.DictReader(stream):
                if row['event'] == 'retire' and row['insn'] in ('22858c27', '62858c27', 'e2858c27'):
                    stores.append(dict(cycle=int(row['cycle']), pc=row['pc'], trap=row['trap']))
        assert len(stores) == 24 and all(r['trap'] == '0' for r in stores), (name, stores)
        source = HERE / 'matrix01/prepared' / name
        assert sha(source / 'case.c') == '24b001f11095c57e3cbcaef840184997c6e0f5c647a193c1d37bff322f3e4824'
        assert len(read(source / 'original/cases.json')) == 24
        for path in (test / 'inputs.json', test / 'console.log', test / 'commit_trace.csv',
                     test / 'input.elf', source / 'case.c', source / 'original/cases.json',
                     run / 'summary.json'):
            pins[str(path)] = sha(path)
        findings.append(dict(name=name, status='PASS', elapsed_s=result['elapsed_s'],
            elf_sha256=expected_sha, trial_numbers=trials, readback_retirements=stores,
            data_bytes_compared=24*regs*128, guard_checks=48, vstart_checks=24,
            full_oracle_markers=programs[name]['pass_markers'], artifact_dir=str(test)))
        print(name, 'PASS24', result['elapsed_s'])
    out.mkdir()
    report = dict(status='PASS_6_SHAPES_144_SUBCASES_ON_FINAL04', shapes=findings,
        total_unique_subcases=144, total_readback_retirements=144,
        total_data_bytes_compared=sum(r['data_bytes_compared'] for r in findings),
        total_guard_checks=288, total_vstart_checks=144,
        pins=pins, image_ledger_sha256=sha(OLD / 'image/image.json'),
        successor_status_sha256=sha(NEW / 'status.json'), auditor_sha256=sha(Path(__file__)),
        scope='Six original shape ELFs across final04 and its same-image successor; not combined144, candidate02 or original Linux campaign',
        no_replay=True, prior_timeout_and_cancelled_records_preserved=True)
    (out / 'finding.json').write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    main()
