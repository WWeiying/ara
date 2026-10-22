#!/usr/bin/env python3
"""Fresh work04 after a diagnosed message-literal escaping error; no old edits."""
import difflib
from pathlib import Path
import shutil
import sys
import prepare03_generated as producer

sys.dont_write_bytecode=True
TOP=Path(__file__).resolve().parent
OUT=TOP/'work04'


def main():
    failure=producer.read(TOP/'STOPPED03.json')
    producer.require('optimized.compile.log' in failure['error'],'Exact Host syntax admission failure')
    log=(TOP/'host/optimized.compile.log').read_text()
    producer.require('missing terminating " character' in log and 'MACC_OPT_RNG_FAIL' in log,
                     'Actual compiler evidence of message literal error')
    producer.require(not (TOP/'soc').exists() and not (TOP/'reference').exists() and not OUT.exists(),
                     'No target compile/reference before failure; fresh work04')
    OUT.mkdir()
    old_pins={str(p):producer.sha(p) for p in TOP.rglob('*') if p.is_file() and not p.is_relative_to(OUT)}
    shutil.copytree(TOP/'prepared03',OUT/'prepared03')
    source=OUT/'prepared03/case.c'
    before=source.read_text()
    bad='text("MACC_OPT_RNG_FAIL\n");return 92;'
    good='text("MACC_OPT_RNG_FAIL\\n");return 92;'
    producer.require(before.count(bad)==1,'Unique malformed message literal')
    fixed=before.replace(bad,good)
    source.write_text(fixed)
    (OUT/'message_escape.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True),fixed.splitlines(True))))
    original=(TOP/'prepared03/original_prefix.c').read_text()
    begin,end='    for(unsigned seed=','        for(unsigned op='
    producer.require(all(s.count(begin)==s.count(end)==1 for s in (original,fixed)), 'Unique final RNG anchors')
    producer.require(original[original.index(begin):original.index(end)]==fixed[fixed.index(begin):fixed.index(end)],
                     'Final RNG bytes must remain exact')
    for name in ('model.json','static_scope.json'):
        shutil.copyfile(TOP/name,OUT/name)
    producer.save(OUT/'successor.json',dict(status='MESSAGE_LITERAL_ESCAPE_ONLY_SOURCE_VALUE_UNCHANGED',
        previous_tool_actual_exit=1,previous_execution='exec session6245 chunka720fe actualexit1',
        original_Host_actual_exit=producer.read(TOP/'host/original.execution.json')['actual_returncode'],
        previous_SoC_compiles=0,previous_Spike_runs=0,old_artifacts=old_pins,
        source_before_sha256=producer.sha(TOP/'prepared03/case.c'),source_after_sha256=producer.sha(source),
        error_message_only=True,RNG_model_or_oracle_changed=False,
        driver_sha256=producer.sha(Path(__file__)),compiler_flags_changed=False))
    producer.HERE=OUT
    try:
        gold=producer.read(OUT/'model.json')
        producer.host(gold)
        print('FULL482 HOST_FULLBYTE+10ERRORS+UNUSED_PERMISSION PASS',flush=True)
        programs=producer.build()
        print('OPTIMIZED SOC+SPIKE ORIGINAL13 MEMORY PASS',flush=True)
        producer.require(all(producer.sha(p)==digest for p,digest in old_pins.items()),'Failed artifacts changed')
        producer.save(OUT/'PRE_REFERENCE.json',dict(status='HOST_AND_ELFS_READY_NO_REFERENCE_YET',programs=programs,
            model_sha256=producer.sha(OUT/'model.json'),pins={**old_pins,**{
                str(p):producer.sha(p) for p in OUT.rglob('*') if p.is_file()}}))
    except BaseException as error:
        producer.save(OUT/'STOPPED.json',dict(status='PREPARATION_FAILED_NO_RETRY',error=repr(error),DUT_runs=0))
        raise


if __name__=='__main__':main()
