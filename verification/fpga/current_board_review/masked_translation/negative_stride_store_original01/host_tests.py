#!/usr/bin/env python3
"""Final observer Host gates. No compiler, Spike, service or DUT invocation."""
import sys
sys.dont_write_bytecode=True
import prepare as p
import observer as o

def main():
    s=p.read(p.OUT/'spike.symbols.json')
    report=p.host_negatives(s)
    report['compiled_host_oracle_rows']=o.host_check((p.OUT/'host.stdout').read_text())
    initial=o.elf_bytes(p.OUT/'spike.elf')
    o.require(o.readint(initial,s['mx_stride'])==o.MASK64-7,'Actual initialized stride')
    o.require(s['mx_out'] not in initial,'BSS must be observed, not synthesized from ELF')
    regs=dict(zip(range(10,16),[o.VA+4118,s['mx_input'],s['mx_out']+2,s['mx_mask'],64,s['mx_stride']]))
    regs[28]=o.MASK64-7
    csr={0x341:s['fault_1_pc'],8:5,0xc20:8,0xc21:8,0x300:0x800}
    o.retry_context(s,regs,csr)
    mutations=[('double_offset_base','r',10,o.VA+4078),('unsigned_stride','r',28,8),
               ('wrong_output','r',12,s['mx_out']),('wrong_mask','r',13,s['mx_mask']+1),
               ('restart0','c',8,0),('skip8','c',8,8),('reenter_helper','c',0x341,s['replay_1']),
               ('load_target','c',0x341,s['fault_0_pc']),
               ('wrong_vl','c',0xc20,64),('wrong_privilege','c',0x300,0x1800)]
    for name,which,k,v in mutations:
        r,c=dict(regs),dict(csr)
        (r if which=='r' else c)[k]=v
        try:o.retry_context(s,r,c)
        except ValueError:report['negative'].append(dict(name=name,rejected=True));continue
        raise ValueError('Accepted wrong retry '+name)
    o.target_access(0,[(o.VA+4102,127)]);o.target_access(1,[(o.VA+4078,166)])
    for name,attempt,access in [
        ('load_instead_of_store',0,[(o.VA+4102,None)]),
        ('inactive_write',0,[(o.VA+4102,127),(o.VA+4094,140)]),
        ('wrong_store_ordinal',1,[(o.VA+4078,127)]),
        ('replay_prefix',1,[(o.VA+4102,127),(o.VA+4078,166)]),
        ('missing_store',1,[]),('extra_attempt',2,[(o.VA+4078,166)]),
    ]:
        try:o.target_access(attempt,access)
        except ValueError:report['negative'].append(dict(name=name,rejected=True));continue
        raise ValueError('Accepted wrong store '+name)
    code=o.disassemble((p.OUT/'spike.dis').read_text())
    o.require(code[s['fault_1_pc']]==0x09c55c27,'Actual store target encoding')
    report['actual_spec_store']=dict(target_pc=hex(s['fault_1_pc']),encoding='09c55c27',
                                    helper_instructions=len(o.window(code,s['replay_1'],10)))
    report.update(status='HOST_PASS_NOT_REFERENCE',negative_count=len(report['negative']),
                  pins={str(p.HERE/n):p.sha(p.HERE/n) for n in ('observer.py','prepare.py','host_tests.py')})
    p.save(p.HERE/'host_final01.json',report)
    print('HOST_PASS',report['compiled_host_oracle_rows'],'rows',report['negative_count'],'negative controls')

if __name__=='__main__':main()
