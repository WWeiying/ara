"""Single Host/UB and fixed-flags SoC+Spike compile; no reference or DUT."""
import difflib
import importlib.util
import json
import os
from pathlib import Path
import resource
import subprocess
import time

from prepare import HERE, OLD, sha, save
import host_adapter

sp = importlib.util.spec_from_file_location('immutable_compile_configuration',OLD/'compile01/execute.py')
old = importlib.util.module_from_spec(sp)
sp.loader.exec_module(old)
CC, FLAGS = old.CC, old.FLAGS
DEFS = ['-DSEW=16','-DUNMASKED_COMPARISONS=0','-DUNBOXED_COMPARISONS=1',
        '-DRESTART_COMPARISONS=0','-DDESTINATION_KIND=0']


def command(argv, prefix, expected=0, timeout=120):
    argv = list(map(str,argv))
    save(prefix.with_suffix('.command.json'),argv)
    started = time.monotonic()
    def limits():
        resource.setrlimit(resource.RLIMIT_CORE,(0,0))
    with prefix.with_suffix('.log').open('x') as log:
        child = subprocess.Popen(argv,stdout=log,stderr=subprocess.STDOUT,preexec_fn=limits)
        timed = False
        try:
            rc = child.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed = True
            child.kill()
            rc = child.wait()
        receipt = dict(actual_wait_exit=rc,elapsed_s=time.monotonic()-started,timed_out=timed,retries=0,validated=False)
        with prefix.with_suffix('.wait.json').open('x') as f:
            json.dump(receipt,f,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    assert not timed and rc==expected, str(prefix)+' actual '+str(receipt)
    return receipt


def main():
    out=HERE/'build01'
    assert not out.exists(),'One compile per backend, no retry'
    out.mkdir()
    source=HERE/'source'
    pins={str(p):sha(p) for p in source.rglob('*') if p.is_file()}
    pins.update(json.loads((HERE/'source_status.json').read_text())['pins'])
    for p in [Path(__file__),HERE/'host_adapter.py',CC,Path('/usr/bin/gcc')]:
        pins[str(p)]=sha(p)
    save(out/'inputs_before.json',pins)
    save(out/'fixed_configuration.json',dict(compiler=str(CC),flags=FLAGS,defines=DEFS,
        backends=['soc','spike'],each_compile_attempts=1,reference_authorized=False,DUT_authorized=False))
    host=out/'host';host.mkdir()
    for name in ('case.c','generated_tables.h'):
        (host/name).write_bytes((source/name).read_bytes())
    core=(source/'packed_core.h').read_text()
    begin,end=core.index('#define SD_AT('),core.index('#define ALL_16_SD(')
    adapted=core[:begin]+'#define SD_AT(base, offset, value) host_store(base,offset,(uint64_t)(value),8)\n#define SH_AT(base, offset, value) host_store(base,offset,(uint64_t)(value),2)\n'+core[end:]
    begin,end=adapted.index('static inline uint32_t result_and_guards'),adapted.index('static inline unsigned packed_errors')
    adapted=adapted[:begin]+'static inline uint32_t result_and_guards(const void *p) {return host_lwu(p);}\n\n'+adapted[end:]
    assert adapted[adapted.index('static inline unsigned packed_errors'):]==core[core.index('static inline unsigned packed_errors'):]
    (host/'packed_core.h').write_text(adapted)
    (host/'host.c').write_text(host_adapter.build())
    (host/'original_host.diff').write_text(''.join(difflib.unified_diff(
        (source/'original/parent.c').read_text().splitlines(True),
        (source/'original_host.c').read_text().splitlines(True),fromfile='original',tofile='Host syscall adapter')))
    hostflags=['/usr/bin/gcc','-O2','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-const-variable',
        *DEFS,'-I'+str(host),'-I'+str(source/'original'),host/'host.c',source/'original_host.c']
    command([*hostflags,'-o',host/'host'],host/'compile')
    modes=['positive','legal_tailones','details','alloff_spurious_NV','active_missing_NV','inactive_result']
    tests={}
    for mode in modes:
        tests[mode]=command([host/'host',mode],host/mode,timeout=30)
    for mode in ['missing_input_store','missing_mask_store','missing_output_tail','wrong_raw_seed','wrong_record_mode']:
        tests[mode]=command([host/'host',mode],host/mode,expected=-6,timeout=30)
        assert 'Assertion' in (host/(mode+'.log')).read_text(), 'Not a deliberate Host assertion'
    command([*hostflags,'-fsanitize=undefined','-fno-sanitize-recover=all','-o',host/'host_ubsan'],host/'compile_ubsan')
    for mode in ('positive','alloff_spurious_NV'):
        tests['ubsan_'+mode]=command([host/'host_ubsan',mode],host/('ubsan_'+mode),timeout=30)
    save(host/'RESULT.json',dict(status='ORIGINAL_C_EQ_AND_TARGETED_NEGATIVES_PASS',tests=tests,
        original_C_executed=True,full_calls_each_positive=17920,helper='C stub not RVV execution',DUT=False))
    binaries={}
    for backend in ('soc','spike'):
        dest=out/backend;dest.mkdir();elf=dest/'program.elf'
        extras=['-DSPIKE_REFERENCE=1'] if backend=='spike' else []
        command([CC,*FLAGS,*DEFS,*extras,'-T',source/'replay.ld','-Wl,-Map='+str(dest/'program.map'),
            '-I'+str(source/'original'),source/'case.c',source/'original/scenario.S',source/'main.c',
            source/'startup.S',source/'runtime.c','-lgcc','-o',elf],dest/'compile')
        for tool,args,label in [('objdump',['-d'],'disassemble'),('nm',['-S','-n'],'symbols'),('readelf',['-l','-A'],'layout')]:
            command([CC.with_name('riscv64-unknown-elf-'+tool),*args,elf],dest/label)
        binaries[backend]=dict(path=str(elf),sha256=sha(elf))
    assert all(sha(p)==h for p,h in pins.items())
    save(out/'RESULT.json',dict(status='DUAL_COMPILED_PENDING_FULL_LINKED_COST',binaries=binaries,
        inputs_unchanged=True,reference_executed=False,DUT_executed=False))
    print(json.dumps(binaries),flush=True)


if __name__=='__main__':
    main()
