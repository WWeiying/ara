#!/usr/bin/env python3
"""Original682 scalar-only packed oracle successor, never launches DUT."""
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import sys
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
OLD = HERE.parent/'prepared02'
CASE = OLD/'prepared/alias_v8_e16m8_prefix682'
UTIL = HERE.parent/'full682_optimized_compile01/measure02.py'
sp = importlib.util.spec_from_file_location('cost_util', UTIL)
u = importlib.util.module_from_spec(sp)
sp.loader.exec_module(u)


def write(path, text):
    with path.open('x') as f:
        f.write(text)


def main():
    run=HERE/'run01'; run.mkdir()
    fixture=(CASE/'original/fixtures.h').read_text()
    inputs=[int(x,16) for x in re.findall(r'UINT64_C\(0x([0-9a-f]+)\)', fixture)]
    expected=json.loads(fixture.split('expected[6][16][16]=',1)[1].split(';',1)[0].replace('{','[').replace('}',']'))
    assert len(inputs)==16 and len(expected)==6
    seq=json.loads((CASE/'call_sequence.json').read_text())
    assert len(seq)==682
    rows=[]; records=[]
    for c in seq:
        seed,op,vl=c['seed'],c['op'],c['vl']
        assert c['vstart']==0
        a=[inputs[(i+seed+7*(seed//16))%16] for i in range(512)]
        b=[inputs[(i*3+seed*5+seed//16)%16 if op<4 else seed%16] for i in range(512)]
        indices=[]
        for values in (a,b):
            row=tuple(sum(values[i+j]<<(16*j) for j in range(4)) for i in range(0,512,4))
            if row not in rows: rows.append(row)
            indices.append(rows.index(row))
        zero=[0]*64; one=[0]*64; flags=c['sticky']
        for i in range(512):
            ai=(i+seed+7*(seed//16))%16
            bi=(i*3+seed*5+seed//16)%16 if op<4 else seed%16
            bit,fl=expected[op if op<4 else op-4][ai][bi]
            old=(a[i//16]>>(i%16))&1
            if i<vl:
                allowed={bit}; flags|=fl
            elif vl==0: allowed={old}
            else: allowed={old,1,bit}
            if 1 not in allowed: zero[i//8]|=1<<(i%8)
            if 0 not in allowed: one[i//8]|=1<<(i%8)
        records.append((seed,op,vl,c['mask'],c['sticky'],*indices,flags,zero,one))
    header='static const uint64_t input_rows[][128]={\n'
    header+='\n'.join('{'+','.join('UINT64_C('+hex(v)+')' for v in r)+'},' for r in rows)+'\n};\n'
    header+='struct packed_case {uint16_t seed,op,vl,mode,sticky,ai,bi,flags; uint8_t zero[64],one[64];};\n'
    header+='static const struct packed_case packed_cases[682]={\n'
    for r in records:
        header+='{'+','.join(map(str,r[:8]))+',{'+','.join(map(str,r[8]))+'},{'+','.join(map(str,r[9]))+'}},\n'
    header+='};\n'
    write(run/'tables.h',header)
    source=(CASE/'case.c').read_text()
    source=source.replace('#include "fixtures.h"','#include "tables.h"\ntypedef uint64_t alias64 __attribute__((__may_alias__));')
    source=source.replace('static word a[1024],b[1024];','static word a[1024] __attribute__((aligned(8))),b[1024] __attribute__((aligned(8)));')
    begin=source.index('static unsigned bit('); end=source.index('int alias_',begin)
    source=source[:begin]+source[end:]
    source=source.replace('if(!cap || cap>1024)','if(cap!=512)')
    begin=source.index('        for(unsigned i=0;i<cap;++i) {')
    end=source.index('        for(unsigned i=0;i<130;++i)',begin)
    source=source[:begin]+'''        const struct packed_case *pc=&packed_cases[cases];
        if(pc->seed!=seed || pc->op!=op || pc->vl!=vl || pc->mode!=mode || pc->sticky!=sticky) return 3;
        for(unsigned i=0;i<128;++i) {
            ((alias64 *)a)[i]=input_rows[pc->ai][i];
            ((alias64 *)b)[i]=input_rows[pc->bi][i];
        }
'''+source[end:]
    begin=source.index('        for(unsigned i=0;i<cap;++i) {')
    end=source.index('        if((status>>32)!=flags)',begin)
    source=source[:begin]+'''        for(unsigned i=0;i<64;++i) {
            unsigned actual=output[i+1];
            if((actual&pc->zero[i]) | ((~actual)&pc->one[i])) ++errors;
        }
        flags=pc->flags;
'''+source[end:]
    write(run/'case.c',source)
    pins={str(p):u.sha(p) for p in [Path(__file__),HERE/'host.c',UTIL,CASE/'case.c',
          CASE/'call_sequence.json',CASE/'original/fixtures.h',CASE/'original/scenario.S',
          CASE/'original/operations.h',run/'case.c',run/'tables.h']}
    commands={}
    for backend in ('soc','spike'):
        path=OLD/backend/(u.NAME+'.compile.log.command.json')
        pins[str(path)]=u.sha(path)
        argv=json.loads(path.read_text())
        for token in argv:
            if Path(token).is_file():pins[token]=u.sha(token)
        argv[argv.index('-Os')]='-O2'
        argv[argv.index(str(CASE/'case.c'))]=str(run/'case.c')
        argv[argv.index('-o')+1]=str(run/(backend+'.elf'))
        commands[backend]=argv
    u.save(run/'input_pins.json',pins)
    u.command(['gcc','-O2','-Wall','-Wextra','-Werror','-I'+str(CASE/'original'),'-I'+str(run),
               HERE/'host.c','-o',run/'host'],run/'host_compile',120)
    u.command([run/'host'],run/'host',120)
    for backend,argv in commands.items():
        u.command(argv,run/(backend+'_compile'),120)
        _,blocks=u.disassemble(run/(backend+'.elf'),argv[0],run/(backend+'_dis'))
        _,orig=u.disassemble(OLD/backend/(u.NAME+'.elf'),argv[0],run/(backend+'_old_dis'))
        helpers=['capacity']+['op_'+str(i) for i in range(10)]
        assert all(blocks[h]==orig[h] for h in helpers)
        for name,words in blocks.items():
            if name in helpers:continue
            for w in words:
                insn=int(w,16)
                assert not (len(w)==8 and ((insn&127)==87 or
                     ((insn&127) in (7,39) and ((insn>>12)&7) in (0,5,6,7)))),(name,w)
        nm=Path(argv[0]).with_name(Path(argv[0]).name.removesuffix('gcc')+'nm')
        u.command([nm,'-n',run/(backend+'.elf')],run/(backend+'_nm'),30)
    sym=dict((name,int(pc,16)) for pc,_,name in re.findall(r'^([0-9a-f]+)\s+(\w)\s+(\S+)$',
             (run/'spike_nm.log').read_text(),re.M))
    assert sym['__bss_end']<sym['__stack_top']-65536 and sym['__stack_top']==0x800ffff0
    debug=run/'spike.cmd'
    write(debug,'until pc 0 '+hex(sym['_start'])+'\nreg 0 minstret\nuntil pc 0 '+hex(sym['replay_exit'])+
          '\nreg 0 minstret\nreg 0 a0\nstr '+hex(sym['replay_log'])+'\nrs\n')
    u.save(run/'execution_pins.json',{str(p):u.sha(p) for p in [run/'soc.elf',run/'spike.elf',
           debug,u.SPIKE,run/'input_pins.json',run/'host',run/'host.log']})
    outcome=u.command([u.SPIKE,'-d','--debug-cmd='+str(debug),'--isa=rv64gcv_zvfh_zvl1024b',
                       '-m2',run/'spike.elf'],run/'spike_cost',180)
    log=(run/'spike_cost.log').read_text()
    values=[int(v,16) for v in re.findall(r'^0x([0-9a-f]+)$',log,re.M)]
    assert len(values)==3 and values[2]==0 and values[1]>values[0]
    assert 'RVV_FP_COMPARE_PASS sew=16 cases=682 errors=0' in log
    assert not re.search(r'RVV_FP_COMPARE_(FAIL|DETAIL|CAPACITY_FAIL)',log)
    assert all(u.sha(p)==h for p,h in pins.items())
    retired=values[1]-values[0]; rate=4529502/7544.534202890936
    result=dict(status='HOST_EXHAUSTIVE_AND_SPIKE_COST_PASS_NOT_DUT_ADMISSION',calls=682,
       source_result_bits=349184,guards=1364,flags_checks=682,vstart_checks=682,
       unique_input_rows=len(rows),input_rom_bytes=len(rows)*1024,case_table_bytes=682*144,
       bss_end=hex(sym['__bss_end']),stack_top=hex(sym['__stack_top']),stack_reserve=65536,
       unchanged_helpers=True,no_new_vector_instructions=True,pins_unchanged=True,
       retired=retired,process=outcome,nominal_s=retired/rate,margin20_s=1.2*retired/rate,
       within_budget_projection=1.2*retired/rate<=10800,
       limitations='Debugger cost run is not full dynamic helper/input/history audit; no worker/checker prepared; no DUT authorized by this report.')
    u.save(run/'result.json',result); print(json.dumps(result,indent=2))


if __name__=='__main__':main()
