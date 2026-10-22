#!/usr/bin/env python3
"""Mechanical dryrun-only correction; keep the frozen plan01 and outcome."""
import difflib
import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
OLD = HERE.parent / 'vi0_missing2_vcs_m7_plan01'
text = (OLD / 'replay.py').read_text()
before = "dict(command=command_for(root,case['id'],ledger['simv']),cwd=str(root/'work'))"
after = "dict(command=[a if not a.startswith('+PRELOAD=') else '+PRELOAD='+case['elf'] for a in command_for(root,case['id'],ledger['simv'])],cwd=str(root/'work'))"
assert text.count(before) == 1
fixed = text.replace(before, after)
anchor = "    pins[str(HERE/'host02.json')] = sha(HERE/'host02.json')\n"
addition = """    for dependency in (Path(common.__file__), Path(common.base.__file__),
                       Path(common.base.shared.__file__), HERE/'materialize.py', HERE/'successor_proof.json',
                       HERE/'worker_delta.diff', HERE.parent/'audit_accepted8.py',
                       HERE.parent/'prepare_successor.py', HERE.parent/'prepare_batch.py'):
        pins[str(dependency)] = sha(dependency)
    m6 = Path('/home/wangwy/fpga_runs/current_board_memory_candidate06/frozen')
    for relative in ('snapshot.json','sources/hardware/bender','sources/frozen.filelist'):
        pins[str(m6/relative)] = sha(m6/relative)
"""
assert fixed.count(anchor) == 1
fixed = fixed.replace(anchor, anchor + addition)
with (HERE / 'replay.py').open('x') as stream:
    stream.write(fixed)
with (HERE / 'worker_delta.diff').open('x') as stream:
    stream.write(''.join(difflib.unified_diff(text.splitlines(True), fixed.splitlines(True))))
for name in ('configure.py','test_worker.py'):
    with (HERE / name).open('xb') as stream:
        stream.write((OLD / name).read_bytes())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
with (HERE / 'successor_proof.json').open('x') as stream:
    json.dump(dict(status='DRYRUN_COMMAND_GATE_CORRECTION_NO_DUT',
        previous_actual_tool_exit=1, previous_execution='exec session65900 chunk6cc709 actualexit1',
        previous_DUT_invocations=0, source_reference_reruns=0,
        only_changes=['Dryrun source ELF matches frozen runner; real monitor private ELF requirement unchanged',
                      'Supplement helper and M6 relocation comparison pins'],
        old_artifacts={str(p):sha(p) for p in OLD.rglob('*') if p.is_file()},
        corrected_worker_sha256=sha(HERE/'replay.py')), stream, indent=2)
    stream.write('\n')
