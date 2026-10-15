"""One bounded short C test and one compile per backend; never executes ELF."""
import hashlib,json,os,subprocess,sys,time
from pathlib import Path
HERE=Path(__file__).resolve().parent;OLD=HERE.parent/'full_e16_m8_block_unrolled01'
REVIEW=HERE.parent/'m8_sentinel_mask_static_review_hilbert01/SOURCE_REVIEW.md'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):
    with p.open('x') as f:json.dump(v,f,indent=2);f.write('\n')
def run(command,log,timeout=90):
    save(log.with_suffix(log.suffix+'.command.json'),dict(command=list(map(str,command)),timeout_s=timeout))
    start=time.monotonic();timed=False
    with log.open('x') as f:
        child=subprocess.Popen(list(map(str,command)),cwd=HERE,stdout=f,stderr=subprocess.STDOUT)
        try:rc=child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:timed=True;child.kill();rc=child.wait()
        record=dict(returncode=rc,pid=child.pid,elapsed_s=time.monotonic()-start,timed_out=timed,retries=0)
        save(log.with_suffix(log.suffix+'.exit.json'),record)
    if rc!=0 or timed:raise ValueError('STOP actual child '+str(log)+' '+repr(record))
    return record
def main():
    if sha(REVIEW)!='08c7c7ed02e585b47f0c37aa1b09549ddcf3dc1d32d1d00bc700b3fabc123599':raise ValueError('Actual source review binding')
    if (HERE/'INPUT_PINS.json').exists():raise ValueError('No rerun')
    files=[HERE/'case.c',HERE/'packed.h',HERE/'short_host.c',HERE/'prepare_once.py',HERE/'SOURCE_PLAN.md',REVIEW,
        OLD/'case.c',OLD/'packed.h',OLD/'dictionary.h',OLD/'sequence.json',OLD/'seed_inputs.json',OLD/'original/scenario.S',OLD/'original/operations.h']
    for backend in ('soc','spike'):
        command=json.loads((OLD/backend/'compile.log.command.json').read_text())['command']
        files += [OLD/backend/'compile.log.command.json',OLD/backend/'main.c',Path(command[0])]
        files += [Path(x) for x in command if str(x).endswith(('.ld','.S','.c'))]
    pins={str(p.resolve()):sha(p) for p in files};save(HERE/'INPUT_PINS.json',pins)
    if (HERE/'case.c').read_bytes()!=(OLD/'case.c').read_bytes():raise ValueError('Original main/fallback changed')
    outputs={}
    try:
        host=HERE/'short_host';run(['/usr/bin/cc','-O2','-Wall','-Wextra','-Werror','-fsanitize=undefined','-fsanitize-undefined-trap-on-error',
            '-fno-tree-vectorize','-fno-tree-slp-vectorize',HERE/'short_host.c','-o',host],HERE/'short_host_compile.log',60)
        run([host],HERE/'short_host.log',30)
        for backend in ('soc','spike'):
            print('PHASE GCC '+backend+' START',flush=True)
            out=HERE/backend;out.mkdir()
            command=json.loads((OLD/backend/'compile.log.command.json').read_text())['command']
            command=[str(HERE/'case.c') if x==str(OLD/'case.c') else str(out/'program.elf') if x==str(OLD/backend/'program.elf') else x for x in command]
            command[1:1]=['-iquote',str(OLD),'-Wl,-Map='+str(out/'program.map')]
            rc=run(command,out/'compile.log',90)
            tools=Path(command[0]).parent
            run([tools/'riscv64-unknown-elf-objdump','-d',out/'program.elf'],out/'program.dis',30)
            run([tools/'riscv64-unknown-elf-nm','-n',out/'program.elf'],out/'symbols.log',30)
            run([tools/'riscv64-unknown-elf-readelf','-lW',out/'program.elf'],out/'segments.log',30)
            symbols={}
            for line in (out/'symbols.log').read_text().splitlines():
                fields=line.split()
                if len(fields)==3:
                    try:symbols[fields[2]]=int(fields[0],16)
                    except ValueError:pass
            save(out/'symbols.json',symbols)
            outputs[backend]=dict(actual_compile=rc,elf_sha256=sha(out/'program.elf'),elf=str(out/'program.elf'),
                stack_gap=symbols['__stack_top']-symbols['__bss_end'])
            print('PHASE GCC '+backend+' actual0',flush=True)
        for p,h in pins.items():
            if sha(Path(p))!=h:raise ValueError('Input pin drift '+p)
        save(HERE/'COMPILE_RESULT.json',dict(status='SHORT_C_PASS_DUAL_COMPILED_PENDING_LINKED_CFG_NO_REFERENCE_NO_DUT',
            backends=outputs,short_host_positive_ordinals=[0,1365,2730,4094,9,45,1257,1278,1299],
            short_host_byte_negatives=9252,full4095_stream_Host_runs=0,source_pins_unchanged=True,
            compile_attempts_each=1,reference_runs=0,DUT_runs=0,original_fallback_byte_identical=True))
    except BaseException as error:
        save(HERE/'STOPPED.json',dict(status='STOPPED_SOFTWARE_PREPARATION_NOT_RTL',firstcause=type(error).__name__+': '+str(error),outputs=outputs,no_auto_retry=True))
        raise
if __name__=='__main__':main()

