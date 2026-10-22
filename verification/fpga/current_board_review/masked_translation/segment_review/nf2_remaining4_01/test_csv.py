#!/usr/bin/env python3
"""Synthetic observer tests only; actual compiled SoC symbols, no DUT claims."""
import copy
import json
from pathlib import Path
import sys
sys.dont_write_bytecode = True
import csv_check as cc
import reference as ref

def synthetic(s, alternate=False):
    rows=[]; checks=0
    def emit(pc=0x80000020,insn=0x13,rd=0,value=0,addr=0,mask=0,data=0,trap=0):
        n=len(rows)
        rows.append(dict(zip(cc.FIELDS,map(str,[n*2+82,'retire',n,0,-1,f'{pc:016x}',f'{insn:08x}',rd,
            f'{value&((1<<64)-1):016x}',f'{addr:016x}','00',f'{mask:02x}',f'{data&((1<<64)-1):016x}',trap]))))
    def reg(r,v,pc=0x80000020): emit(pc=pc,rd=r,value=v)
    def store(a,v,width=8,pc=0x80000020,allpc=None):
        reg(5,a,allpc or 0x80000020); reg(8,v,allpc or 0x80000020)
        emit(allpc or pc,0x00828023|({1:0,2:1,4:2,8:3}[width]<<12),addr=a,mask=((1<<width)-1)<<(a%8),data=v)
    def oracle(n):
        nonlocal checks
        for _ in range(n):
            reg(10,0x5b);reg(11,0x5b);emit(s['check']);checks+=1;store(s['mx_checks'],checks)
    def trap(c,n):
        emit(s['mx_handler']);cfg=ref.CASES[c];fault=cfg['fault'] and n==0
        vals=[(15 if cfg['store'] else 13) if fault else 9,s[ref.SITE[c]] if fault else s['mx_ecall'],
              ref.VA+ref.OFF[c]+4*cfg['start']+2*int(alternate) if fault else 0,0x800,
              (8<<60)|((s['mx_pages']+8192)>>12),8,8,cfg['start'] if fault else 0,117,5,
              0 if fault else 1,0 if fault or not cfg['fault'] else ((s['mx_pages']+4096)>>12<<10)|0xc7]
        for csr,j in cc.CSR.items():emit(s['mx_trap'],(csr<<20)|0x2573,10,vals[j])
        for j,v in enumerate(vals):store(s['mx_records']+192*c+96*n+8*j,v)
        store(s['mx_count']+8*c,n+1)
    def refill():
        emit(s['mx_refill_page'])
        for i in range(2048):store(s['mx_pages']+4096+2*i,ref.orig(2048+i),2,allpc=s['mx_refill_page']+2)
        emit()
    for name in ('mx_errors','mx_unexpected','mx_current','mx_checks'):store(s[name],0)
    for c in range(4):
        for name in ('mx_count','mx_marker','mx_case_checks'):store(s[name]+8*c,0)
        for j in range(24):store(s['mx_records']+192*c+8*j,(1<<64)-1)
    oracle(3)
    for c,cfg in enumerate(ref.CASES):
        skip=int(alternate and cfg['fault']);begin=checks
        store(s['mx_current'],c)
        for i,v in enumerate((ref.VA+ref.OFF[c],s[ref.SITE[c]])):store(s['mx_args']+8*i,v)
        for i in range(16):store(s['mx_mask']+16*c+i,cfg['mask'],1)
        leaf=s['mx_pages']+16392;store(leaf,0);emit(s['mx_enter_s'])
        if cfg['fault']:
            trap(c,0);store(s['mx_restart'],cfg['start'])
            oracle((302 if cfg['store'] else 300)-skip)
            store(s['mx_phase'],1);emit(s['mx_checkpoint'])
            store(leaf,((s['mx_pages']+4096)>>12<<10)|0xc7)
            reg(28,ref.VA+4096);emit(s['mx_repair_sfence'],0x120e0073)
            if cfg['unmapped']:refill()
            for i in range(cfg['start']):
                if not ref.active(c,i):continue
                for f in (0,1):
                    off=ref.OFF[c]+4*i+2*f
                    poison=(ref.seed(c,f+1,i) if cfg['store'] else ref.orig(off//2))^0x5b
                    store(s['mx_pages']+off,poison,2)
            reg(5,cfg['start']);emit(insn=0x00829073);emit(s['mx_trap_mret'],0x30200073)
        emit(s[ref.SITE[c]],0x20055c27 if cfg['store'] else 0x20055c07)
        for j,v in enumerate((8,8,0,117,5)):store(s['mx_post']+40*c+8*j,v)
        store(s['mx_marker']+8*c,1,pc=s['mx_younger_store'])
        trap(c,int(cfg['fault']));emit(s['mx_trap_mret'],0x30200073)
        if not cfg['fault']:
            oracle(30);store(s['mx_phase'],3);emit(s['mx_checkpoint'])
            store(leaf,((s['mx_pages']+4096)>>12<<10)|0xc7)
            reg(28,ref.VA+4096);emit(s['mx_cleanup_sfence'],0x120e0073)
            if cfg['unmapped']:refill()
        oracle(cc.COUNTS[c]-skip-(checks-begin))
        store(s['mx_phase'],2);emit(s['mx_checkpoint']);store(s['mx_case_checks']+8*c,cc.COUNTS[c]-skip)
    oracle(3567-2*int(alternate)-checks)
    store(s['mx_completed'],ref.DONE);store(0xd0000000,0)
    return rows

def run(rows,s):
    c=cc.Checker(s)
    try:
        for i,r in enumerate(rows):c.row(dict(r,order=str(i),cycle=str(i*2+82)))
        return c.finish()
    except (ValueError,KeyError,TypeError) as e:return dict(status='REJECTED',error=str(e))

def main(out):
    ref.require(not out.exists(),'Fresh Host output required')
    out.mkdir()
    s=json.loads((ref.OUT/'soc.symbols.json').read_text());rows=synthetic(s)
    positive=run(rows,s);ref.require(positive['status']=='NF2_CSV_ORACLE_PASS',str(positive))
    alternate=run(synthetic(s,True),s)
    ref.require(alternate['status']=='NF2_CSV_ORACLE_PASS' and alternate['checks']==3565,str(alternate))
    negatives=[]
    def reject(name,bad):
        result=run(bad,s);ref.require(result['status']=='REJECTED','Accepted '+name)
        negatives.append(dict(name=name,error=result['error']))
    def change(name,a,v,occurrence=0):
        bad=copy.deepcopy(rows)
        i=[i for i,r in enumerate(bad) if int(r['mem_wmask'],16) and int(r['mem_addr'],16)==a][occurrence]
        bad[i]['mem_wdata']=f'{v:016x}';bad[i-1]['rd_wdata']=f'{v:016x}';reject(name,bad)
    checks=[i for i,r in enumerate(rows) if int(r['pc'],16)==s['check']]
    for n,name in ((0,'startup'),(100,'prefix'),(280,'guard'),(800,'field1'),(1540,'alloff_precleanup'),
                   (1800,'fullmemory'),(2200,'alloff_load'),(3566,'CSR_restore')):
        bad=copy.deepcopy(rows);bad[checks[n]-2]['rd_wdata']='1';reject('wrong_'+name,bad)
    change('wrong_mask',s['mx_mask'],255)
    change('wrong_start2_record',s['mx_records']+56,5,1)
    change('alloff_fake_pagefault',s['mx_records']+384,15,1)
    change('alloff_second_record',s['mx_records']+480,0)
    change('alloff_ecall_mapped_leaf',s['mx_records']+384+88,123,1)
    change('wrong_refill_data',s['mx_pages']+4096,1)
    change('completed_store_field1_poison',s['mx_pages']+ref.OFF[1]+10,0)
    change('post_vstart',s['mx_post']+80+16,1)
    change('wrong_CTRL',0xd0000000,1)
    for name,pc in (('missing_precleanup','mx_checkpoint'),('missing_cleanup_sfence','mx_cleanup_sfence'),
                    ('missing_target','mx_segment_load'),('missing_refill_entry','mx_refill_page')):
        bad=copy.deepcopy(rows)
        ids=[i for i,r in enumerate(bad) if int(r['pc'],16)==s[pc]]
        del bad[ids[4] if name=='missing_precleanup' else ids[0]];reject(name,bad)
    bad=copy.deepcopy(rows);i=next(i for i,r in enumerate(bad) if int(r['pc'],16)==s['mx_segment_load'])
    bad[i]['insn']='22055c07';reject('wrong_unmasked_opcode',bad)
    bad=copy.deepcopy(rows);bad.insert(i,dict(bad[i]));reject('duplicate_target',bad)
    reject('no_CTRL',rows[:-1])
    bad=copy.deepcopy(rows);del bad[checks[-1]];reject('missing_final_oracle',bad)
    pins={str(p):ref.sha(p) for p in (Path(__file__),Path(cc.__file__),ref.OUT/'soc.symbols.json',ref.HERE/'READY.json')}
    ref.save(out/'status.json',dict(status='PASS_HOST_ONLY_NOT_DUT',positive=positive,alternate=alternate,
        negative_count=len(negatives),negatives=negatives,synthetic_rows=len(rows),pins=pins))
    print('PASS_HOST_ONLY_NOT_DUT',len(negatives))

if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);main(p.parse_args().out)
