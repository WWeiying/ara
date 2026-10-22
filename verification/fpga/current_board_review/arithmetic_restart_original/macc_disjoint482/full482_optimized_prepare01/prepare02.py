#!/usr/bin/env python3
"""Python compatibility successor; preserve the failed pre-Host attempt."""
import difflib
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
old=(HERE/'prepare.py').read_text()
failure=json.loads((HERE/'STOPPED.json').read_text())
assert failure['error']=="TypeError('zip() takes no keyword arguments')"
assert not (HERE/'prepared').exists() and not (HERE/'host').exists() and not (HERE/'reference').exists()
before="    for actual,want in zip(gold['rows'],old_expected,strict=True):"
after="    require(len(gold['rows'])==len(old_expected),'Complete original scope length')\n    for actual,want in zip(gold['rows'],old_expected):"
assert old.count(before)==1
fixed=old.replace(before,after).replace("save(HERE/'input_pins.json',pins)","save(HERE/'input_pins02.json',pins)")
fixed=fixed.replace("save(HERE/'STOPPED.json',dict(","save(HERE/'STOPPED02.json',dict(")
generated=HERE/'prepare02_generated.py'
with generated.open('x') as stream:stream.write(fixed)
with (HERE/'python_compatibility.diff').open('x') as stream:
    stream.write(''.join(difflib.unified_diff(old.splitlines(True),fixed.splitlines(True))))
namespace={'__file__':str(generated),'__name__':'owned_compatibility_successor'}
exec(compile(fixed,str(generated),'exec'),namespace)
namespace['save'](HERE/'attempt01_receipt.json',dict(status='PRESERVED_STATIC_PYTHON_COMPATIBILITY_FAILURE',
    actual_tool_exit=1,execution='exec session16610 chunke550e4 actualexit1',
    Host_compiles=0,SoC_compiles=0,Spike_runs=0,error=failure['error'],
    original_producer_sha256=namespace['sha'](HERE/'prepare.py'),
    original_input_pins_sha256=namespace['sha'](HERE/'input_pins.json'),
    original_failure_sha256=namespace['sha'](HERE/'STOPPED.json')))
namespace['main']()
