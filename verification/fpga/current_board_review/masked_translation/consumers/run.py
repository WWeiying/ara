#!/usr/bin/env python3
"""Pinned, host-VCS consumer probes; no production edits or full image build."""
import argparse
import csv
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import time

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[4]
VCS = Path('/home/wangwy/software/synopsys/install/vcs/V-2023.12-SP1')
FILES = [
    'hardware/deps/common_cells/src/cf_math_pkg.sv',
    'hardware/deps/axi/src/axi_pkg.sv',
    'hardware/deps/cva6/core/include/config_pkg.sv',
    'hardware/deps/cva6/core/include/cv64a6_imafdcv_sv39_config_pkg.sv',
    'hardware/deps/cva6/core/include/riscv_pkg.sv',
    'hardware/deps/cva6/core/include/build_config_pkg.sv',
    'hardware/include/rvv_pkg.sv', 'hardware/deps/fpnew/src/fpnew_pkg.sv',
    'hardware/include/ara_pkg.sv',
    'hardware/deps/common_cells/src/spill_register_flushable.sv',
    'hardware/deps/common_cells/src/stream_register.sv',
    'hardware/src/vlsu/vldu.sv',
    str((HERE / 'vldu_exception_tb.sv').relative_to(ROOT)),
]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def env():
    result = {k: os.environ[k] for k in ('HOME', 'USER', 'LOGNAME', 'TMPDIR') if k in os.environ}
    result.update(PATH=f'{VCS}/bin:/usr/bin:/bin', VCS_HOME=str(VCS),
                  VCS_TARGET_ARCH='linux64', SNPSLMD_LICENSE_FILE='27000@t7920',
                  LM_LICENSE_FILE='27000@t7920', LC_ALL='C')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--rtl-root', type=Path, required=True,
                        help='Explicit source tree, preferably an existing frozen baseline/candidate')
    parser.add_argument('--suite', choices=('exception', 'arrival', 'sequencer'), default='exception')
    args = parser.parse_args()
    out = args.out.resolve()
    if not out.is_relative_to(HERE) or out == HERE:
        raise ValueError('Output must be a new owned subdirectory')
    out.mkdir(parents=True, exist_ok=False)
    source_root = args.rtl_root.resolve()
    top = {'exception': 'vldu_exception_tb', 'arrival': 'vldu_arrival_tb',
           'sequencer': 'sequencer_fault_tb'}[args.suite]
    files = FILES[:-1]
    if args.suite == 'sequencer':
        files = FILES[:9] + ['hardware/deps/common_cells/src/' + name + '.sv'
                            for name in ('lzc', 'delta_counter', 'counter')]
        files += ['hardware/src/ara_sequencer.sv']
    files = files + [str((HERE / (top + '.sv')).relative_to(ROOT))]
    paths = set(files) | {str(Path(__file__).resolve().relative_to(ROOT))}
    if args.suite == 'sequencer':
        paths.add('hardware/src/ara.sv')
    for directory in ('hardware/include/ara', 'hardware/deps/common_cells/include/common_cells',
                      'hardware/deps/axi/include/axi'):
        paths.update(str(p.relative_to(source_root)) for p in (source_root / directory).glob('*.svh'))
    def source(p):
        return (source_root if p.startswith('hardware/') else ROOT) / p
    hashes = {p: sha(source(p)) for p in sorted(paths)}
    frozen = out / 'frozen'
    for p, digest in hashes.items():
        target = frozen / p
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(source(p).read_bytes())
        assert sha(target) == digest, p
        target.chmod(0o444)
    assert hashes == {p: sha(source(p)) for p in hashes}, 'Snapshot drift'
    if args.suite == 'sequencer':
        source_text = (frozen / 'hardware/src/ara.sv').read_text()
        types = []
        for name in ('ara_req_t', 'ara_resp_t'):
            matches = re.findall(r'typedef struct packed \{[^}]*\} ' + name + ';', source_text)
            if len(matches) != 1:
                raise ValueError('Unambiguous source-derived type required: ' + name)
            types.append(matches[0])
        (frozen / 'sequencer_types.svh').write_text('\n'.join(types) + '\n')
    save(out / 'pins.json', dict(files=hashes, scope=args.suite + ' public-interface unit, not SoC',
                                 nr_lanes=4, vlen=1024, axi_bits=256, rtl_source_root=str(source_root)))
    cmd = [str(VCS / 'bin/vcs'), '-full64', '-sverilog', '-timescale=1ns/1ps',
           '-top', top, '-debug_access+all',
           '+incdir+' + str(frozen / 'hardware/deps/common_cells/include'),
           '+incdir+' + str(frozen / 'hardware/deps/axi/include'),
           '+incdir+' + str(frozen / 'hardware/include'),
           '+incdir+' + str(frozen),
           *[str(frozen / p) for p in files], '-o', str(out / 'simv'),
           '-l', str(out / 'compile.log')]
    save(out / 'command.json', cmd)
    status = dict(state='STARTED', cases=[])
    save(out / 'status.json', status)
    try:
        start = time.monotonic()
        with (out / 'compile.console.log').open('w') as log:
            subprocess.run(cmd, cwd=out, env=env(), stdout=log, stderr=subprocess.STDOUT,
                           timeout=180, check=True)
        status['compile_seconds'] = time.monotonic() - start
        cases = (('normal_delayed_final', 'partial_exception', 'first_exception',
                  'fof_exception_successor', 'older_full_then_partial', 'word_boundary_exception')
                 if args.suite == 'exception' else
                 ('descriptor_first', 'descriptor_same_cycle', 'sideband_first', 'sideband_same_cycle'))
        if args.suite == 'sequencer':
            cases = ('normal_delayed_done', 'fof_fault_delayed_done', 'fault_delayed_done',
                     'other_vid_done', 'done_before_ack', 'done_with_ack', 'fof_no_fault')
        for variant, name in enumerate(cases):
            directory = out / name
            directory.mkdir()
            command = [str(out / 'simv'), '-no_save', f'+CASE={variant}']
            with (directory / 'run.log').open('w') as log:
                result = subprocess.run(command, cwd=directory, env=env(), stdout=log,
                                        stderr=subprocess.STDOUT, timeout=20)
            logtext = (directory / 'run.log').read_text()
            observations = [line for line in logtext.splitlines() if line.startswith('OBSERVATION ')]
            observation = {}
            if len(observations) == 1:
                observation = {k: int(v) for k, v in
                               (item.split('=') for item in observations[0].split()[1:])}
            entry = dict(name=name, command=command, returncode=result.returncode,
                         probe_completed=f'PROBE_COMPLETED case={variant}' in logtext,
                         observation=observation)
            if (directory / 'cycles.csv').exists():
                with (directory / 'cycles.csv').open() as stream:
                    rows = list(csv.DictReader(stream))
                entry['terminal_row'] = rows[-1] if rows else None
            entry['scope'] = 'consumer unit only; no trap/CSR/MMU claim'
            status['cases'].append(entry)
            save(out / 'status.json', status)
            print(name, json.dumps(entry), flush=True)
        assert hashes == {p: sha(frozen / p) for p in hashes}, 'Frozen drift'
        status['state'] = ('PROBES_COMPLETE' if all(c['probe_completed'] and c['returncode'] == 0
                                                   for c in status['cases']) else 'PROBE_ERROR')
        status['frozen_verified'] = True
    except Exception as error:
        status.update(state='ERROR', error=repr(error))
    save(out / 'status.json', status)
    print(json.dumps(status, indent=2))
    return status['state'] != 'PROBES_COMPLETE'


if __name__ == '__main__':
    raise SystemExit(main())
