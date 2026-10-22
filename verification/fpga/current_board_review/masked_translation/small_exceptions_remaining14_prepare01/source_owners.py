"""Source-bound memory owners following the M9 alignment successor pattern.

Adds lifecycle presence to the sealed data oracle; no source/oracle reduction.
"""
import csv
from pathlib import Path
import csv_check as old
need=old.require
import observer as o

def memory(op):
    return op & 127 in (7,39) and (op>>12)&7 in (0,5,6,7)

def recipe(spec):
    code={int(k):v for k,v in spec['code'].items()}
    width={8:0,16:5,32:6}[spec['sew']]<<12
    sites=[('old_vd',1,0x02058c07|width),('mask',2,0x02b60007),
           ('target',3,(0x00050c07 if spec['scenario'] in (1,3) else 0x01050c07)|width),
           ('result',9,0x02058c27|width)]
    result=[]
    for name,i,op in sites:
        pc=spec['helper'][i]
        need(code[pc]==op and memory(op),'Exact source memory instruction')
        result.append(dict(site=name,pc=pc,insn=op,vl=8,vtype=o.spec_values(spec['sew'],spec['scenario'])['vtype'],vstart=0))
    need([pc for pc in spec['helper'] if memory(code[pc])]==[x['pc'] for x in result],
         'All four original helper memory sites')
    return result

class MemoryOwners:
    def __init__(self,spec):
        self.expected=recipe(spec)
        self.s=spec['symbols']
        self.cfg=o.spec_values(spec['sew'],spec['scenario'])
        self.scenario=spec['scenario']
        self.arch={};self.owners=[];self.active={};self.requests={}
        self.request_count=0;self.retired=[]

    def row(self,r,regs,csrs,mem):
        event,op=r['event'],int(r['insn'],16)
        seq,tid,vid,cycle=(int(r[k]) for k in ('order','trans_id','port','cycle'))
        if event=='arch_start':
            need(seq==len(self.arch),'Architecture sequence discontinuity')
            a=dict(seq=seq,trans_id=tid,insn=op,cycle=cycle,allocations=[],completions=[])
            self.arch[seq]=a
            if memory(op):
                i=len(self.owners)
                need(i<len(self.expected) and op==self.expected[i]['insn'],'Source memory dispatch order/encoding')
                a.update(self.expected[i],request_cycle=None,response_cycle=None,trap=None)
                self.owners.append(a)
        elif event=='uop_alloc':
            a=self.arch.get(seq)
            need(a is not None and (op,tid)==(a['insn'],a['trans_id']),'Allocation owner/op/transaction')
            need(0<=vid<8 and vid not in self.active and cycle>=a['cycle'],'Live VID reuse or early allocation')
            self.active[vid]=(seq,op,tid,cycle)
            a['allocations'].append(dict(vid=vid,cycle=cycle))
        elif event=='uop_done':
            prior=self.active.get(vid)
            need(prior is not None and prior[:3]==(seq,op,tid) and cycle>=prior[3],
                 'Orphan/wrong-owner/early backend completion')
            del self.active[vid]
            self.arch[seq]['completions'].append(dict(vid=vid,allocated=prior[3],cycle=cycle))
        elif event=='cvx_req' and memory(op):
            need(self.request_count<len(self.owners) and tid not in self.requests,'Unowned/duplicate memory request')
            a=self.owners[self.request_count]
            need((op,tid)==(a['insn'],a['trans_id']) and cycle>=a['cycle'],'Memory request owner')
            a['request_cycle']=cycle;self.requests[tid]=a;self.request_count+=1
        elif event=='cvx_resp' and tid in self.requests:
            a=self.requests.pop(tid)
            need(int(r['trap'])==0 and cycle>=a['request_cycle'],'No target/helper fault is allowed')
            a['response_cycle']=cycle;a['trap']=0
        elif event=='retire' and memory(op):
            i=len(self.retired);pc=int(r['pc'],16)
            need(i<len(self.expected) and (pc,op)==(self.expected[i]['pc'],self.expected[i]['insn'])
                 and int(r['trap'])==0,'Original complete memory retirement')
            need((csrs.get(0xc20),csrs.get(0xc21),csrs.get(8))==(8,self.cfg['vtype'],0),
                 'Actual source nonempty VL8/m1/start0')
            if self.expected[i]['site']=='target':
                need([mem.get(self.s['fx_mask']+j) for j in range(16)]==[self.cfg['mask']]+[0]*15,
                     'Exact original predicate; allactive FOF or alloff ordinary')
                need(regs.get(10)==self.cfg['base'],'Original target protected-page geometry')
            self.retired.append(dict(pc=pc,insn=op,cycle=cycle,vl=8,vtype=self.cfg['vtype'],vstart=0))

    def finish(self):
        need(not self.active and not self.requests,'Pending backend/memory owner')
        need(len(self.owners)==self.request_count==len(self.retired)==4,'Exactly four original memory owners')
        for a,retired in zip(self.owners,self.retired):
            need(a['allocations'] and len(a['allocations'])==len(a['completions']),
                 'Missing nonempty backend lifecycle for '+a['site'])
            need(a['request_cycle'] is not None and a['response_cycle'] is not None and a['trap']==0,
                 'Incomplete memory request/response')
            need(a['cycle']<=retired['cycle'] and a['response_cycle']<=retired['cycle'],
                 'Memory retirement before accepted response')
            a['retire_context']=retired
        return dict(memory_owner_count=4,helper_owner_count=3,memory_owners=self.owners,
                    memory_allocations=sum(len(a['allocations']) for a in self.owners),
                    source_active_elements=8 if self.scenario==0 else 4 if self.scenario in (1,2) else 0,
                    source_masked_elements=0 if self.scenario==0 else 4 if self.scenario in (1,2) else 8,
                    source_successful_target_elements=4 if self.scenario<3 else 0,
                    target_returned_vl=self.cfg['returned_vl'])

class Checker(old.Checker):
    def __init__(self,spec):
        super().__init__(spec)
        self.memory_owners=MemoryOwners(spec)
    def row(self,r):
        self.memory_owners.row(r,self.regs,self.csrs,self.mem)
        super().row(r)
    def finish(self):
        result=super().finish()
        result.update(self.memory_owners.finish(),lifecycle_successor='source-bound-four-memory-owners01')
        return result

def analyze(path,spec):
    q=Checker(spec)
    try:
        with Path(path).open() as stream:
            rows=csv.DictReader(stream)
            need(rows.fieldnames==old.FIELDS,'Exact CSV header')
            for row in rows:q.row(row)
        return q.finish()
    except (ValueError,KeyError,TypeError,IndexError,OSError) as error:
        return dict(status='NOT_PASS_UNIT_FOF',error=str(error),rows=q.rows,retired=q.retired,
                    last_cycle=q.last_cycle,checks=q.checks,actions=q.actions,checkpoints=q.points)
