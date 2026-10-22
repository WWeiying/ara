#!/usr/bin/env python3
"""Convert the sealed, explicit slide profile into a bounded VCD."""
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
        parser.error('output must remain under large_offset_slide/')
    status = json.loads((out / 'status.json').read_text())
    if status['state'] != 'CAPTURED':
        raise ValueError('Capture is not complete')
    if (out / 'selected.vcd').exists():
        raise FileExistsError('Do not overwrite evidence')
    signals = json.loads((out / 'signals.json').read_text())
    window = json.loads((out / 'command.json').read_text())['window_ns']
    cmd = [str(VERDI / 'platform/linux64/bin/fsdb2vcd'), 'slide.fsdb',
           '-o', 'selected.vcd', '-bt', str(window[0]) + 'ns',
           '-et', str(window[1]) + 'ns', '-compacttree', '-s']
    cmd += ['/' + signal.replace('.', '/') for signal in signals]
    (out / 'convert_command.json').write_text(json.dumps(cmd, indent=2) + '\n')
    env = dict(os.environ, LD_LIBRARY_PATH=str(VERDI / 'etc/lib/libstdc++/linux64'))
    with (out / 'convert.log').open('w') as log:
        subprocess.run(cmd, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT,
                       check=True, timeout=120)
    with (out / 'selected.vcd').open() as vcd:
        if not any('$enddefinitions' in line for line in vcd):
            raise ValueError('Incomplete VCD header')
    print('SELECTED_VCD_COMPLETE', (out / 'selected.vcd').stat().st_size)


if __name__ == '__main__':
    main()
