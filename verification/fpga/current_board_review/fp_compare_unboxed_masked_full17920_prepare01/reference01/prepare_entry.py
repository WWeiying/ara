"""Derive actual new PC spec; reuse short tests; seal once, never run Spike."""
import importlib.util
import json
from pathlib import Path
import sys
from execute import save,sha,wait

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent;ROOT=HERE.parent
OLD=ROOT.parent/'fp_compare_unboxed_full17920_prepare01'


def main():
    assert not (HERE/'spec.json').exists()
    ready=json.loads((ROOT/'SOFTWARE_READY.json').read_text())
    assert sha(ROOT/'SOFTWARE_READY.json')=='e51ea7eea21acac640db20c1c6fd0a85e47823a7cdfd31270e85c12078bec5f4'
    pins=dict(ready['pins'])
    assert all(sha(p)==v for p,v in pins.items())
    p=OLD/'compile01/inspect_linked.py'
    sp=importlib.util.spec_from_file_location('immutable_masked_spec_parser',p)
    parser=importlib.util.module_from_spec(sp);sp.loader.exec_module(parser)
    parser.RUN=ROOT/'build01'
    directory,code,functions,symbols,sizes=parser.parse('spike')
    name='fp_compare_unboxed_masked_e16_mf4_full17920_main'
    lower=json.loads((ROOT/'linked01/spike.json').read_text())
    assert sha(directory/'program.elf')==ready['backends']['spike']['elf_sha256']
    helpers=[functions['op_'+str(i)] for i in range(10)]
    proof=json.loads((ROOT/'helper_identity.json').read_text())['helpers']
    assert [r['insn'] for r in functions['capacity']]==proof[0]['codes']
    assert [[r['insn'] for r in h] for h in helpers]==[h['codes'] for h in proof[1:]]
    def one(fn,op,args):
        rows=[r for r in functions[fn] if r['op']==op and r['args'].split(' #')[0]==args]
        assert len(rows)==1,(fn,op,args)
        return rows[0]['pc']
    opaque=[]
    for fn in (name,'main'):
        for r in functions[fn]:
            if r['op']=='jal':break
            if r['op']=='sd' and '(sp)' in r['args'] and r['args'].split(',')[0] not in ('ra','zero'):
                opaque.append(r['pc'])
    prelude=[r['pc'] for fn in ('_start','main') for r in functions[fn]
             if int(r['insn'],16)&127==0x73 and (int(r['insn'],16)>>12)&7]
    assert [int(code[pc]['insn'],16) for pc in prelude]==[0x30401073,0x30529073,0x3002a073,0x00305073,0x00805073,0xc2202773]
    failures=set(map(int,lower['failure_PCs']))
    for fn in ('trap_entry','replay_trap','hex'):failures.update(r['pc'] for r in functions[fn])
    for lo,hi in ((0x80000744,0x80000750),(0x80000772,0x80000780)):
        failures.update(pc for pc in code if lo<=pc<=hi)
    # All other inherited fixed locations are independently checked in this ELF.
    assert one(name,'ld','t0,56(sp)')==0x80000236
    assert one(name,'or','a4,a4,t0')==0x80000240
    assert code[0x80000046]['insn']=='0002b023' and code[0x8000004e]['op']=='jal'
    spec=dict(elf=str(directory/'program.elf'),elf_sha256=sha(directory/'program.elf'),
        symbols=symbols,sizes=sizes,code=code,helpers=helpers,capacity=functions['capacity'],
        stores=lower['fresh_store_sites'],input_loads=lower['input_LD_sites'],
        record_load=one(name,'ld','s6,0(a5)'),output_read=one(name,'lwu','s0,0(s0)'),
        exit_store=one('replay_exit','sd','a0,0(t0)'),park=one('replay_exit','j','8000007e <replay_exit+0x16>'),
        prelude=prelude,opaque_initial_spills=opaque,failure_pcs=sorted(failures),
        BSS_bytes=symbols['__bss_end']-symbols['__bss_start'])
    save(HERE/'spec.json',spec)
    oldtests=(OLD/'reference_entry02/test_checker.py').read_text().replace("'2240'","'8960'")
    (HERE/'test_mature.py').write_text(oldtests)
    actual=wait([sys.executable,'-B',str(HERE/'test_short.py')],HERE/'host',120)
    assert actual['actual_wait_exit']==0 and not actual['timed_out'],'Short Host failure, no retry'
    spike=Path('/home/wangwy/openproject/riscv-isa-sim-ara-dsa-vstart/build/spike')
    extras=[ROOT/'SOFTWARE_READY.json',ROOT/'REPORT.md',OLD/'reference_entry02/checker.py',
        OLD/'reference_entry02/test_checker.py',ROOT/'model.json',spike,
        HERE/'spec.json',HERE/'host.wait.json',HERE/'host.log',HERE/'host.command.json',
        Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/coverage/scoped_rv64c_memory.py')]
    extras+=list(HERE.glob('*.py'))
    for p in extras:pins[str(p)]=sha(p)
    assert all(sha(p)==v for p,v in pins.items())
    save(HERE/'input_pins.json',pins)
    save(HERE/'ENTRY.json',dict(status='MASKED_REFERENCE_PREPARED_NOT_EXECUTED',
        input_pins_sha256=sha(HERE/'input_pins.json'),spec_sha256=sha(HERE/'spec.json'),
        spike=str(spike),calls=17920,record_LD=8960,firmware_limit=3000000,
        reference_seconds=120,raw_limit_bytes=768*1024*1024,audit_seconds=600,
        debug_command='rs 4000000\nquit\n',host_wait_sha256=sha(HERE/'host.wait.json'),
        pin_count=len(pins),actual_parent_authorization='Current parent message: one reviewed complete masked reference, not VCS',
        required_review_status='NO_BLOCKER_MASKED_FULL17920_REFERENCE_ONCE',retry=False,DUT_authorized=False))
    print('ENTRY',sha(HERE/'ENTRY.json'),'pins',len(pins),flush=True)


if __name__=='__main__':main()
