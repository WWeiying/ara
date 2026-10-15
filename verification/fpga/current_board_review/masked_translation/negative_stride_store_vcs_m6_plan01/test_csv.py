"""Host-only synthetic events with actual SoC PC/code and full independent oracle."""
import copy
import sys
from pathlib import Path
sys.dont_write_bytecode=True
import checker as c
import csv_check as cc
o=c.source

def synthetic(spec):
    s=spec['symbols'];code={int(k):v for k,v in spec['code'].items()};rows=[];checks=0;labels={}
    def emit(pc,rd=0,value=0,addr=0,rm=0,wm=0,data=0,trap=0,event='retire',tid=-1):
        rows.append(dict(zip(cc.FIELDS,map(str,[len(rows)*2+82,event,0,0,tid,f'{pc:016x}',f'{code[pc]:08x}',rd,
             f'{value&o.MASK64:016x}',f'{addr:016x}',f'{rm:02x}',f'{wm:02x}',f'{data&o.MASK64:016x}',trap]))))
    def setter(reg,lo=0,hi=1<<64):
        return next(p for p,i in code.items() if lo<=p<hi and i&127 in (0x13,0x17,0x1b) and (i>>7)&31==reg
                    and p not in sum((spec[k] for k in ('helper','unused','capacity')),[]) and p not in s.values())
    setters={r:setter(r) for r in (5,10,11,12,13,14,15,28)}
    def reg(r,v,inside=None):
        if r not in setters:setters[r]=setter(r)
        emit(setter(r,*inside) if inside else setters[r],rd=r,value=v)
    def instruction(kind,width,lo=0,hi=1<<64):
        for p,i in code.items():
            if not lo<=p<hi or p in spec['helper']+spec['unused'] or p in s.values():continue
            d=cc.memory_op(i,{})
            if d and d['kind']==kind and d['size']==width and d['base'] in setters and d['register'] in setters:return p,d
        raise ValueError('No actual instruction '+str((kind,width)))
    stores={w:instruction('write',w) for w in (1,2,8)}
    checksnap=next(v for k,v in s.items() if k.startswith('checksnap'))
    loadpc,ld=instruction('read',2,checksnap,s['mx_checkpoint'])
    def store(a,v,width=8,pc=None,inside=None):
        p,d=(pc,cc.memory_op(code[pc],{})) if pc else instruction('write',width,*inside) if inside else stores[width]
        reg(d['base'],a-d['offset'],inside);reg(d['register'],v,inside)
        emit(p,addr=a,wm=((1<<width)-1)<<(a%8),data=v)
    def load(a,v):
        reg(ld['base'],a-ld['offset']);emit(loadpc,rd=ld['register'],value=v,addr=a,rm=3<<(a%8))
    def oracle(total):
        nonlocal checks
        while checks<total:
            reg(10,0);reg(11,0);emit(s['check']);checks+=1;store(s['mx_checks'],checks)
    def csr_read(k,v):
        p=next(p for p,i in code.items() if s['mx_trap']<=p<s['main'] and i&0x707f==0x2073 and
               (i>>15)&31==0 and (i>>7)&31!=0 and i>>20==k)
        emit(p,rd=(code[p]>>7)&31,value=v)
    def csr_write(k,v):
        p=next(p for p,i in code.items() if s['mx_handler']<=p<s['mx_trap_mret'] and i&127==0x73 and (i>>12)&7==1 and i>>20==k)
        reg((code[p]>>15)&31,v);emit(p)
    def phase(p):
        reg(10,p);emit(s['check_memory'])
        for h in range(4096):load(s['mx_pages']+2*h,o.data(p,h))
        oracle(cc.COUNTS[p]);store(s['mx_phase'],p);labels['checkpoint'+str(p)]=len(rows);emit(s['mx_checkpoint'])
    def snapshot(name,phase):
        for r in range(3):
            p=next(p for p,i in code.items() if s['mx_snapshot']<=p<s['mx_handler'] and i&0x707f==0x5027 and (i>>7)&31==23+r)
            reg((code[p]>>15)&31,s[name]+64+128*r);emit(p)
        for r in range(3):
            for i in range(64):load(s[name]+64+128*r+2*i,o.vector(phase,r,i))
    def handler(n):
        emit(s['mx_handler'])
        values=[15 if n==0 else 9,s['fault_1_pc'] if n==0 else s['mx_ecall'],o.VA+4078 if n==0 else 0,
            0x800,(8<<60)|((s['mx_pages']+8192)>>12),8 if n==0 else 64,8,5 if n==0 else 0,117,5,n,
            (s['mx_pages']>>12<<10)|0xc7 if n else 0]
        for k,j in cc.CSR_FIELDS.items():csr_read(k,values[j])
        for j,v in enumerate(values):store(s['mx_records']+96*n+8*j,v)
        store(s['mx_count'],n+1)
    def args():
        for r,v in zip(range(10,16),[o.VA+4118,s['mx_input'],s['mx_out']+2,s['mx_mask'],64,s['mx_stride']]):reg(r,v)
    initial=o.expected(s,0)
    for a in sorted(initial):store(a,initial[a],1)
    store(s['mx_checks'],0);store(s['mx_completed'],0);store(s['mx_phase'],0)
    for p in spec['capacity']:emit(p,rd=10 if p==spec['capacity'][1] else 0,value=64 if p==spec['capacity'][1] else 0)
    phase(0)
    reg(11,(8<<60)|((s['mx_pages']+8192)>>12));emit(s['mx_enter_s']);args()
    h=spec['helper']
    for i in range(5):
        if i==2:emit(h[i],rd=28,value=o.MASK64-7,addr=s['mx_stride'],rm=255)
        else:emit(h[i],rd=5 if i in (0,4) else 0,value=8 if i==4 else 64 if i==0 else 0)
    emit(s['fault_1_pc'],event='cvx_req',tid=0)
    for e in ('arch_start','uop_alloc','uop_done'):emit(s['fault_1_pc'],event=e)
    emit(s['fault_1_pc'],event='cvx_resp',tid=0,trap=1)
    handler(0)
    p=s['mx_fault_prefix_read'];d=cc.memory_op(code[p],{})
    reg(d['base'],s['mx_pages']+4102-d['offset'])
    labels['prefix_read']=len(rows)
    emit(p,rd=d['register'],value=127,addr=s['mx_pages']+4102,rm=3<<6)
    store(s['mx_prefix_observed'],127)
    store(s['mx_restart'],5);snapshot('mx_fault',1);phase(1)
    store(s['mx_pages']+16384,(s['mx_pages']>>12<<10)|0xc7)
    p=s['mx_repair_sfence'];reg((code[p]>>15)&31,o.VA);emit(p)
    emit(s['mx_refill_page'])
    for hword in range(2048):store(s['mx_pages']+2*hword,o.original(hword),2,inside=(s['mx_refill_page'],s['mx_trap']))
    store(s['mx_pages']+4102,36,2);phase(2)
    p=next(p for p,i in code.items() if s['mx_handler']<=p<s['mx_trap_mret'] and i&0x707f==0x7057)
    reg(5,8);emit(p,rd=5,value=8);csr_write(8,5);args();reg(28,o.MASK64-7)
    labels['retry_mret']=len(rows);emit(s['mx_trap_mret'])
    emit(s['fault_1_pc'],event='cvx_req',tid=1)
    for e in ('arch_start','uop_alloc','uop_done'):
        emit(s['fault_1_pc'],event=e);rows[-1]['order']='1'
    emit(s['fault_1_pc'],event='cvx_resp',tid=1)
    emit(h[5]);emit(h[6],rd=10,value=0);emit(h[7],rd=5,value=64);emit(h[8]);emit(h[9])
    store(s['mx_return'],0)
    for j,v in enumerate([64,8,0,117,5,0]):store(s['mx_post']+8*j,v)
    snapshot('mx_result',3)
    store(s['mx_marker'],1,pc=s['mx_younger_store']);handler(1);emit(s['mx_trap_mret'])
    for i in list(range(1,65))+[0,65]+list(range(66,130)):
        labels['out'+str(i)]=len(rows)+1
        load(s['mx_out']+2*i,o.vector(3,1,i-1) if 1<=i<=64 else 0x5b)
    phase(3);oracle(17275);store(s['mx_completed'],o.DONE)
    store(0xd0000000,0,pc=spec['exit_store']);emit(spec['park'])
    return rows,labels

