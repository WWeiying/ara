#!/usr/bin/env python3
"""Read closed M6 waveform once; write only independent offline evidence copies."""
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time

HERE = Path(__file__).resolve().parent
OWNER = HERE.parent
ART = OWNER/'repair06_worker/prepared01/pilot/tests/d32m2_i64_fault_ov1'
VERDI = Path('/home/wangwy/software/synopsys/install/verdi/V-2023.12-SP1')
TOOL = VERDI/'platform/linux64/bin/fsdb2vcd'


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1024*1024), b''):
            h.update(b)
    return h.hexdigest()


def save(p, value):
    with p.open('x') as f:
        json.dump(value, f, indent=2)
        f.write('\n')


def files():
    return {str(p): dict(size=p.stat().st_size, mtime_ns=p.stat().st_mtime_ns, sha256=sha(p))
            for p in sorted((ART/'work').glob('indexed_first_round.fsdb*')) if p.is_file()}


def main():
    assert not (HERE/'inputs').exists()
    prefix = bytearray()
    with (ART/'console.log').open('rb') as stream:
        for line_number, line in enumerate(stream, 1):
            prefix.extend(line)
            if line.strip() == b'INDEXED_PROFILE_CLOSED_AT_1000000NS':
                break
        else:
            raise ValueError('No actual closed-profile marker; refuse export')
    t0, before = time.time(), files()
    assert before and str(ART/'work/indexed_first_round.fsdb') in before
    time.sleep(2)
    t1, after = time.time(), files()
    assert before == after, 'Wave/sidecars still changing; no retry'
    dest = HERE/'inputs'
    dest.mkdir()
    for name, item in before.items():
        p = Path(name)
        shutil.copyfile(p, dest/p.name)
        assert sha(dest/p.name) == item['sha256']
    with (dest/'console_through_profile_close.log').open('xb') as f:
        f.write(prefix)
    csv_in = ART/'commit_trace.csv'
    rows, last = 0, None
    with csv_in.open('rb') as src, (dest/'commit_through_cycle600000.csv').open('xb') as dst:
        dst.write(next(src))
        for raw in src:
            if not raw.endswith(b'\n'):
                break
            cycle = int(raw.split(b',', 1)[0])
            if cycle > 600000:
                break
            dst.write(raw)
            rows, last = rows+1, cycle
    assert last is not None and last >= 599000, 'Requested CSV prefix not yet available; no retry'
    pinned = [ART/'input.elf', ART/'inputs.json', ART/'command.json', OWNER/'repair06_worker/capture.tcl',
              OWNER/'repair06_worker/prepared01/plan.json', Path(__file__)]
    env = dict(os.environ, LD_LIBRARY_PATH=str(VERDI/'etc/lib/libstdc++/linux64'))
    commands = []
    for args, name in (([str(dest/'indexed_first_round.fsdb'), '-summary'], 'fsdb_summary.log'),
                       (['-help'], 'fsdb2vcd_help.log')):
        command = [str(TOOL), *args]
        result = subprocess.run(command, cwd=HERE, env=env, capture_output=True, text=True, timeout=90)
        with (HERE/name).open('x') as stream:
            stream.write(result.stdout+result.stderr)
        commands.append(dict(command=command, returncode=result.returncode, log=name))
        if name == 'fsdb_summary.log':
            assert result.returncode == 0 and '100fs' in result.stdout
    final = files()
    assert final == before, 'Original FSDB changed during acquisition'
    save(HERE/'acquisition.json', dict(status='STABLE_CLOSED_WAVE_COPIED_NOT_TERMINAL_DUT',
        original_artifact=str(ART), before_time=t0, after_time=t1, before=before, after=after,
        after_export_metadata=final, closed_marker_line=line_number,
        console_prefix_bytes=len(prefix), csv_prefix_rows=rows, csv_last_cycle=last,
        csv_prefix_boundary='Complete lines with cycle<=600000; running original is not a sealed terminal CSV',
        inputs={str(p):sha(p) for p in sorted(dest.iterdir()) if p.is_file()},
        pins={str(p):sha(p) for p in pinned}, tool_sha256=sha(TOOL), commands=commands,
        no_DUT_started=True, full50_acceptance=False))
    print(json.dumps(dict(marker_line=line_number, stable_files=len(before), csv_rows=rows,
                          last_cycle=last, main_sha=sha(dest/'indexed_first_round.fsdb'))), flush=True)


if __name__ == '__main__':
    main()
