#!/usr/bin/env python3
"""Synthetic negative custom-contract fixtures, never substitutes for DUT execution."""
import argparse
import copy
import csv
import io
import json
import hashlib
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock
from types import SimpleNamespace

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'verification/coverage'))
import audit_gap73_akv as audit

PREFLIGHT = None
COLUMNS = 'cycle,event,order,port,trans_id,pc,insn,rd,rd_wdata,mem_addr,mem_rmask,mem_wmask,mem_wdata,trap'.split(',')
VCOLUMNS = 'cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,addr,be,wdata,nr_lanes,vlen_bits'.split(',')


def csv_text(rows, fields):
    out = io.StringIO(); writer = csv.DictWriter(out,fieldnames=fields)
    writer.writeheader(); writer.writerows(rows); return out.getvalue()


def info_fixture():
    sym = {}; addr=0x80010000
    for n,size in audit.BUFFERS.items():
        addr = (addr+4095)//4096*4096; sym[n]=addr; addr+=size
    sym['gap73_trap_count']=addr+64; sym['gap73_handler']=0x80000100
    return dict(sites=[dict(phase=p+1,pc=0x80001000+64*p,word=w) for p,w in enumerate(audit.WORDS)],symbols=sym)


def commit_fixture(info):
    rows = []
    def emit(event,**values):
        r={k:'0' for k in COLUMNS}; r.update(cycle=str(len(rows)+1),event=event,trans_id='-1')
        r.update({k:str(v) for k,v in values.items()}); rows.append(r)
    wanted=audit.expected_memory(info)
    for address in sorted(wanted):
        if address%8: continue
        data=bytes(wanted[address+i] for i in range(8))
        emit('retire',insn='00003023',mem_addr='%x'%address,mem_wmask='ff',mem_wdata='%016x'%int.from_bytes(data,'little'))
    for p,w in enumerate(audit.WORDS):
        emit('retire',rd=10,rd_wdata='%x'%(info['symbols']['gap73_descriptor']+64*p if p<=6 else p-7))
        emit('retire',rd=11,rd_wdata='0')
        emit('arch_start',order=100+p,trans_id=p%4,insn='%08x'%w)
        emit('cvx_req',trans_id=p%4,insn='%08x'%w)
        emit('cvx_resp',trans_id=p%4,trap=int(p<6))
        if p>=6: emit('retire',pc='%x'%info['sites'][p]['pc'],insn='%08x'%w)
        for off,word,value in ((4,0x001022f3,21),(8,0x00802373,0)):
            emit('retire',pc='%x'%(info['sites'][p]['pc']+off),insn='%08x'%word,rd_wdata='%x'%value)
    return rows


