"""Host-only full16 synthetic RVFI using actual SoC PC/code, never DUT evidence."""
import copy
import json
import sys
from pathlib import Path
sys.dont_write_bytecode=True
import checker as c
import csv_check as cc
o=c.source

def synthetic(spec):
    s=spec['symbols'];code={int(k):v for k,v in spec['code'].items()};rows=[];labels={};checks=0
    protected=set(sum(spec['windows'].values(),[])+spec['bootstrap'])
    def emit(pc,rd=0,value=0,a=0,rm=0,wm=0,data=0,trap=0,event='retire',tid=-1,order=0):
        rows.append(dict(zip(cc.FIELDS,map(str,[0,event,order,0,tid,f'{pc:016x}',f'{code[pc]:08x}',rd,
          f'{value&o.MASK64:016x}',f'{a:016x}',f'{rm:02x}',f'{wm:02x}',f'{data&o.MASK64:016x}',trap]))))
    def setter(reg,lo=0,hi=1<<64):
        return next(p for p,i in code.items() if lo<=p<hi and p not in protected and p not in s.values() and
                    i&127 in (0x13,0x17,0x1b,0x33,0x37) and (i>>7)&31==reg)
    def reg(r,v,inside=None):emit(setter(r,*(inside or (0,1<<64))),rd=r,value=v)
    def memop(kind,width,inside=None):
        lo,hi=inside or (0,1<<64)
        for p,i in code.items():
            if not lo<=p<hi or p in protected or p in s.values():continue
            d=cc.memory_op(i,{})
            if d and d['kind']==kind and d['size']==width and d['base'] and d['register']:
                try:setter(d['base'],lo,hi);setter(d['register'],lo,hi)
                except StopIteration:continue
                return p,d
        raise ValueError('Missing real memory instruction '+str((kind,width,inside)))
    storeops={w:memop('write',w) for w in (1,8)};lp,ld=memop('read',8)
    def store(a,v,w=8,pc=None,inside=None):
        p,d=(pc,cc.memory_op(code[pc],{})) if pc else memop('write',w,inside) if inside else storeops[w]
        reg(d['base'],a-d['offset'],inside);reg(d['register'],v,inside)
        emit(p,a=a,wm=((1<<w)-1)<<(a%8),data=v)
    def load(a,v,label=None):
        reg(ld['base'],a-ld['offset'])
        if label:labels[label]=len(rows)
        emit(lp,rd=ld['register'],value=v,a=a,rm=255)
    def materialize(m):
        keys=sorted(m);at=0
        while at<len(keys):
            a=keys[at];w=8 if a%8==0 and keys[at:at+8]==list(range(a,a+8)) else 1
            store(a,int.from_bytes(bytes(m[a+j] for j in range(w)),'little'),w);at+=w
    def oracle(n):
        nonlocal checks
        while checks<n:
            reg(10,0);reg(11,0);emit(s['check']);checks+=1;store(s['mx_checks'],checks)
    def point(case,p):
        oracle(cc.POINTS[case,p]);store(s['mx_phase'],p);labels[f'point{case}_{p}']=len(rows);emit(s['mx_checkpoint'])
    def csrread(k,v):
        p=next(p for p,i in code.items() if s['mx_trap']<=p<s['main'] and i&0x707f==0x2073 and
               (i>>15)&31==0 and (i>>7)&31 and i>>20==k)
        emit(p,rd=(code[p]>>7)&31,value=v)
    def csrwrite(k,v):
        p=next(p for p,i in code.items() if s['mx_handler']<=p<s['mx_trap_mret'] and i&0x707f==0x1073 and i>>20==k)
        reg((code[p]>>15)&31,v);emit(p)
    def args():
        for r,v in zip(range(10,16),o.args(s)):reg(r,v)
    def snapshot(name):
        p=next(p for p,i in code.items() if s['mx_snapshot']<=p<s['mx_handler'] and i&0x707f==0x7027)
        reg((code[p]>>15)&31,s[name]+64);emit(p)
    def handler(case,finish):
        emit(s['mx_handler']);u,st,m=o.config(case);fault=m<3;n=int(fault) if finish else 0
        pte=lambda a,f:(a>>12<<10)|f
        v=[9 if finish else 15 if st else 13,s['mx_ecall'] if finish else s[f'fault_{st}_pc'],0 if finish else o.VA+4096,
           0x800,(8<<60)|((s['mx_pages']+8192)>>12),64 if finish else 8,26,0 if finish else m,0,0,int(finish),
           pte(s['mx_pages']+4096,0xc7) if finish and fault else 0 if u else pte(s['mx_pages']+4096,1)]
        for k in (8,0xc21,0xc20,0x342,0x341,0x343,0x300,0x180,3,15):csrread(k,v[cc.CSR_FIELDS[k]])
        for j,x in enumerate(v):store(s['mx_records']+case*192+n*96+8*j,x)
        store(s['mx_count'],n+1)
    def repair(case):
        store(s['mx_pages']+16384+8,((s['mx_pages']+4096)>>12<<10)|0xc7)
        reg((code[s['mx_repair_sfence']]>>15)&31,o.VA+4096);emit(s['mx_repair_sfence'])
        if case>=8:
            emit(s['mx_refill_page'])
            for i in range(512):store(s['mx_pages']+4096+8*i,37*(512+i)+11,inside=(s['mx_refill_page'],s['restore_page']))
            emit(s['restore_page']+4)
    arch=0
    def target(case,fault):
        nonlocal arch
        p=s[f'fault_{(case//4)%2}_pc'];emit(p,event='cvx_req',tid=0)
        for e in ('arch_start','uop_alloc','uop_done'):emit(p,event=e,order=arch)
        emit(p,event='cvx_resp',tid=0,trap=int(fault));arch+=1
        if not fault:emit(p)
    materialize(o.expected(s,0,0));store(s['mx_checks'],0);store(s['mx_completed'],0)
    for p in spec['windows']['capacity']:emit(p,rd=10 if p==spec['windows']['capacity'][1] else 0,value=64)
    reg(15,s['mx_action_source']);reg(11,s['mx_action_copy'])
    for i,p in enumerate(spec['bootstrap']):emit(p)
    for case in range(16):
        if case:
            m=o.expected(s,case,0)
            for a in range(s['mx_action_copy'],s['mx_action_copy']+24):m.pop(a,None)
            materialize(m)
        point(case,0);reg(11,(8<<60)|((s['mx_pages']+8192)>>12));emit(s['mx_enter_s']);args()
        h=spec['windows'][f'replay_{(case//4)%2}']
        for i in range(5):
            if i==2:emit(h[i],rd=28,value=0,a=s['mx_stride'],rm=255)
            else:emit(h[i],rd=5 if i in (0,4) else 0,value=8 if i==4 else 64)
        if case%4<3:
            target(case,True);handler(case,False)
            store(s['mx_signals'],sum(j%4<3 for j in range(case+1)));store(s['mx_restart'],case%4)
            snapshot('mx_fault')
            for i in range(case%4):load(s['mx_fault']+64+i*8,101 if (case//4)%2 else 91)
            point(case,1);repair(case);point(case,2)
            p=next(p for p,i in code.items() if s['mx_handler']<=p<s['mx_trap_mret'] and i&0x707f==0x7057)
            reg(5,8);emit(p,rd=5,value=8);csrwrite(8,case%4);args()
            labels[f'retry{case}']=len(rows);emit(s['mx_trap_mret'])
        target(case,False)
        emit(h[6],rd=10,value=0);emit(h[7],rd=5,value=64);emit(h[8]);emit(h[9])
        store(s['mx_return'],0)
        for j,v in enumerate((64,26,0,0,0,0)):store(s['mx_post']+case*48+j*8,v)
        snapshot('mx_result');store(s['mx_marker'],1,pc=s['mx_younger_store'])
        emit(s['mx_ecall'],trap=1);handler(case,True);emit(s['mx_trap_mret']);point(case,3)
        if case%4==3:repair(case)
        for i in range(64):
            load(s['mx_out']+(i+1)*8,o.vector(case,i),f'out{case}_{i}')
            load(s['mx_result']+64+i*8,o.vector(case,i))
        for i in range(1024):load(s['mx_pages']+8*i,o.data(case,4,i),f'mem{case}_{i}' if i in (0,512,1023) else None)
        load(s['mx_out'],91,f'guard{case}_0');load(s['mx_out']+65*8,91,f'guard{case}_65');point(case,4)
    oracle(19212);store(s['mx_completed'],o.DONE);store(0xd0000000,0,pc=spec['exit_store']);emit(spec['park'])
    retired=0
    for i,r in enumerate(rows):
        r['cycle']=str(i*2+82)
        if r['event']=='retire':r['order']=str(retired);retired+=1
    return rows,labels

def main(out):
    c.require(not out.exists(),'Fresh Host output only');out.mkdir()
    spec=c.specification();rows,labels=synthetic(spec);q=cc.Checker(spec);states={}
    selected=('out0_0','out1_0','out0_63','guard0_0','guard15_65','mem4_512','mem7_512',
              'mem15_1023','retry2','out15_63','point15_4')
    indices={labels[x] for x in selected}
    try:
        for i,r in enumerate(rows):
            if i in indices:states[i]=copy.deepcopy(q)
            q.row(r)
        positive=q.finish()
    except Exception as e:
        c.common.save(out/'positive_failure.json',dict(error=str(e),row=q.rows,case=q.case,checks=q.calls,step=q.step));raise
    c.common.save(out/'positive.json',positive)
    changes=[('load_wrong','out0_0','rd_wdata','0'),('typed_seed','out1_0','rd_wdata','5b5b5b5b5b5b5b5b'),
      ('tail63','out0_63','rd_wdata','0'),('guard_low','guard0_0','rd_wdata','0'),('guard65','guard15_65','rd_wdata','0'),
      ('active_store','mem4_512','rd_wdata','0'),('alloff_store','mem7_512','rd_wdata','65'),
      ('last_memory','mem15_1023','rd_wdata','0'),('wrong_retry_encoding','retry2','insn','00000013'),
      ('missing_output_observation','out15_63','mem_rmask','00')]
    negative=[]
    for name,label,key,value in changes:
        i=labels[label];bad=copy.deepcopy(states[i]);rejected=None
        try:
            bad.row(dict(rows[i],**{key:value}))
            for r in rows[i+1:]:bad.row(r)
            bad.finish()
        except (ValueError,KeyError,IndexError,TypeError) as e:rejected=str(e)
        c.require(rejected is not None,'Accepted '+name);negative.append(dict(name=name,error=rejected))
    bad=copy.deepcopy(states[labels['point15_4']])
    try:bad.finish()
    except ValueError as e:negative.append(dict(name='missing_final_case_oracle_and_CTRL',error=str(e)))
    else:raise ValueError('Truncated full16 accepted')
    text='ZERO_STRIDE_ORIGINAL16_PASS cases=16 faults=12 errors=0\nCore Test *** SUCCESS *** (tohost = 0)\n$finish\n'
    c.console_gate(text)
    for bad in ('ZERO_STRIDE_ORIGINAL16_FAIL','BOARD_REPLAY_MISMATCH case0',text.replace('cases=16','cases=15'),text+'FAIL'):
        try:c.console_gate(bad)
        except ValueError:negative.append(dict(name='raw_console_veto',rejected=True))
        else:raise ValueError('Console veto missed')
    c.require(c.runtime_case(dict(id=c.NAME,original_name=c.HISTORICAL))['original_name']==c.NAME,'Runtime map')
    for bad in (dict(id=c.HISTORICAL,original_name=c.HISTORICAL),dict(id=c.NAME,original_name=c.NAME)):
        try:c.runtime_case(bad)
        except ValueError:negative.append(dict(name='runtime_historical_name_mix',rejected=True))
        else:raise ValueError('Runtime/provenance mix accepted')
    pins={str(p):c.sha(p) for p in (Path(__file__),Path(cc.__file__),Path(c.__file__),c.REF/'READY.json')}
    c.common.save(out/'status.json',dict(status='PASS_HOST_ONLY_NOT_DUT',synthetic=True,rows=len(rows),
      positive=positive,negative=negative,pins=pins,actual_soc_elf_sha256=spec['elf_sha256']))
    print('PASS_HOST_ONLY_NOT_DUT',len(rows),len(negative))
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args().out)
