"""One read-only pass per accepted M6 CSV, plus owner-only deletion negatives."""
import csv
import time
from pathlib import Path
import checker as c
import successor_handler as s

def run(out):
    c.require(not out.exists(),'Fresh checker bridge output')
    out.mkdir()
    results=[]
    started=time.time()
    for sew in c.SHAPES:
        spec=c.specification(sew)
        name=next(v['id'] for v in c.scope() if v['sew']==sew)
        root=c.HERE.parent/'fof_two_singles_vcs_m6_plan01'
        path=root/'prepared01/replay/tests'/name/'commit_trace.csv'
        accepted=c.read(root/'terminal_waiter01/terminal01/result.json')
        prior=next(r for r in accepted['results'] if r['name']==name)
        c.require(c.sha(path)==prior['csv_sha256'],'Exact closed previously accepted CSV')
        q=s.Checker(spec)
        inputs=[]
        with path.open() as f:
            stream=csv.DictReader(f)
            c.require(stream.fieldnames==c.csv_source.FIELDS,'Actual complete header')
            for r in stream:
                op=int(r['insn'],16)
                if r['event']!='retire' or c.source_owners.memory(op):
                    inputs.append((dict(r),dict(q.regs),dict(q.csrs),
                                   {q.s['fx_mask']+j:q.mem.get(q.s['fx_mask']+j) for j in range(16)}))
                q.row(r)
        result=q.finish()
        c.require(result['status']=='PASS_FOF_ORIGINAL_SINGLE' and result['checks']==prior['numerical']['checks'],
                  'Same full original oracle on closed evidence')
        negatives=[]
        ownerseq=[v['seq'] for v in result['memory_owners']]
        for idx in range(4):
            m=c.source_owners.MemoryOwners(spec)
            try:
                for row,regs,csrs,mem in inputs:
                    if row['event'] in ('uop_alloc','uop_done') and int(row['order'])==ownerseq[idx]:
                        continue
                    m.row(row,regs,csrs,mem)
                m.finish()
            except ValueError as error:
                c.require('Missing nonempty backend lifecycle' in str(error),'Specific deleted-pair rejection')
                negatives.append(dict(site=result['memory_owners'][idx]['site'],reason=str(error)))
            else:raise ValueError('Deleted complete owner lifecycle was accepted')
        for kind in ('unknown_owner','zero_vl','wrong_vtype','bad_target_base','bad_mask'):
            m=c.source_owners.MemoryOwners(spec);mutated=False
            try:
                for row,regs,csrs,mem in inputs:
                    row,regs,csrs,mem=dict(row),dict(regs),dict(csrs),dict(mem)
                    if not mutated and kind=='unknown_owner' and row['event']=='uop_alloc':
                        row['order']='999';mutated=True
                    if not mutated and row['event']=='retire' and int(row['pc'],16)==spec['helper'][3]:
                        if kind=='zero_vl':csrs[0xc20]=0;mutated=True
                        if kind=='wrong_vtype':csrs[0xc21]^=8;mutated=True
                        if kind=='bad_target_base':regs[10]+=1;mutated=True
                        if kind=='bad_mask':mem[q.s['fx_mask']]^=1;mutated=True
                    m.row(row,regs,csrs,mem)
                m.finish()
            except ValueError as error:
                c.require(mutated,'Negative must reach its mutation')
                negatives.append(dict(kind=kind,reason=str(error)))
            else:raise ValueError('Corrupt owner input accepted: '+kind)
        c.common.save(out/(name+'.json'),result)
        results.append(dict(name=name,sew=sew,status=result['status'],checks=result['checks'],rows=result['rows'],
            csv=str(path),csv_sha256=c.sha(path),full_csv_parses=1,negative_count=len(negatives),negatives=negatives,
            report_sha256=c.sha(out/(name+'.json'))))
    pins={str(p):c.sha(p) for p in c.HERE.glob('*.py')}
    c.common.save(out/'result.json',dict(status='CLOSED_M6_CHECKER_BRIDGE_PASS_NOT_NEW_DUT',
        results=results,code_pins=pins,elapsed_s=time.time()-started,new_simulations=0,reference_reruns=0))
    print('BRIDGE_PASS',c.sha(out/'result.json'),flush=True)

if __name__=='__main__':
    run(c.HERE/'host_bridge02')