def run(rows,spec):
    q=cc.Checker(spec);order=0
    try:
        for n,r in enumerate(rows):
            row=dict(r,order=str(order) if r['event']=='retire' else r['order'],cycle=str(n*2+82))
            if r['event']=='retire':order+=1
            q.row(row)
        return q.finish()
    except (ValueError,KeyError,IndexError,TypeError) as e:return dict(status='REJECTED',error=str(e),row=q.rows,actions=q.actions,checks=q.calls)

def main(out):
    c.require(not out.exists(),'Fresh Host artifacts only');out.mkdir()
    spec=c.specification();rows,labels=synthetic(spec)
    positive=run(rows,spec)
    c.common.save(out/'positive.json',positive)
    c.require(positive['status']=='PASS_NEGATIVE_STRIDE_STORE_FULL_SINGLE',str(positive))
    negatives=[]
    mutations=[('store_source_output2','out3','rd_wdata','24'),('store_source_element5','out6','rd_wdata','0'),
               ('inactive_output','out4','rd_wdata','0'),('tail63','out64','rd_wdata','0'),
               ('guard0','out0','rd_wdata','0'),('guard65','out65','rd_wdata','0'),
               ('prefix_not_visible','prefix_read','rd_wdata','287a'),
               ('wrong_retry_encoding','retry_mret','insn','00000013')]
    for name,label,key,value in mutations:
        bad=list(rows);i=labels[label];bad[i]=dict(rows[i],**{key:value});r=run(bad,spec)
        c.require(r['status']=='REJECTED','Accepted '+name);negatives.append(dict(name=name,result=r))
    for name,label in (('missing_checkpoint','checkpoint2'),('missing_final_guard','out65')):
        bad=list(rows);del bad[labels[label]];r=run(bad,spec)
        c.require(r['status']=='REJECTED','Accepted '+name);negatives.append(dict(name=name,result=r))
    r=run(rows[:-3],spec);c.require(r['status']=='REJECTED','Missing CTRL accepted')
    negatives.append(dict(name='missing_CTRL',result=r))
    for name,select,modify in (
        ('missing_store_done',lambda x:x['event']=='uop_done',None),
        ('wrong_fault_opcode',lambda x:x['event']=='cvx_req',{'insn':'09c55c07'}),
        ('missing_prefix_observation',lambda x:int(x['pc'],16)==spec['symbols']['mx_fault_prefix_read'],None),
        ('prefix_store_replayed',lambda x:x['event']=='retire' and int(x['mem_addr'],16)==spec['symbols']['mx_pages']+4102 and int(x['mem_rmask'],16)!=0,{'rd_wdata':'7f'}),
        ('retry_store_wrong_ordinal',lambda x:x['event']=='retire' and int(x['mem_addr'],16)==spec['symbols']['mx_pages']+4078 and int(x['mem_rmask'],16)!=0,{'rd_wdata':'7f'}),
    ):
        bad=list(rows);indices=[i for i,x in enumerate(bad) if select(x)]
        c.require(bool(indices),'Missing actual fixture coordinate '+name)
        i=indices[-1] if name in ('prefix_store_replayed','retry_store_wrong_ordinal') else indices[0]
        if modify is None:del bad[i]
        else:bad[i]=dict(bad[i],**modify)
        r=run(bad,spec);c.require(r['status']=='REJECTED','Accepted '+name)
        negatives.append(dict(name=name,result=r))
    pins={str(p):c.sha(p) for p in (Path(__file__),Path(cc.__file__),Path(c.__file__),c.REF/'READY.json')}
    c.common.save(out/'status.json',dict(status='PASS_HOST_ONLY_NOT_DUT',synthetic=True,
        actual_soc_elf_sha256=spec['elf_sha256'],rows=len(rows),positive=positive,negatives=negatives,pins=pins))
    print('PASS_HOST_ONLY_NOT_DUT',len(rows),'synthetic rows',len(negatives),'negative fixtures')

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args().out)
