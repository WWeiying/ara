#!/usr/bin/env python3
"""One shared Host pass across34 full inputs and representative2/4 observer dimensions."""
import copy
from pathlib import Path
import shutil
import sys
sys.dont_write_bytecode=True
import batch
import model as m
import csv_check as cc
import synthetic
from scope import HERE,read,save,sha,require,verify

def state(s,c,p):
    mem,choices=m.expected(s,c,p)
    for a,n,values in choices:
        for i,b in enumerate(values[0].to_bytes(n,'little')):mem[a+i]=b
    for n in range(m.record_count(c,p)):
        for i,b in enumerate((0x800).to_bytes(8,'little')):mem[s['mx_records']+192*c+96*n+24+i]=b
    m.compare(mem,s,c,p);return mem
def run_rows(rows,s):
    observer=cc.Checker(s)
    for i,row in enumerate(rows):observer.row(dict(row,order=str(i),cycle=str(82+2*i)))
    return observer.finish()

def main():
    out=HERE/'host01';require(not out.exists(),'Fresh shared Host only');out.mkdir()
    inv=read(HERE/'source_manifest.json');allcases=[c for g in inv['groups'] for c in g['cases']]
    for n in ('fixture.c','fixture.h'):shutil.copyfile(HERE/n,out/n)
    batch.text_new(out/'group_config.h',batch.header(allcases))
    batch.base.run_logged(['/usr/bin/cc','-Wall','-Wextra','-Werror','-DMX_HOST',out/'fixture.c','-o',out/'host'],out/'compile.log')
    batch.base.run_logged([out/'host'],out/'host.stdout')
    m.configure(allcases);rows=m.check_host((out/'host.stdout').read_text())
    positives=[];negative=[]
    for g in inv['groups']:
        cfg=batch.configure(g['id']);s=read(HERE/g['id']/'reference02/spike.symbols.json')
        for c,cfg in enumerate(g['cases']):
            for p in m.phases(c):state(s,c,p);positives.append([g['id'],cfg['id'],p])
            mutations=[('upper_field1_tail',2,s['mx_out']+260*c+2+128+126),
                       ('last_guard',2,s['mx_out']+260*c+258),('post_vstart',2,s['mx_post']+40*c+16),
                       ('PTE_neighbor',2,s['mx_pages']+16384+16),('mask',2,s['mx_mask']+16*c)]
            if cfg['fault']:
                mutations.append(('fault_start',1,s['mx_records']+192*c+56))
                for i in range(cfg['start']):
                    if m.active(c,i):
                        for f in (0,1):mutations.append(('completed_prefix_field'+str(f),2,s['mx_pages']+cfg['base']+4*i+2*f))
            else:
                mutations += [('precleanup_memory',3,s['mx_pages']+4096),('precleanup_leaf',3,s['mx_pages']+16392),
                              ('extra_fault_record',3,s['mx_records']+192*c+96)]
            for label,p,a in mutations:
                mem=state(s,c,p);mem[a]^=1
                try:m.compare(mem,s,c,p)
                except ValueError:negative.append([g['id'],cfg['id'],label]);continue
                raise ValueError('Oracle accepted '+str((g['id'],c,label)))
    observers=[]
    # Once per materially different shape: protected4, unmapped4, and final N=2.
    for g in (inv['groups'][0],inv['groups'][5],inv['groups'][-1]):
        cc.configure(g['cases']);s=read(HERE/g['id']/'reference02/soc.symbols.json')
        rows0=synthetic.synthetic(s);result=run_rows(rows0,s)
        require(result['status']=='NF2_CSV_ORACLE_PASS','Observer positive rejected')
        tests=[]
        for label,mutate in (
            ('missing_CTRL',lambda r:r.pop()),
            ('wrong_target',lambda r:next(x for x in r if int(x['pc'],16)==s['mx_segment_store'] or int(x['pc'],16)==s['mx_segment_load']).update(insn='22055c07')),
            ('missing_full_oracle',lambda r:r.pop(next(i for i,x in enumerate(r) if int(x['pc'],16)==s['check'])))):
            bad=copy.deepcopy(rows0);mutate(bad)
            try:run_rows(bad,s)
            except ValueError:tests.append(label);continue
            raise ValueError('Observer accepted '+label)
        observers.append(dict(group=g['id'],N=len(g['cases']),checks=result['checks'],negative=tests))
    pins={str(HERE/n):sha(HERE/n) for n in ('host.py','synthetic.py','model.py','reference_core.py','csv_check.py','scope.py',
         'source_manifest.json','fixture.c','fixture.h','fixture.S','batch.py')}
    for g in inv['groups']:
        for name in ('source_proof.json','soc.symbols.json','spike.symbols.json'):
            p=HERE/g['id']/'reference02'/name;pins[str(p)]=sha(p)
    save(out/'status.json',dict(status='PASS_HOST_ONLY',full_input_oracle_rows=rows,full_input_cases=len(allcases),
        positive_checkpoints=positives,negative=negative,observer_tests=observers,pins=pins,
        fake_rows_are_not_architectural_evidence=True,VCS_started=False))
    print('PASS_HOST_ONLY',rows,len(positives),len(negative),observers)

if __name__=='__main__':main()
