#!/usr/bin/env python3
"""Offline synthetic CSV/gate tests, plus real archived CSV store-format checks."""
import copy
import csv
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
import csv_check as cc
import successor as su
import reference as ref


def synthetic(s):
    rows=[]; checks=0
    def emit(pc=0x80000020,insn=0x13,rd=0,value=0,addr=0,mask=0,data=0,trap=0):
        n=len(rows)
        rows.append(dict(zip(cc.FIELDS,map(str,[n*2+82,'retire',n,0,-1,f'{pc:016x}',f'{insn:08x}',rd,
            f'{value&((1<<64)-1):016x}',f'{addr:016x}','00',f'{mask:02x}',f'{data&((1<<64)-1):016x}',trap]))))
    def reg(r,v): emit(rd=r,value=v)
    def store(a,v,width=8,pc=0x80000020):
        reg(5,a); reg(8,v)
        emit(pc,0x00828023|({1:0,2:1,4:2,8:3}[width]<<12),addr=a,
             mask=((1<<width)-1)<<(a%8),data=v)
    def oracle(n):
        nonlocal checks
        for _ in range(n):
            reg(10,0x5b); reg(11,0x5b); emit(s['check']); checks+=1; store(s['mx_checks'],checks)
    def trap(c,n):
        emit(s['mx_handler'])
        fault=bool(ref.CAUSE[c]) and n==0
        vals=[ref.CAUSE[c] if fault else 9,s[ref.SITE[c]] if fault else s['mx_ecall'],
              ref.VA+ref.OFF[c]+ref.START[c]*ref.STRIDE[c] if fault else 0,0x800,
              (8<<60)|((s['mx_pages']+8192)>>12),8,8,ref.START[c] if fault else 0,117,5,
              0 if fault else 1,0 if fault or not ref.CAUSE[c] else
              (((s['mx_pages']+ref.PAGE[c]*4096)>>12)<<10)|0xc7]
        for csr,j in cc.CSR.items(): emit(s['mx_trap'],(csr<<20)|0x2573,10,vals[j])
        for j,v in enumerate(vals): store(s['mx_records']+c*192+n*96+j*8,v)
        store(s['mx_count']+c*8,n+1)
    for name in ('mx_errors','mx_unexpected','mx_current','mx_checks'): store(s[name],0)
    for c in range(8):
        for name in ('mx_count','mx_marker','mx_case_checks'): store(s[name]+c*8,0)
        for j in range(24): store(s['mx_records']+c*192+j*8,(1<<64)-1)
    oracle(3)
    for c in range(8):
        store(s['mx_current'],c)
        for i,v in enumerate((ref.VA+ref.OFF[c],ref.STRIDE[c]&((1<<64)-1),s[ref.SITE[c]])): store(s['mx_args']+i*8,v)
        for i in range(16): store(s['mx_mask']+c*16+i,ref.MASK[c] if c<6 or i==0 else 0,1)
        leaf=s['mx_pages']+16384+ref.PAGE[c]*8; store(leaf,0)
        emit(s['mx_enter_s'])
        if ref.CAUSE[c]:
            trap(c,0); store(s['mx_restart'],ref.START[c]); oracle(238)
            store(s['mx_phase'],1); emit(s['mx_checkpoint'])
            store(leaf,(((s['mx_pages']+ref.PAGE[c]*4096)>>12)<<10)|0xc7)
            reg(28,ref.VA+ref.PAGE[c]*4096); emit(s['mx_repair_sfence'],0x120e0073)
            for i in range(ref.START[c]):
                if ref.MASK[c]>>i&1:
                    off=ref.OFF[c]+i*ref.STRIDE[c]
                    poison=(ref.seed(c,1,i) if c in (1,3,5) else ref.orig(c,off//2))^0x5b
                    store(s['mx_pages']+off,poison,2)
            reg(5,ref.START[c]); emit(insn=0x00829073); emit(s['mx_trap_mret'],0x30200073)
        insn=(0x55c07,0x55c27,0x09c55c07,0x09c55c27,0x09c55c07,0x09c55c27,0x01055c07,0x01055c07)[c]
        emit(s[ref.SITE[c]],insn)
        for j,v in enumerate((ref.VL[c],8,0,117,5)): store(s['mx_post']+c*40+j*8,v)
        store(s['mx_marker']+c*8,1,pc=s['mx_younger_store'])
        trap(c,1 if ref.CAUSE[c] else 0); emit(s['mx_trap_mret'],0x30200073)
        oracle(cc.COUNTS[c]-(238 if ref.CAUSE[c] else 0))
        store(s['mx_phase'],2); emit(s['mx_checkpoint']); store(s['mx_case_checks']+c*8,cc.COUNTS[c])
    oracle(6227-checks); store(s['mx_completed'],0x6d78737633390008); store(0xd0000000,0)
    return rows


def run_rows(rows,s):
    checker=cc.Checker(s)
    try:
        for i,r in enumerate(rows):
            r=dict(r,order=str(i),cycle=str(i*2+82)); checker.row(r)
        return checker.finish()
    except (ValueError,KeyError,TypeError) as e: return dict(status='REJECTED',error=str(e))


def parent_fixture():
    image=dict(simv=str(su.IMAGE/'_build/vcs/simv'),files={'simv':'pinned'})
    status=dict(status='PASS',stages=[dict(name='build-image',status='PASS',returncode=0,completed_at='now',out=str(su.IMAGE))])
    data={}
    for group,names in su.GROUPS.items():
        argv=['python',str(su.RUNNER),'run','--image',str(su.IMAGE),'--execute']
        for n in names: argv+=['--case',n]
        stage=dict(name=group,status='PASS',returncode=0,completed_at='now',cases=names,out=str(su.CAMPAIGN/group),argv=argv)
        status['stages'].append(stage)
        data[group]=(dict(status='COMPLETE',tests=names,simv=image['simv'],commit_trace=True,invocation=argv[1:]),
                     [dict(name=n,status='PASS',returncode=0) for n in names],
                     {n:dict(simv=dict(path=image['simv'],image_sha256=image['files'])) for n in names})
    return status,data,image


def main(out):
    su.require(not out.exists(),'Fresh offline-test directory required'); out.mkdir()
    s=su.read(su.REFERENCE/'soc.symbols.json'); rows=synthetic(s)
    result=run_rows(rows,s); su.require(result['status']=='EXTENDED8_CSV_ORACLE_PASS',str(result))
    su.save(out/'synthetic_positive.json',result)
    with (out/'synthetic.csv').open('x') as stream:
        w=csv.DictWriter(stream,fieldnames=cc.FIELDS); w.writeheader(); w.writerows(rows)
    su.require(cc.analyze(out/'synthetic.csv',s)['status']=='EXTENDED8_CSV_ORACLE_PASS','CSV file parser differs')
    negatives=[]
    def rejected(name,bad):
        r=run_rows(bad,s); su.require(r['status']=='REJECTED','Accepted '+name)
        negatives.append(dict(name=name,error=r['error']))
    checks=[i for i,r in enumerate(rows) if int(r['pc'],16)==s['check']]
    for n,label in ((0,'first_oracle_mismatch'),(97,'fault_load_prefix_compare'),(158,'fault_full_oldvd_tail_compare'),(6226,'final_restore_compare')):
        bad=copy.deepcopy(rows); bad[checks[n]-2]['rd_wdata']='0000000000000001'; rejected(label,bad)
    bad=copy.deepcopy(rows); del bad[checks[0]]; rejected('missing_oracle_call',bad)
    def change_store(name,address,value,occurrence=0):
        bad=copy.deepcopy(rows)
        idx=[i for i,r in enumerate(bad) if int(r['mem_wmask'],16) and int(r['mem_addr'],16)==address][occurrence]
        bad[idx]['mem_wdata']=f'{value:016x}'; bad[idx-1]['rd_wdata']=f'{value:016x}'
        rejected(name,bad)
    change_store('wrong_fault_vstart_record',s['mx_records']+56,3,1)
    change_store('mapped_alloff_page',s['mx_pages']+16384+8,0x123,9)
    change_store('wrong_fof_vl',s['mx_post']+6*40,8)
    change_store('wrong_case_check_delta',s['mx_case_checks'],629,1)
    change_store('wrong_completion_magic',s['mx_completed'],0)
    change_store('CTRL_nonzero',0xd0000000,1)
    bad=copy.deepcopy(rows); idx=next(i for i,r in enumerate(bad) if int(r['pc'],16)==s['mx_repair_sfence']); del bad[idx]; rejected('missing_repair_sfence',bad)
    bad=copy.deepcopy(rows); idx=next(i for i,r in enumerate(bad) if int(r['pc'],16)==s['mx_trap_mret']); bad[idx-1]['insn']='34129073'; rejected('changed_retry_mepc',bad)
    bad=copy.deepcopy(rows); idx=next(i for i,r in enumerate(bad) if int(r['pc'],16)==s['mx_unit_load']); bad[idx]['insn']='02055c07'; rejected('unmasked_target_opcode',bad)
    bad=copy.deepcopy(rows); bad[-1]['mem_wmask']='0f'; rejected('store_mask_width_mismatch',bad)
    rejected('truncated_before_CTRL',rows[:-1])
    status,data,image=parent_fixture(); su.validate_parent(status,data,image)
    parent_tests=[]
    def parent_bad(label,modify):
        a,b,c=copy.deepcopy((status,data,image)); modify(a,b,c)
        try: su.validate_parent(a,b,c)
        except (ValueError,KeyError) as e: parent_tests.append(dict(name=label,error=str(e))); return
        raise ValueError('Parent gate accepted '+label)
    parent_bad('parent_running',lambda a,b,c:a.update(status='RUNNING'))
    parent_bad('parent_failed',lambda a,b,c:a.update(status='FAIL'))
    parent_bad('smoke_pending',lambda a,b,c:a['stages'][2].update(status='PENDING'))
    parent_bad('missing_smoke',lambda a,b,c:b['smokes'][1].pop())
    parent_bad('smoke_failed',lambda a,b,c:b['smokes'][1][0].update(status='FAIL'))
    parent_bad('sv39_nonzero_exit',lambda a,b,c:b['sv39'][1][0].update(returncode=1))
    parent_bad('summary_duplicate',lambda a,b,c:b['smokes'][1].append(b['smokes'][1][0]))
    parent_bad('stale_image_hash',lambda a,b,c:b['sv39'][2]['alloff_fault'].update(simv=dict(path=c['simv'],image_sha256={'simv':'other'})))
    parent_bad('incomplete_run',lambda a,b,c:b['smokes'][0].update(status='RUNNING'))
    # Check store decoding on archived real CSV, not just synthetic rows.
    historical=HERE.parent/'sv39_candidate01_acceptance01/active_fault_retry/tests/active_fault_retry/commit_trace.csv'
    regs={i:0 for i in range(32)}; stores=0; shifted=0
    with historical.open() as stream:
        for r in csv.DictReader(stream):
            if r['event']!='retire': continue
            write=cc.scalar_store(r,regs)
            if write: stores+=1; shifted+=write[0]%8!=0
            if int(r['rd']) and r['trap']=='0': regs[int(r['rd'])]=int(r['rd_wdata'],16)
    su.require(stores>0 and shifted>0,'No real shifted-store checks')
    su.save(out/'tests.json',dict(status='OFFLINE_TESTS_PASS_NOT_DUT',synthetic_rows=len(rows),
        csv_negative_tests=negatives,parent_negative_tests=parent_tests,
        real_archived_store_checks=stores,real_shifted_store_checks=shifted,
        historical_csv_sha256=su.sha(historical),VCS_started=False))
    print(json.dumps(dict(status='OFFLINE_TESTS_PASS_NOT_DUT',csv_negatives=len(negatives),
                         gate_negatives=len(parent_tests),real_stores=stores,shifted_stores=shifted)))


HERE=Path(__file__).resolve().parent
if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--out',type=Path,required=True)
    main(su.inside(p.parse_args().out))
