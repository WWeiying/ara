#!/usr/bin/env python3
"""Fresh work05 with the missing Host adapter staged unchanged."""
from pathlib import Path
import shutil
import sys
import prepare03_generated as producer

sys.dont_write_bytecode=True
TOP=Path(__file__).resolve().parent
OUT=TOP/'work05'


def main():
    previous=TOP/'work04'
    failure=producer.read(previous/'STOPPED.json')
    producer.require('original.compile.log' in failure['error'] and
        'host_adapter.c: No such file' in (previous/'host/original.compile.log').read_text(),
        'Exact missing Host dependency cause')
    producer.require(not OUT.exists() and not (previous/'soc').exists() and not (previous/'reference').exists(),
                     'Fresh work05; no previous target/ref launch')
    OUT.mkdir()
    pins={str(p):producer.sha(p) for p in TOP.rglob('*') if p.is_file() and not p.is_relative_to(OUT)}
    shutil.copytree(previous/'prepared03',OUT/'prepared03')
    for name in ('model.json','static_scope.json'):
        shutil.copyfile(previous/name,OUT/name)
    shutil.copyfile(TOP/'host_adapter.c',OUT/'host_adapter.c')
    producer.require(producer.sha(OUT/'host_adapter.c')==producer.sha(TOP/'host_adapter.c'), 'Host adapter bytes changed')
    inputs=[OUT/'host_adapter.c',producer.CC,producer.OBJDUMP,producer.SPIKE,
        OUT/'prepared03/case.c',OUT/'prepared03/original_prefix.c',OUT/'prepared03/main.c',
        OUT/'prepared03/tables.h',OUT/'prepared03/original/operations.h',OUT/'prepared03/original/scenario.S',
        OUT/'prepared03/startup.S',OUT/'prepared03/runtime.c',OUT/'prepared03/replay.ld']
    producer.require(all(path.is_file() for path in inputs),'Compiler/runtime prerequisite missing')
    producer.save(OUT/'successor.json',dict(status='HOST_ADAPTER_PATH_STAGED_UNCHANGED',
        previous_actual_tool_exit=1,previous_execution='exec session41528 chunkdb0a46 actualexit1',
        compiler_inputs={str(path):producer.sha(path) for path in inputs},
        old_artifacts=pins,previous_target_compiles=0,previous_reference_runs=0,
        source_model_and_flags_unchanged=True,driver_sha256=producer.sha(Path(__file__))))
    producer.HERE=OUT
    try:
        producer.host(producer.read(OUT/'model.json'))
        print('FULL482 HOST_FULLBYTE+10ERRORS+UNUSED_PERMISSION PASS',flush=True)
        programs=producer.build()
        print('OPTIMIZED SOC+SPIKE ORIGINAL13 MEMORY PASS',flush=True)
        producer.require(all(producer.sha(path)==digest for path,digest in pins.items()),'Old evidence changed')
        producer.save(OUT/'PRE_REFERENCE.json',dict(status='HOST_AND_ELFS_READY_NO_REFERENCE_YET',
            programs=programs,model_sha256=producer.sha(OUT/'model.json'),pins={**pins,**{
                str(path):producer.sha(path) for path in OUT.rglob('*') if path.is_file()}}))
    except BaseException as error:
        producer.save(OUT/'STOPPED.json',dict(status='PREPARATION_FAILED_NO_RETRY',error=repr(error),DUT_runs=0))
        raise


if __name__=='__main__':main()
