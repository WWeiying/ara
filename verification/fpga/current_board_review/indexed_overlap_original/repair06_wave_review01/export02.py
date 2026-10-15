#!/usr/bin/env python3
"""Direct bounded FSDB reader; -s extractor cannot handle an open writer container."""
import json
import os
import subprocess
import time
from pathlib import Path
from acquire import HERE, ART, OWNER, VERDI, TOOL, files, sha, save

before_time, before = time.time(), files()
time.sleep(2)
after_time, after = time.time(), files()
assert before == after
for p, metadata in before.items():
    assert sha(HERE/'inputs'/Path(p).name) == metadata['sha256']
env = dict(os.environ, LD_LIBRARY_PATH=str(VERDI/'etc/lib/libstdc++/linux64'))
command = [str(TOOL), str(HERE/'inputs/indexed_first_round.fsdb'), '-o', str(HERE/'bounded.vcd'),
           '-bt', '367700ns', '-et', '369300ns', '-compacttree']
with (HERE/'export02.log').open('x') as stream:
    result = subprocess.run(command, cwd=HERE, env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
final = files()
assert before == final
pins = {str(p):sha(p) for p in sorted((HERE/'inputs').iterdir()) if p.is_file()}
for p in (ART/'input.elf', ART/'inputs.json', ART/'command.json', OWNER/'repair06_worker/capture.tcl',
          OWNER/'repair06_worker/prepared01/plan.json', HERE/'export_profile.json', Path(__file__),
          HERE/'fsdb_summary02.log', HERE/'export.log', HERE/'export02.log'):
    pins[str(p)] = sha(p)
if result.returncode == 0:
    pins[str(HERE/'bounded.vcd')] = sha(HERE/'bounded.vcd')
save(HERE/'acquisition.json', dict(status='STABLE_DISABLED_FLUSHED_PROFILE_NOT_TERMINAL_DUT',
    marker='INDEXED_PROFILE_CLOSED_AT_1000000NS', before_time=before_time, after_time=after_time,
    before=before, after=after, after_export=final, copied_inputs_match=True,
    original_fsdb_stable=True, max_ticks=10000000000, max_ns=1000000, scale='100fs',
    writer_container_closed=False, command=command, returncode=result.returncode,
    tool_sha256=sha(TOOL), pins=pins, no_DUT=True, full50_acceptance=False,
    first_export_failure='-s invokes fsdbextract, rejects unfinished gate/event FSDB container; log preserved',
    first_metadata_assertion='Summary is printed to stderr; merged summary02 verifies100fs/maximum.',
    csv_scope='Copied complete rows through cycle600000; not a terminal original CSV'))
print(json.dumps(dict(returncode=result.returncode, stable_files=len(before),
                     fsdb_sha=sha(HERE/'inputs/indexed_first_round.fsdb'))), flush=True)
assert result.returncode == 0
