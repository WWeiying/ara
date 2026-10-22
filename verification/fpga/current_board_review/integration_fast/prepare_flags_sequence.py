#!/usr/bin/env python3
"""Prepare a separate nonreset flag-ownership regression; never edit old inputs."""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent / 'integration'
sys.path.insert(0, str(BASE))
import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--parent', type=Path, default=Path('/tmp/current-board-integration-fast01/prepared'))
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out = args.out.resolve()
    original = prepare.check(args.parent)
    args.out.mkdir(parents=True, exist_ok=False)
    target = args.out / 'prepared'
    shutil.copytree(args.parent, target, copy_function=shutil.copyfile)
    source = target / 'extensions.c'
    text = source.read_text()
    begin, end = '#elif REPLAY_EXT == 3\n', '#elif REPLAY_EXT == 4\n'
    if text.count(begin) != 1 or text.count(end) != 1:
        raise ValueError('unexpected parent structure')
    source.write_text(text[:text.index(begin)] + begin +
                      (HERE / 'reduction_flags_sequence.c').read_text() + '\n' + text[text.index(end):])
    provenance = dict(original)
    provenance['sequence_test'] = dict(
        parent_sha256=prepare.sha(args.parent / 'provenance.json'),
        source_sha256=prepare.sha(HERE / 'reduction_flags_sequence.c'),
        scope='new directed nonreset sequence; not original FPGA program acceptance')
    provenance['files'] = {str(p.relative_to(target)): prepare.sha(p)
                           for p in target.rglob('*') if p.is_file() and p.name != 'provenance.json'}
    prepare.save(target / 'provenance.json', provenance)
    cc = Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
    for backend in ('soc', 'spike'):
        directory = args.out / backend
        prepare.compile_programs(target, directory, cc, spike_reference=backend == 'spike')
        ledger = json.loads((directory / 'programs.json').read_text())
        entry = ledger['programs']['m8widen_nonzero']
        entry['pass_markers'] = ['BOARD_REPLAY_PASS', 'BOARD_CASE_PASS m8widen_nonzero',
                                 'EXTENDED_PASS flags_sequence reductions=8 ordinary=8']
        ledger['programs'] = {'flags_sequence': entry}
        prepare.save(directory / 'programs.json', ledger)
    subprocess.run([sys.executable, str(BASE / 'reference.py'), '--programs',
                    str(args.out / 'spike'), '--out', str(args.out / 'reference')], check=True)
    print('FLAGS_SEQUENCE_PREPARED', args.out)


if __name__ == '__main__':
    main()
