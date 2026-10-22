#!/usr/bin/env python3
"""Convert only the explicit captured signal profile; never traverse whole scopes."""
import argparse
import json
import os
from pathlib import Path
import subprocess

HERE = Path(__file__).resolve().parent
VERDI = Path('/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('capture', type=Path)
    args = parser.parse_args()
    out = args.capture.resolve()
    if not out.is_relative_to(HERE):
        raise ValueError('owned output only')
    signals = json.loads((out / 'signals.json').read_text())
    command = [str(VERDI / 'platform/linux64/bin/fsdb2vcd'), 'comparison.fsdb',
               '-o', 'selected.vcd', '-bt', '16200ns', '-et', '16600ns', '-compacttree', '-s']
    command += ['/' + name.replace('.', '/') for name in signals]
    (out / 'convert_command.json').write_text(json.dumps(command, indent=2) + '\n')
    env = dict(os.environ, LD_LIBRARY_PATH=str(VERDI / 'etc/lib/libstdc++/linux64'))
    with (out / 'convert.log').open('w') as log:
        subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=120)
    text = (out / 'selected.vcd').read_text()
    if '$enddefinitions' not in text:
        raise ValueError('conversion incomplete')
    print('SELECTED_VCD_COMPLETE', len(text))


if __name__ == '__main__':
    main()
