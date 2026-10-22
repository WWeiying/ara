#!/usr/bin/env python3
"""Offline synthetic CSV negatives and archived real RVFI store decoding only."""
import copy
import csv
from pathlib import Path
import sys

sys.dont_write_bytecode=True
import reference as ref
import csv_check as cc
import vcs_adapter as adapter


def synthetic(s,alternate=False):
    rows=[]; checks=0
    def emit(pc=0x80000020,insn=0x13,rd=0,value=0,addr=0,mask=0,data=0,trap=0):
        n=len(rows)
        rows.append(dict(zip(cc.FIELDS,map(str,[n*2+82,'retire',n,0,-1,f'{pc:016x}',f'{insn:08x}',rd,
            f'{value&((1<<64)-1):016x}',f'{addr:016x}','00',f'{mask:02x}',f'{data&((1<<64)-1):016x}',trap]))))
    def reg(r,v): emit(rd=r,value=v)
    def store(a,v,width=8,pc=0x80000020):
        reg(5,a); reg(8,v)
        emit(pc,0x00828023|({1:0,2:1,4:2,8:3}[width]<<12),addr=a,mask=((1<<width)-1)<<(a%8),data=v)
    def oracle(n):
        nonlocal checks
        for _ in range(n):
            reg(10,0x5b); reg(11,0x5b); emit(s['check']); checks+=1; store(s['mx_checks'],checks)
    def trap(c,n):
        emit(s['mx_handler']); fault=n==0
        field=1 if c>=2 or alternate else 0
        vals=[(15 if c%2 else 13) if fault else 9,s[ref.SITE[c]] if fault else s['mx_ecall'],
              ref.VA+ref.OFF[c]+20+2*field if fault else 0,0x800,(8<<60)|((s['mx_pages']+8192)>>12),
              8,8,5 if fault else 0,117,5,0 if fault else 1,0 if fault else ((s['mx_pages']+4096)>>12<<10)|0xc7]
        for csr,j in cc.CSR.items(): emit(s['mx_trap'],(csr<<20)|0x2573,10,vals[j])
        for j,v in enumerate(vals): store(s['mx_records']+192*c+96*n+8*j,v)
        store(s['mx_count']+8*c,n+1)
    for name in ('mx_errors','mx_unexpected','mx_current','mx_checks'): store(s[name],0)
    for c in range(4):
        for name in ('mx_count','mx_marker','mx_case_checks'): store(s[name]+8*c,0)
        for j in range(24): store(s['mx_records']+192*c+8*j,(1<<64)-1)
    oracle(3)
    for c in range(4):
        skip=int(alternate and c<2)
        store(s['mx_current'],c)
        for i,v in enumerate((ref.VA+ref.OFF[c],s[ref.SITE[c]])): store(s['mx_args']+8*i,v)
        for i in range(16): store(s['mx_mask']+16*c+i,0x24,1)
        leaf=s['mx_pages']+16392; store(leaf,0); emit(s['mx_enter_s'])
        trap(c,0); store(s['mx_restart'],5)
        prefix=(300 if c%2==0 else 302)-skip
        oracle(prefix); store(s['mx_phase'],1); emit(s['mx_checkpoint'])
        store(leaf,((s['mx_pages']+4096)>>12<<10)|0xc7)
        reg(28,ref.VA+4096); emit(s['mx_repair_sfence'],0x120e0073)
        for f in (0,1):
            off=ref.OFF[c]+8+2*f
            poison=(ref.seed(c,f+1,2) if c%2 else ref.orig(off//2))^0x5b
            store(s['mx_pages']+off,poison,2)
        reg(5,5); emit(insn=0x00829073); emit(s['mx_trap_mret'],0x30200073)
        emit(s[ref.SITE[c]],0x20055c27 if c%2 else 0x20055c07)
        for j,v in enumerate((8,8,0,117,5)): store(s['mx_post']+40*c+8*j,v)
        store(s['mx_marker']+8*c,1,pc=s['mx_younger_store'])
        trap(c,1); emit(s['mx_trap_mret'],0x30200073)
        oracle(cc.COUNTS[c]-skip-prefix)
        store(s['mx_phase'],2); emit(s['mx_checkpoint']); store(s['mx_case_checks']+8*c,cc.COUNTS[c]-skip)
    oracle(4133-(2 if alternate else 0)-checks)
    store(s['mx_completed'],ref.DONE); store(0xd0000000,0)
    return rows


def run_rows(rows,s):
    checker=cc.Checker(s)
    try:
        for i,r in enumerate(rows): checker.row(dict(r,order=str(i),cycle=str(i*2+82)))
        return checker.finish()
    except (ValueError,KeyError,TypeError) as e: return dict(status='REJECTED',error=str(e))


def main(out):
    adapter.require(not out.exists(),'Fresh host-test output required'); out.mkdir()
    s=adapter.read(adapter.REFERENCE/'soc.symbols.json'); rows=synthetic(s)
    result=run_rows(rows,s); adapter.require(result['status']=='NF2_CSV_ORACLE_PASS',str(result))
    adapter.save(out/'synthetic_positive.json',result)
    with (out/'synthetic.csv').open('x') as stream:
        writer=csv.DictWriter(stream,fieldnames=cc.FIELDS); writer.writeheader(); writer.writerows(rows)
    adapter.require(cc.analyze(out/'synthetic.csv',s)['status']=='NF2_CSV_ORACLE_PASS','CSV file parser differs')
    alternate=run_rows(synthetic(s,True),s)
    adapter.require(alternate['status']=='NF2_CSV_ORACLE_PASS' and alternate['checks']==4131,
                    'Original second-protected-field oracle branch rejected')
    adapter.save(out/'alternate_field_positive.json',alternate)
    negatives=[]
    def rejected(name,bad):
        r=run_rows(bad,s); adapter.require(r['status']=='REJECTED','Accepted '+name)
        negatives.append(dict(name=name,error=r['error']))
    checkrows=[i for i,r in enumerate(rows) if int(r['pc'],16)==s['check']]
    for n,label in ((0,'startup_oracle'),(97,'prefix_oracle'),(220,'field1_tail_oracle'),(250,'neighbor_oracle'),
                    (285,'memory_oracle'),(286,'pte_oracle'),(4132,'final_restore_oracle')):
        bad=copy.deepcopy(rows); bad[checkrows[n]-2]['rd_wdata']='0000000000000001'; rejected(label,bad)
    bad=copy.deepcopy(rows); del bad[checkrows[10]]; rejected('missing_oracle_call',bad)
    def change_store(name,address,value,occurrence=0):
        bad=copy.deepcopy(rows)
        idx=[i for i,r in enumerate(bad) if int(r['mem_wmask'],16) and int(r['mem_addr'],16)==address][occurrence]
        bad[idx]['mem_wdata']=f'{value:016x}'; bad[idx-1]['rd_wdata']=f'{value:016x}'
        rejected(name,bad)
    change_store('wrong_vstart_record',s['mx_records']+56,3,1)
    change_store('wrong_laterfield_mtval',s['mx_records']+384+16,ref.VA+4094,1)
    change_store('wrong_mask',s['mx_mask'],0xff)
    change_store('wrong_target_base',s['mx_args'],ref.VA+4074)
    change_store('mapped_protected_page',s['mx_pages']+16392,0x123)
    change_store('field1_prefix_poison',s['mx_pages']+ref.OFF[0]+10,1)
    change_store('wrong_post_vl',s['mx_post'],7)
    change_store('wrong_case_count',s['mx_case_checks'],755,1)
    change_store('wrong_magic',s['mx_completed'],0)
    change_store('nonzero_CTRL',0xd0000000,1)
    for name,pc in (('missing_sfence','mx_repair_sfence'),('missing_target','mx_segment_load'),
                    ('missing_checkpoint','mx_checkpoint')):
        bad=copy.deepcopy(rows); idx=next(i for i,r in enumerate(bad) if int(r['pc'],16)==s[pc]); del bad[idx]; rejected(name,bad)
    bad=copy.deepcopy(rows); idx=next(i for i,r in enumerate(bad) if int(r['pc'],16)==s['mx_trap_mret'])
    bad[idx-1]['insn']='34129073'; rejected('changed_retry_mepc',bad)
    bad=copy.deepcopy(rows); idx=next(i for i,r in enumerate(bad) if int(r['pc'],16)==s['mx_segment_load'])
    bad[idx]['insn']='22055c07'; rejected('unmasked_target',bad)
    bad=copy.deepcopy(rows); bad[-1]['mem_wmask']='0f'; rejected('wrong_store_mask',bad)
    rejected('truncated_before_CTRL',rows[:-1])
    bad=copy.deepcopy(rows); bad[-1].pop('trap'); rejected('truncated_CSV_row',bad)
    # Direct row sequence test: do not renumber away the deliberately missing order.
    checker=cc.Checker(s); checker.row(rows[0]); gap=dict(rows[1],order='2')
    try: checker.row(gap)
    except ValueError as e: negatives.append(dict(name='retirement_gap',error=str(e)))
    else: raise ValueError('Retirement gap accepted')
    valid_review=dict(parent_authorized=True,no_overlap_confirmed=True,preflight_sha256='a'*64,
        image_json_sha256='b'*64,soc_elf_sha256=adapter.ELF_SHA,
        extended8=dict(disposition='REVIEWED_TIMEOUT',evidence_path=str(ref.MT/'sv39_extended/example.json'),
                       evidence_sha256='c'*64,review_note='Synthetic review, not an authorization file'))
    adapter.validate_review(valid_review,'a'*64,'b'*64)
    gates=[]
    def gate_bad(name,mutate):
        bad=copy.deepcopy(valid_review); mutate(bad)
        try: adapter.validate_review(bad,'a'*64,'b'*64)
        except (ValueError,KeyError) as e: gates.append(dict(name=name,error=str(e))); return
        raise ValueError('Review gate accepted '+name)
    gate_bad('not_authorized',lambda x:x.update(parent_authorized=False))
    gate_bad('overlap_unreviewed',lambda x:x.update(no_overlap_confirmed=False))
    gate_bad('wrong_preflight',lambda x:x.update(preflight_sha256='0'*64))
    gate_bad('wrong_image',lambda x:x.update(image_json_sha256='0'*64))
    gate_bad('wrong_elf',lambda x:x.update(soc_elf_sha256='0'*64))
    gate_bad('extended8_pending',lambda x:x['extended8'].update(disposition='PENDING'))
    gate_bad('unbound_extended8',lambda x:x['extended8'].update(evidence_sha256=''))
    gate_bad('wrong_evidence_owner',lambda x:x['extended8'].update(evidence_path='/tmp/not-extended8.json'))
    gate_bad('missing_disposition_note',lambda x:x['extended8'].update(review_note=''))
    adapter.require(adapter.INNER_TIMEOUT==2400 and adapter.OUTER_TIMEOUT>=2700 and
                    adapter.OUTER_TIMEOUT>adapter.INNER_TIMEOUT,'Outer service lacks observer headroom')
    # Archived real RVFI checks validate byte-lane conventions, not NF2 DUT behavior.
    historical=ref.MT/'sv39_candidate01_acceptance01/active_fault_retry/tests/active_fault_retry/commit_trace.csv'
    regs={i:0 for i in range(32)}; stores=shifted=0
    with historical.open() as stream:
        for r in csv.DictReader(stream):
            if r['event']!='retire': continue
            write=cc.scalar_store(r,regs)
            if write: stores+=1; shifted+=write[0]%8!=0
            if int(r['rd']) and r['trap']=='0': regs[int(r['rd'])]=int(r['rd_wdata'],16)
    adapter.require(stores and shifted,'No archived shifted-store checks')
    adapter.save(out/'tests.json',dict(status='OFFLINE_TESTS_PASS_NOT_DUT',synthetic_rows=len(rows),
        csv_negative_tests=negatives,review_negative_tests=gates,alternate_field_counts=alternate['checks'],
        real_archived_store_checks=stores,real_shifted_store_checks=shifted,
        historical_csv=str(historical),historical_csv_sha256=adapter.sha(historical),VCS_started=False))
    print(f'OFFLINE_TESTS_PASS_NOT_DUT csv_negatives={len(negatives)} review_negatives={len(gates)} real_stores={stores}')


if __name__=='__main__':
    import argparse
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('--out',type=Path,required=True)
    main(adapter.inside(p.parse_args().out))
