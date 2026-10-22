#!/usr/bin/env python3
"""Offline focused export of already-copied closed waveform, no simulation."""
import json
import os
import re
import subprocess
import time
from acquire import HERE, ART, OWNER, VERDI, TOOL, files, sha, save

inputs = HERE/'inputs'
before_time, before = time.time(), files()
time.sleep(2)
after_time, after = time.time(), files()
assert before == after
for p, metadata in before.items():
    assert sha(inputs/__import__('pathlib').Path(p).name) == metadata['sha256']
env = dict(os.environ, LD_LIBRARY_PATH=str(VERDI/'etc/lib/libstdc++/linux64'))
command = [str(TOOL), str(inputs/'indexed_first_round.fsdb'), '-summary']
summary = subprocess.run(command, cwd=HERE, env=env, text=True, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, timeout=90)
with (HERE/'fsdb_summary02.log').open('x') as stream:
    stream.write(summary.stdout)
assert summary.returncode == 0 and re.search(r'scale unit\s*:\s*100fs', summary.stdout)
max_tag = re.search(r'max xtag\s*:\s*\((\d+) (\d+)\)', summary.stdout)
ticks = (int(max_tag[1]) << 32) | int(max_tag[2])
assert ticks == 1000000*10000
top = '/ara_tb/dut/i_ara_soc/i_system'
ara = top+'/i_ara'
profile = [('/ara_tb/clk', 0), (top+'/i_ara_commit_monitor/cycle_q', 0)]
profile += [(ara+'/'+m, 2) for m in ('i_dispatcher', 'i_sequencer', 'i_vlsu/i_addrgen', 'i_vlsu/i_vldu')]
profile += [(ara+f'/gen_lanes[{lane}]/i_lane', 2) for lane in range(4)]
command = [str(TOOL), str(inputs/'indexed_first_round.fsdb'), '-o', str(HERE/'focus.vcd'),
           '-bt', '367700ns', '-et', '369300ns', '-compacttree']
for path, depth in profile:
    command += ['-s', path, '-level', str(depth)]
save(HERE/'export_profile.json', dict(command=command, signal_scopes=profile,
    start_ns=367700, end_ns=369300, actual_fsdb_units='100fs', ticks_per_ns=10000,
    scope='Only already-captured dispatcher/sequence/lane/AddrGen/VLDU signals, 1600ns; not full SoC'))
with (HERE/'export.log').open('x') as stream:
    result = subprocess.run(command, cwd=HERE, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
assert result.returncode == 0
final = files()
assert before == final
pins = {str(p):sha(p) for p in sorted(inputs.iterdir()) if p.is_file()}
for p in (ART/'input.elf', ART/'inputs.json', ART/'command.json', OWNER/'repair06_worker/capture.tcl',
          OWNER/'repair06_worker/prepared01/plan.json', HERE/'export_profile.json', HERE/'focus.vcd'):
    pins[str(p)] = sha(p)
save(HERE/'acquisition.json', dict(status='CLOSED_STABLE_WAVE_EXPORTED_NOT_FULL50_ACCEPTANCE',
    closed_marker='INDEXED_PROFILE_CLOSED_AT_1000000NS', before_time=before_time, after_time=after_time,
    before=before, after=after, after_export=final, copied_inputs_match=True,
    original_fsdb_stable=True, max_ticks=ticks, max_ns=ticks/10000, scale='100fs',
    command=command, returncode=result.returncode, tool_sha256=sha(TOOL), pins=pins,
    original_acquire_assertion='Metadata appeared on stderr, not stdout. Original summary log retained; merged stdout/stderr verified here.',
    csv_scope='Copied complete rows through cycle600000; not a terminal original CSV',
    no_DUT=True, full50_acceptance=False))
print(json.dumps(dict(status='EXPORTED', max_ns=ticks/10000, stable_files=len(before),
                     fsdb_sha=sha(inputs/'indexed_first_round.fsdb'), vcd_bytes=(HERE/'focus.vcd').stat().st_size)))
