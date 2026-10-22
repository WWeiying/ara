"""Actual RVFI addresses/BE/GPRs plus complete independent on-device oracle."""
import csv
import json
from pathlib import Path
import re
import check as c

class Checker:
    def __init__(self,spec,st,sv):
        self.o=c.Observer(spec,st,sv);self.rows=0;self.order=0;self.cycle=-1
        self.target=self.o.code[self.o.s['mt_target']]
        self.requests={};self.target_count=0;self.faults=[];self.pending={};self.done=[];self.arch=[]
    def row(self,r):
        c.need(set(r)==set(c.FIELDS) and None not in r.values(),'CSV schema')
        self.rows+=1;cycle=int(r['cycle']);c.need(cycle>=self.cycle,'Cycle regression');self.cycle=cycle
        event=r['event'];insn=int(r['insn'],16);tid=int(r['trans_id'])
        c.need(event in ('retire','cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'),'Unknown event')
        if event=='cvx_req':
            c.need(tid not in self.requests,'Duplicate CVX');self.requests[tid]=insn
            if insn==self.target:self.target_count+=1
        if event=='cvx_resp':
            c.need(tid in self.requests,'Unowned CVX response');op=self.requests.pop(tid)
            if int(r['trap']):
                c.need(op==self.target and not self.faults,'Wrong/extra CVX fault');self.faults.append(cycle)
        if event=='arch_start' and insn==self.target:self.arch.append(int(r['order']))
        if event=='uop_alloc' and insn==self.target:
            key=(int(r['order']),int(r['port']))
            c.need(key[0] in self.arch and key not in self.pending,'Target owner allocation')
            self.pending[key]=cycle
        if event=='uop_done' and insn==self.target:
            key=(int(r['order']),int(r['port']))
            c.need(key in self.pending,'Unowned target completion')
            self.done.append(dict(owner=key,allocated=self.pending.pop(key),done=cycle))
        if event!='retire':return
        c.need(int(r['order'])==self.order,'Retire gap');self.order+=1
        pc=int(r['pc'],16);rd=int(r['rd']);value=int(r['rd_wdata'],16);trap=bool(int(r['trap']))
        gp={rd:value} if rd and not trap else {}
        a,rm,wm,v=(int(r[k],16) for k in ('mem_addr','mem_rmask','mem_wmask','mem_wdata'))
        access=[]
        if rm or wm:
            c.need(not trap and not(rm and wm),'Trapped/bidirectional scalar memory')
            d=c.memory_op(insn);c.need(d is not None,'Nonscalar RVFI memory')
            n=d['size'];c.need(n in (1,2,4,8) and a%8+n<=8,'Scalar width/alignment')
            c.need((rm or wm)==((1<<n)-1)<<(a%8),'Actual byte enables')
            if wm:
                c.need(d['kind']=='write','Store opcode');access=[('write',a,v&((1<<(8*n))-1),n)]
            else:
                c.need(d['kind']=='read' and rd==d['register'],'Load destination')
                low=value&((1<<(8*n))-1)
                want=low|((c.MASK64^((1<<(8*n))-1)) if d.get('signed',n==4) and low>>(8*n-1) else 0)
                c.need(value==want,'Actual load sign extension')
                access=[('read',a,low,n)]
        self.o.step(pc,insn,gp,access,trap=trap)
    def finish(self):
        c.need(not self.requests and not self.pending and self.target_count==2 and len(self.faults)==1
               and len(self.arch)==2 and len(self.done)==2,'Target lifecycle incomplete')
        result=self.o.finish('dut')
        result.update(status='STRIDED_ALIGNMENT_DUT_CSV_PASS',rows=self.rows,retired_rows=self.order,last_cycle=self.cycle,
                      target_requests=self.target_count,cvx_fault_cycles=self.faults,target_owners=self.done,
                      data_evidence='Complete independent actual scalar oracle operands; vector data not invented from scalar RVFI')
        return result

def analyze(path,spec,st,sv):
    checker=Checker(spec,st,sv)
    with Path(path).open() as f:
        reader=csv.DictReader(f);c.need(reader.fieldnames==c.FIELDS,'CSV header')
        for row in reader:checker.row(row)
    return checker.finish()

def bridge(ref):
    """Host-only projection of existing Spike commits, not RVFI or DUT acceptance."""
    member=ref.name.removeprefix('reference_').removesuffix('01')
    st=member.startswith('store');sv=member.endswith('sv39')
    spec=json.loads((ref/'spike.spec.json').read_text());checker=Checker(spec,st,sv)
    partials=0;order=0
    with (ref/'spike.trace').open() as f:
        for line in f:
            m=re.match(r'^core\s+0:\s+([0-3])\s+0x([0-9a-f]+)\s+\(0x([0-9a-f]+)\)(.*)$',line)
            if not m:continue
            pc,insn,tail=int(m[2],16),int(m[3],16),m[4]
            if pc==spec['symbols']['mt_target'] and not partials:partials+=1;continue
            gp=[(int(r),int(v,16)) for r,v in re.findall(r'\bx([0-9]+)\s+0x([0-9a-f]+)',tail)]
            c.need(len(gp)<=1,'Multiple GPR writes')
            row={k:'0' for k in c.FIELDS};row.update(event='retire',cycle=str(order),order=str(order),pc=f'{pc:x}',insn=f'{insn:x}')
            if gp:row.update(rd=str(gp[0][0]),rd_wdata=f'{gp[0][1]:x}')
            d=c.memory_op(insn)
            if d is not None:
                accesses=[(int(a,16),int(v,16) if v else None) for a,v in re.findall(r'\bmem 0x([0-9a-f]+)(?: 0x([0-9a-f]+))?',tail)]
                c.need(len(accesses)==1,'Actual scalar memory access missing')
                a,v=accesses[0];n=d['size'];row['mem_addr']=f'{a:x}'
                row['mem_wmask' if d['kind']=='write' else 'mem_rmask']=f'{((1<<n)-1)<<(a%8):x}'
                if v is not None:row['mem_wdata']=f'{v:x}'
            checker.row(row);order+=1
    c.need(partials==1,'Actual partial count')
    # No CVX events exist in Spike: test scalar decoder/observer and native HTIF
    # endpoint, deliberately not Checker.finish() or a synthetic DUT lifecycle.
    result=checker.o.finish('spike')
    return dict(member=member,status='HOST_EXISTING_REFERENCE_DECODER_BRIDGE_PASS_NOT_DUT',
                checks=result['checks'],scalar_rows=order,endpoint='native Spike HTIF1',cvx_proven=False)

if __name__=='__main__':
    import reference as r
    out=c.HERE/'host_dut01';out.mkdir(exist_ok=False)
    results=[]
    for member in ('load_m','store_m','load_sv39','store_sv39'):
        ref=c.HERE/('reference_'+member+'01');ready=json.loads((ref/'READY.json').read_text())
        pins=dict(ready['input_pins']);pins.update({str(ref/p):v for p,v in ready['outputs'].items()})
        c.need(all(r.sha(p)==v for p,v in pins.items()),'Reference drift')
        results.append(bridge(ref))
        c.need(all(r.sha(p)==v for p,v in pins.items()),'Post bridge drift')
    r.save(out/'result.json',dict(status='HOST_FOUR_BRIDGES_PASS_NOT_DUT',results=results,
             checker_sha256=r.sha(Path(__file__)),oracle_sha256=r.sha(c.HERE/'check.py')))
    print(json.dumps(results,indent=2))
