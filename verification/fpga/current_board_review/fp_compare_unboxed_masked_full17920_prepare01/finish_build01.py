"""Continue after proven missing UBSan runtime; no completed Host/SoC retry."""
import json
from pathlib import Path
from prepare import HERE, sha, save
from build import command, CC, FLAGS, DEFS

out=HERE/'finish01'
assert not out.exists()
out.mkdir()
run=HERE/'build01';host=run/'host';source=HERE/'source'
failure=json.loads((host/'compile_ubsan.wait.json').read_text())
assert failure['actual_wait_exit']==1 and not failure['timed_out']
assert 'cannot find /usr/lib64/libubsan.so.1.0.0' in (host/'compile_ubsan.log').read_text()
pins=json.loads((run/'inputs_before.json').read_text())
pins[str(Path(__file__))]=sha(Path(__file__))
assert all(sha(p)==h for p,h in pins.items())
save(out/'inputs_before.json',pins)
tests={}
for mode in ['positive','legal_tailones','details','alloff_spurious_NV','active_missing_NV','inactive_result',
             'missing_input_store','missing_mask_store','missing_output_tail','wrong_raw_seed','wrong_record_mode']:
    receipt=json.loads((host/(mode+'.wait.json')).read_text())
    expected=0 if mode in ('positive','legal_tailones','details','alloff_spurious_NV','active_missing_NV','inactive_result') else -6
    assert receipt['actual_wait_exit']==expected and not receipt['timed_out']
    tests[mode]=dict(receipt=receipt,sha256=sha(host/(mode+'.wait.json')))
save(out/'ENVIRONMENT_CAUSE.json',dict(original_failure=failure,
    cause='Missing host libubsan shared and static runtime; source/equivalence did not fail',
    successor='GCC undefined instrumentation with trap-on-error, no external UBSan runtime',
    old_Host_repeated=False, SoC_Spike_compiles_previously_run=0))
command(['/usr/bin/gcc','-O2','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-const-variable',
    *DEFS,'-I'+str(host),'-I'+str(source/'original'),host/'host.c',source/'original_host.c',
    '-fsanitize=undefined','-fsanitize-undefined-trap-on-error','-o',out/'host_ubtrap'],out/'compile_ubtrap')
for mode in ('positive','alloff_spurious_NV'):
    tests['ubtrap_'+mode]=command([out/'host_ubtrap',mode],out/('ubtrap_'+mode),timeout=30)
save(out/'HOST_RESULT.json',dict(status='FULL_ORIGINAL_C_EQ_HOST_AND_UBTRAP_PASS',tests=tests,
    native_full_pairs=6, target_negatives=5, ubtrap_full_pairs=2, full_calls_each=17920,
    original_runtime_link_failure_preserved=True, source_unchanged=True, no_ISA_reference=True))
binaries={}
for backend in ('soc','spike'):
    dest=run/backend
    assert not dest.exists(),'No backend compiler retry'
    dest.mkdir();elf=dest/'program.elf'
    extra=['-DSPIKE_REFERENCE=1'] if backend=='spike' else []
    command([CC,*FLAGS,*DEFS,*extra,'-T',source/'replay.ld','-Wl,-Map='+str(dest/'program.map'),
        '-I'+str(source/'original'),source/'case.c',source/'original/scenario.S',source/'main.c',
        source/'startup.S',source/'runtime.c','-lgcc','-o',elf],dest/'compile')
    for tool,args,label in [('objdump',['-d'],'disassemble'),('nm',['-S','-n'],'symbols'),('readelf',['-l','-A'],'layout')]:
        command([CC.with_name('riscv64-unknown-elf-'+tool),*args,elf],dest/label)
    binaries[backend]=dict(path=str(elf),sha256=sha(elf))
assert all(sha(p)==h for p,h in pins.items())
save(out/'RESULT.json',dict(status='DUAL_COMPILED_PENDING_LINKED_COST',binaries=binaries,
    inputs_unchanged=True, original_ubsan_link_failure_preserved=True,
    reference_executed=False,DUT_executed=False))
print(json.dumps(binaries),flush=True)