def vector_fixture(commands):
    rows=[]
    def emit(event,**values):
        row={k:'0' for k in VCOLUMNS}; row.update(cycle=str(len(rows)),event=event,nr_lanes='4',vlen_bits='1024')
        row.update({k:str(v) for k,v in values.items()}); rows.append(row)
    emit('config')
    def group(seq,vid,word,reg,p,custom=False,use=1):
        args=dict(arch_seq=seq,vid=vid,insn='%08x'%word,use_vd=use,vd=reg,eew=1,vl=64 if use else 1)
        emit('alloc',**args)
        if use:
            for chunk in range(4):
                for lane in range(4):
                    value=0
                    for b in range(8):
                        slot,within=divmod(b,2); natural=((slot&1)<<1)|(slot>>1)
                        index=chunk*32+(natural*4+lane)*2+within
                        half=audit.half(p-7,index//2) if custom else audit.seed(p,reg-7,index//2)
                        value|=half.to_bytes(2,'little')[index%2]<<(8*b)
                    emit('write',**args,lane=lane,addr=reg*4+chunk,be='ff',wdata='%016x'%value)
        emit('done',**args)
    for p,c in enumerate(commands):
        for r in (7,8,9): group(1000+p*10+r,r,0x02005007|(r<<7),r,p)
        group(c['seq'],p%4,audit.WORDS[p],8 if 7<=p<=9 else 0,p,True,int(7<=p<=9))
    return rows


def stdout_fixture(info, commands):
    lines=[]; count=13
    for p,s in enumerate(info['sites']):
        perf={k:0 for k in audit.PERF_KEYS}; perf.update(audit.expected_perf(p))
        perf.update(id=p%4,busy_cycles=4,read_outstanding_max=int(p<=6))
        lines.append('[AKV_PERF] '+' '.join('%s=%d'%(k,perf[k]) for k in audit.PERF_KEYS))
        if p<6: lines.append('AKV73_TRAP phase=%d cause=2 pc=%x expected=%x tval=0'%(p+1,s['pc'],s['pc']))
        lines.append('AKV73_CSR phase=%d fflags=21 vstart=0 vl=64 vtype=8 vxrm=2 vxsat=1'%(p+1))
        count+=9 if p<6 else 6
        lines.append('AKV73_PHASE phase=%d word=%08x traps=%d checks=%d errors=0'%(p+1,s['word'],min(p+1,6),count))
    lines+=['PASSED: '+audit.NAME+' checks=97 errors=0',
        '[ARA_CONTRACT] requests=11 responses=11 exceptions=6 mmu_request_cycles=0 protocol_errors=0 outstanding=0',
        'Core Test *** SUCCESS *** (tohost = 0)','UVM_ERROR : 0','UVM_FATAL : 0','$finish at simulation time 100']
    return '\n'.join(lines)+'\n'


class ContractTests(unittest.TestCase):
    def setUp(self):
        self.info=info_fixture(); self.commit=commit_fixture(self.info)
        self.proof=audit.commit_audit(csv_text(self.commit,COLUMNS),self.info)
        self.vector=vector_fixture(self.proof['commands']); self.log=stdout_fixture(self.info,self.proof['commands'])
    def reject_commit(self, rows):
        with self.assertRaises((ValueError,KeyError)): audit.commit_audit(csv_text(rows,COLUMNS),self.info)
    def reject_vector(self, rows):
        with self.assertRaises((ValueError,KeyError)): audit.vector_audit(csv_text(rows,VCOLUMNS),self.proof['commands'])
    def test_positive_independent_contract(self):
        self.assertEqual(audit.stdout_audit(self.log,self.info)['status'],'PASS')
        self.assertEqual(audit.vector_audit(csv_text(self.vector,VCOLUMNS),self.proof['commands'])['status'],'PASS')
    def test_scalar_store_lane_offsets(self):
        for width in (1,2,4,8):
            for offset in range(0,8,width):
                value=0x8877665544332211
                self.assertEqual(audit.scalar_store_bytes(0x1000+offset,value,
                    ((1<<width)-1)<<offset),
                    [(0x1000+offset+i,(value>>(8*i))&255) for i in range(width)])
        for mask in (0,0x55,0x0f,0xff):
            with self.assertRaises(ValueError):
                audit.scalar_store_bytes(0x1004,0x81,mask)
    def test_descriptor_upper_word_store_and_corruption(self):
        rows=copy.deepcopy(self.commit)
        addr=self.info['symbols']['gap73_descriptor']+64+12
        first=next(i for i,r in enumerate(rows) if r['event']=='cvx_req')
        store={k:'0' for k in COLUMNS}
        store.update(event='retire',insn='00002023',mem_addr='%x'%addr,
                     mem_wmask='f0',mem_wdata='81',trans_id='-1')
        rows.insert(first,store)
        for i,r in enumerate(rows): r['cycle']=str(i+1)
        self.assertEqual(audit.commit_audit(csv_text(rows,COLUMNS),self.info)['status'],'PASS')
        store['mem_wdata']='80'
        self.reject_commit(rows)
    def test_scalar_readback_corruption_rejected(self):
        rows=copy.deepcopy(self.commit)
        addr=self.info['symbols']['gap73_got']+4
        value=int.from_bytes(bytes(audit.expected_memory(self.info)[addr+i]
                                  for i in range(4)),'little')
        row={k:'0' for k in COLUMNS}
        row.update(cycle=str(len(rows)+1),event='retire',mem_addr='%x'%addr,
                   mem_rmask='f0',rd=5,rd_wdata='%x'%value)
        rows.append(row)
        self.assertEqual(audit.commit_audit(csv_text(rows,COLUMNS),self.info)['status'],'PASS')
        row['rd_wdata']='%x'%(value^1)
        self.reject_commit(rows)
    def test_each_descriptor_is_one_hot(self):
        for p,term in enumerate(audit.TERMS):
            self.assertEqual(audit.predicates(audit.descriptor(p,0x80010000)),tuple(int(i==term) for i in range(9)))
        self.assertEqual(audit.predicates(audit.descriptor(6,0x80010000)),(0,)*9)
    def test_v2_raw_rejected(self):
        rows=copy.deepcopy(self.commit); next(r for r in rows if r['event']=='cvx_req')['insn']='00b5605b'; self.reject_commit(rows)
    def test_full_rd_reserved_rejected(self):
        rows=copy.deepcopy(self.commit); next(r for r in rows if r['event']=='cvx_req')['insn']='00b5245b'; self.reject_commit(rows)
    def test_wrong_actual_descriptor_operand(self):
        rows=copy.deepcopy(self.commit); next(r for r in rows if r['rd']=='10')['rd_wdata']='80000001'; self.reject_commit(rows)
    def test_illegal_falsely_success(self):
        rows=copy.deepcopy(self.commit); next(r for r in rows if r['event']=='cvx_resp')['trap']='0'; self.reject_commit(rows)
    def test_recovery_fault(self):
        rows=copy.deepcopy(self.commit); [r for r in rows if r['event']=='cvx_resp'][6]['trap']='1'; self.reject_commit(rows)
    def test_cause_epc_tval_and_trap_csrs(self):
        base=self.info['symbols']['gap73_trap']
        for off in range(0,336,8):
            rows=copy.deepcopy(self.commit)
            r=next(r for r in rows if int(r['mem_addr'],16)==base+off)
            r['mem_wdata']='%x'%(int(r['mem_wdata'],16)^1); self.reject_commit(rows)
    def test_full_frame_source_descriptor_memory(self):
        for n in ('gap73_got','gap73_initial','gap73_source','gap73_descriptor','gap73_snapshot'):
            rows=copy.deepcopy(self.commit); base=self.info['symbols'][n]
            r=next(r for r in rows if int(r['mem_addr'],16)==base)
            r['mem_wdata']='%x'%(int(r['mem_wdata'],16)^1); self.reject_commit(rows)
    def test_duplicate_retired_csr(self):
        rows=copy.deepcopy(self.commit); r=next(r for r in rows if r['insn']=='001022f3')
        idx=rows.index(r); rows.insert(idx,dict(r)); self.reject_commit(rows)
    def test_illegal_custom_retired_without_trap(self):
        rows=copy.deepcopy(self.commit); r=dict(rows[-1],pc='%x'%self.info['sites'][0]['pc'],insn='00b5205b',trap='0')
        rows.append(r); self.reject_commit(rows)
    def test_missing_reply(self):
        rows=copy.deepcopy(self.commit); rows.remove(next(r for r in rows if r['event']=='cvx_resp')); self.reject_commit(rows)
    def test_rejected_full_vrf_write(self):
        rows=copy.deepcopy(self.vector); r=dict(next(r for r in rows if r['event']=='alloc' and r['insn']=='00b5205b'))
        idx=next(i for i,x in enumerate(rows) if x is not r and x['event']=='done' and x['arch_seq']==r['arch_seq'])
        r.update(event='write',be='ff',addr='32',wdata='0000000000000000'); rows.insert(idx,r); self.reject_vector(rows)
    def test_rejected_full_reserves_destination(self):
        rows=copy.deepcopy(self.vector); next(r for r in rows if r['event']=='alloc' and r['insn']=='00b5205b')['use_vd']='1'; self.reject_vector(rows)
    def test_eew_initialization_error(self):
        rows=copy.deepcopy(self.vector); next(r for r in rows if r['event']=='alloc')['eew']='0'; self.reject_vector(rows)
    def test_neighbor_write(self):
        rows=copy.deepcopy(self.vector); next(r for r in rows if r['event']=='write' and r['insn']=='0005345b')['addr']='36'; self.reject_vector(rows)
    def test_numerical_recovery_error(self):
        rows=copy.deepcopy(self.vector); next(r for r in rows if r['event']=='write' and r['insn']=='0005345b')['wdata']='0000000000000000'; self.reject_vector(rows)
    def test_missing_vector_completion(self):
        rows=copy.deepcopy(self.vector); rows.pop(); self.reject_vector(rows)
    def test_write_after_completion_rejected(self):
        rows=copy.deepcopy(self.vector)
        idx=next(i for i,r in enumerate(rows) if r['event']=='write' and r['insn']=='0005345b')
        write=rows.pop(idx)
        done=next(i for i,r in enumerate(rows) if r['event']=='done' and
                  (r['arch_seq'],r['vid'])==(write['arch_seq'],write['vid']))
        rows.insert(done+1,write)
        for i,r in enumerate(rows): r['cycle']=str(i)
        self.reject_vector(rows)
    def test_completion_and_last_write_same_cycle_allowed(self):
        rows=copy.deepcopy(self.vector)
        done=next(i for i,r in enumerate(rows) if r['event']=='done' and r['insn']=='0005345b')
        write=rows.pop(done-1)
        rows.insert(done,write)
        write['cycle']=rows[done-1]['cycle']
        self.assertEqual(audit.vector_audit(csv_text(rows,VCOLUMNS),self.proof['commands'])['status'],'PASS')
    def test_no_payload_ar_or_bytes_after_rejection(self):
        for a,b in (('read_ranges=1','read_ranges=2'),('ar=1','ar=2'),('read_payload_bytes=64','read_payload_bytes=192'),
                    ('q_external_bytes=0','q_external_bytes=128'),('kv_external_bytes=0','kv_external_bytes=128'),
                    ('replay_bytes=0','replay_bytes=128'),('validation_error=9','validation_error=8')):
            with self.assertRaises(ValueError): audit.stdout_audit(self.log.replace(a,b,1),self.info)
    def test_stdout_trap_tval_must_zero_not_rawword(self):
        with self.assertRaises(ValueError): audit.stdout_audit(self.log.replace('tval=0','tval=b5205b',1),self.info)
    def test_stdout_completion_required(self):
        for marker in ('Core Test *** SUCCESS *** (tohost = 0)','UVM_ERROR : 0','$finish at simulation time 100'):
            with self.assertRaises(ValueError): audit.stdout_audit(self.log.replace(marker,''),self.info)
    def test_perf_missing_or_duplicate(self):
        line=self.log.splitlines()[0]
        for text in (self.log.replace(line+'\n','',1),line+'\n'+self.log):
            with self.assertRaises(ValueError): audit.stdout_audit(text,self.info)
    def test_adapter_only_installs_evidence_hooks(self):
        import coverage_evidence as evidence
        import run_checked_extension as checked
        import run_gap73_akv_checked_extension as wrapper
        oldpre,oldrow,oldhooks=evidence.precheck,evidence.Evidence.baseline_row,wrapper._hooks
        original=checked.SCRIPT
        try:
            hooks=wrapper.install_hooks()
            self.assertIs(hooks,wrapper.install_hooks()); self.assertEqual(checked.SCRIPT,original)
            self.assertEqual(wrapper.NAME,audit.NAME); self.assertEqual(wrapper.CASE_NAMES,[audit.TEST])
            self.assertIs(hooks['precheck'].delegate,oldpre)
            self.assertIs(hooks['baseline_row'].delegate,oldrow)
        finally:
            evidence.precheck,evidence.Evidence.baseline_row,wrapper._hooks=oldpre,oldrow,oldhooks
    def test_actual_preflight_artifacts(self):
        if PREFLIGHT is None: self.skipTest('actual ELF/host artifacts not supplied')
        exe=audit.elf_audit((PREFLIGHT/(audit.NAME+'.elf')).read_bytes())
        self.assertEqual(len(exe['sites']),11)
        self.assertEqual(audit.host_oracle((PREFLIGHT/'host-oracle.log').read_text())['status'],'PASS')
        self.assertEqual((PREFLIGHT/'host-results.log').read_text(),'PASSED: '+audit.NAME+' checks=79 errors=0\n')
    def test_actual_elf_custom_words_negative(self):
        if PREFLIGHT is None: self.skipTest('actual ELF artifacts not supplied')
        original=(PREFLIGHT/(audit.NAME+'.elf')).read_bytes()
        for word in (0x00b5205b,0x0005345b,0x0000505b):
            blob=bytearray(original); offset=blob.index(word.to_bytes(4,'little')); blob[offset+1]^=0x40
            with self.assertRaises(ValueError): audit.elf_audit(blob)
    def test_runtime_api_binds_all_four_and_rejects_missing(self):
        if PREFLIGHT is None: self.skipTest('actual ELF artifacts not supplied')
        import coverage_evidence as evidence
        import run_gap73_akv_checked_extension as wrapper
        blob=(PREFLIGHT/(audit.NAME+'.elf')).read_bytes(); actual=audit.elf_audit(blob)
        rows=commit_fixture(actual); contract=audit.commit_audit(csv_text(rows,COLUMNS),actual)
        vector=vector_fixture(contract['commands']); log=stdout_fixture(actual,contract['commands'])
        targets=json.loads((PREFLIGHT/'native-targets.json').read_text())
        with tempfile.TemporaryDirectory(prefix='gap73-runtime-fixture-') as temp:
            output=Path(temp); target=output/'results'/audit.NAME; artifact=target/'tests'/('app_'+audit.NAME)
            work=artifact/'work'; work.mkdir(parents=True)
            data=work/'code.vdb/snps/coverage/db/testdata/gap73/cond.verilog.data.xml'; data.parent.mkdir(parents=True)
            data.write_text('SYNTHETIC_NATIVE_FIXTURE_NOT_DUT\n')
            paths=dict(stdout=work/'run.vcs.log',vector=work/'vector_trace.csv',commit=artifact/'commit_trace.csv',elf=artifact/'input.elf')
            paths['stdout'].write_text(log); paths['vector'].write_text(csv_text(vector,VCOLUMNS))
            paths['commit'].write_text(csv_text(rows,COLUMNS)); paths['elf'].write_bytes(blob)
            summary=target/'summary.json'; summary.write_text(json.dumps([dict(name=audit.TEST,artifact_dir=str(artifact))]))
            launch=work/'coverage.command.json'; launch.write_text(json.dumps(dict(command=[str(output/'simv'),
                '+TESTCASE='+audit.NAME,'+NO_FSDB','+AKV_PERF','+VECTOR_TRACE='+str(paths['vector'])],cwd=str(work))))
            selection=output/'selection.json'; selection.write_text(json.dumps(dict(cases=[dict(name=audit.TEST,timeout_s=300,
                precheck=dict(record=str(PREFLIGHT/(audit.NAME+'.precheck.json'))))])))
            case=dict(name=audit.NAME,source_name=audit.TEST,timeout_s=300,kind='directed',oracle='custom-contract',
                elf_sha256=hashlib.sha256(blob).hexdigest(),directed_test=dict(name=audit.TEST,kind='app'))
            case['contract']=evidence.full.contract(case)
            plan=dict(cases=[case],simv=str(output/'simv'),design_vdb=targets['design_vdb'],source_selection=dict(selection=str(selection)))
            files={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [*paths.values(),summary,launch]}
            row=dict(name=audit.NAME,status='PASS',returncode=0,passed_only=True,vdb_valid=True,reused=False,
                elf_sha256=case['elf_sha256'],contract=case['contract'],files=files,vdb=str(work/'code.vdb'),
                vdb_files={str(data):hashlib.sha256(data.read_bytes()).hexdigest()})
            native={audit.SCOPE:dict(width=targets['width'],checksum=targets['checksum'],bits='f'*((targets['width']+3)//4))}
            with mock.patch.object(wrapper,'sealed_precheck'),mock.patch.object(wrapper,'install_hooks'),\
                 mock.patch.object(wrapper,'_hooks',dict(precheck=SimpleNamespace(delegate=None))),\
                 mock.patch('coverage_bitmap_delta.read_metric',return_value=native):
                result=wrapper.runtime_proof(output,plan,row,evidence.Evidence())
                self.assertEqual((result['status'],result['schema']),('PASS',audit.SCHEMA))
                self.assertTrue(set(map(str,paths.values()))<=set(result['files']))
                for path in paths.values():
                    bad=copy.deepcopy(row); del bad['files'][str(path)]
                    with self.assertRaises(ValueError): wrapper.runtime_proof(output,plan,bad,evidence.Evidence())
                launch.write_text(json.dumps(dict(command=[str(output/'simv'),'+TESTCASE='+audit.NAME,
                    '+NO_FSDB','+AKV_PERF','+VECTOR_TRACE=work/vector_trace.csv'],cwd=str(work))))
                row['files'][str(launch)]=hashlib.sha256(launch.read_bytes()).hexdigest()
                with self.assertRaises(ValueError): wrapper.runtime_proof(output,plan,row,evidence.Evidence())


def main():
    global PREFLIGHT
    parser=argparse.ArgumentParser(); parser.add_argument('--preflight',type=Path)
    parser.add_argument('--report',type=Path); parser.add_argument('-v',action='store_true')
    args=parser.parse_args(); PREFLIGHT=args.preflight
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests)
    result=unittest.TextTestRunner(verbosity=2 if args.v else 1).run(suite)
    if args.report:
        args.report.write_text(json.dumps(dict(status='PASS' if result.wasSuccessful() else 'FAIL',
            tests_run=result.testsRun,skipped=len(result.skipped),fixture_scope='SYNTHETIC_NOT_DUT',
            c_mutations_rejected=audit.NEGATIVES if PREFLIGHT else None),indent=2)+'\n')
    return not result.wasSuccessful()


if __name__=='__main__': raise SystemExit(main())
