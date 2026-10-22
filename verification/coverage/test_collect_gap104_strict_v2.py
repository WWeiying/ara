from collections import Counter
from copy import deepcopy
import csv
import json
from types import SimpleNamespace
import unittest

import collect_gap104_strict_v2 as m
from ara_verify.vector_commit import _deshuffle_byte


def controls():
    rows=[]
    for seq,word in enumerate(m.proof.WORDS,1):
        base=dict(order=str(seq),trans_id='0',pc='00000000',insn='%08x'%word,
                  cycle=str(seq*10),trap='0',port='0')
        rows.extend(dict(base,event=e) for e in ('arch_start','cvx_req'))
        rows.append(dict(base,event='cvx_resp',order='-1',insn='00000000',trap='1'))
    base=dict(order='3',trans_id='0',pc='00000000',insn='5e02c057',cycle='30',trap='0',port='0')
    rows.extend(dict(base,event=e) for e in ('arch_start','cvx_req','uop_alloc','uop_done'))
    rows.append(dict(base,event='cvx_resp',order='-1',insn='00000000'))
    vectors=[dict(event=e,arch_seq='3',vid='0',cycle='30',insn='5e02c057',
                  use_vd='1',vd='0',eew='0',vl='128',vstart='0',nr_lanes='4',vlen_bits='1024')
             for e in ('alloc','done')]
    return rows,vectors


def observations():
    names=set(m.proof.SYMBOLS)
    symbols={name:0x90000000+i*0x10000 for i,name in enumerate(sorted(names))}
    words=m.proof.expected_words()
    for phase in range(2):
        ledger=[2,symbols['g104_bad_a' if phase==0 else 'g104_bad_b'],m.proof.WORDS[phase],1,0,0,0,phase+1]
        words.update({('g104_ledger',phase*80+i*8):v for i,v in enumerate(ledger)})
    words.update({('g104_restore',i*8):v for i,v in enumerate((0x100,0x100,0x200,0x200))})
    words.update({('g75_result',0):1309,('g75_result',4):0,('num_failed',0):0})
    ordered=list(words.items())+[(('tohost',0),1)]
    rows=[]
    for i,((name,offset),value) in enumerate(ordered):
        size=4 if name in ('g75_result','num_failed') else 8;addr=symbols[name]+offset
        rows.append(dict(event='retire',order=str(i),trap='0',pc='0000000080000000',
            cycle=str(i),insn='00003023' if size==8 else '00002023',mem_addr='%x'%addr,
            mem_wmask='%x'%(((1<<size)-1)<<(addr&7)),mem_wdata='%x'%value))
    return rows,symbols


def transport_rows():
    rows=[]
    for seq in range(64):
        reg=seq%32;cycle=seq*3
        base=dict(arch_seq=str(seq),vid='0',insn='%08x'%(0x5e02c057|(reg<<7)),
            use_vd='1',vd=str(reg),eew='0',vl='128',vstart='0',nr_lanes='4',vlen_bits='1024')
        rows.append(dict(base,event='alloc',cycle=str(cycle)))
        for word in range(4):
            for lane in range(4):
                rows.append(dict(base,event='write',cycle=str(cycle+1),lane=str(lane),source='0',
                    addr=str(reg*4+word),be='ff',wdata='%016x'%int.from_bytes(bytes([0x40+reg])*8,'little')))
        rows.append(dict(base,event='done',cycle=str(cycle+2)))
    return rows


def vector_result(audit):
    result=dict(status='PASS',compared_instructions=64,compared_bytes=8192,skipped_unknown_bytes=0,
        non_bit_exact_instructions=0,unobservable_instructions=0,nr_lanes=4,vlen_bits=1024,
        selected_index=None,stopped_at_spike_index=None,trapped_requests=[71,72],
        incomplete_requests=[],unretired_requests=[],first_mismatch=None)
    result['instructions']=[dict(status='PASS',unknown_write_bytes=0,mismatch_count=0,first_mismatch=None,
        skipped_unknown_bytes=0,compared_bytes=128,arch_seq=r['arch_seq'],instruction=r['instruction'],
        uops=1,write_events=r['write_events']) for r in audit['records']]
    return result


class CollectorTests(unittest.TestCase):
    def test_two_rejected_requests_no_backend(self):
        rows,vectors=controls();result=m.lifecycle(rows,vectors)
        self.assertEqual(result['exception_arch_seqs'],[1,2])
        self.assertEqual(result['requests'],3)

    def test_illegal_backend_activity_rejected(self):
        rows,vectors=controls();base=rows[0]
        rows.extend(dict(base,event=e) for e in ('uop_alloc','uop_done'))
        with self.assertRaises(ValueError):m.lifecycle(rows,vectors)

    def test_illegal_vrf_activity_rejected(self):
        rows,vectors=controls();vectors[0]['arch_seq']='1'
        with self.assertRaises(ValueError):m.lifecycle(rows,vectors)

    def test_missing_exception_response_or_duplicate_request(self):
        rows,vectors=controls()
        for bad in (rows[:2]+rows[3:],rows+[rows[0]]):
            with self.assertRaises(ValueError):m.lifecycle(bad,vectors)
        bad=deepcopy(rows);bad[2]['trap']='0'
        with self.assertRaises(ValueError):m.lifecycle(bad,vectors)

    def test_backend_and_vector_completion_identity(self):
        rows,vectors=controls()
        bad=deepcopy(vectors);bad[-1]['vl']='1'
        with self.assertRaises(ValueError):m.lifecycle(rows,bad)
        bad=deepcopy(rows);bad[9]['cycle']='29'
        with self.assertRaises(ValueError):m.lifecycle(bad,vectors)

    def test_complete_phase_snapshots(self):
        rows,symbols=observations()
        self.assertEqual(m.observed(rows,symbols)['checks'],1309)

    def test_vrf_memory_guard_recovery_csr_trap_and_restore_rejections(self):
        rows,symbols=observations()
        for name,offset in (('g104_dump',0),('g104_dump',8192-8),('g104_target_dump',0),
                ('g104_target_dump',1024-8),('g104_recovery_dump',16),('g104_recovery_dump',1024-8),
                ('g104_csr',40),('g104_ledger',80+16),('g104_restore',8),('g104_traps',0)):
            bad=deepcopy(rows);addr=symbols[name]+offset
            row=next(r for r in bad if int(r['mem_addr'],16)==addr)
            row['mem_wdata']='%x'%(int(row['mem_wdata'],16)^1)
            with self.subTest(name=name),self.assertRaises(ValueError):m.observed(bad,symbols)

    def test_missing_byte_bad_retire_and_postterminal(self):
        rows,symbols=observations()
        bad=deepcopy(rows);bad[0]['mem_wmask']='1'
        with self.assertRaises(ValueError):m.observed(bad,symbols)
        bad=deepcopy(rows);bad[0]['pc']='%x'%symbols['g104_bad_a']
        with self.assertRaises(ValueError):m.observed(bad,symbols)
        with self.assertRaises(ValueError):m.observed(rows+[dict(rows[0],order=str(len(rows)))],symbols)

    def test_full_physical_transport(self):
        audit=m.transport_exact(transport_rows());self.assertEqual(audit['compared_bytes'],8192)
        m.vector_exact(vector_result(audit),{'exception_arch_seqs':[71,72]},audit)

    def test_corrupt_unknown_or_missing_physical_byte(self):
        rows=transport_rows()
        for field,value in (('wdata','xxxxxxxxxxxxxxxx'),('wdata','4040404040404041'),('be','fe'),('addr','4')):
            bad=deepcopy(rows);bad[1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):m.transport_exact(bad)

    def test_extra_unobservable_write_rejected(self):
        rows=transport_rows();rows[0]['use_vd']='0'
        with self.assertRaises(ValueError):m.transport_exact(rows)

    def test_perrecord_unknown_skip_and_wrong_exception_population(self):
        audit=m.transport_exact(transport_rows());control={'exception_arch_seqs':[71,72]}
        for field,value in (('unknown_write_bytes',1),('skipped_unknown_bytes',1),('compared_bytes',127)):
            result=vector_result(audit);result['instructions'][-1][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):m.vector_exact(result,control,audit)
        result=vector_result(audit);result['trapped_requests']=[71]
        with self.assertRaises(ValueError):m.vector_exact(result,control,audit)

    def test_latest_target_already_hit_not_fresh(self):
        targets=json.loads((m.runner.PRE/'target-before.json').read_bytes());before={'metrics':{}}
        for target in targets['targets']:
            before['metrics'].setdefault(target['metric'],{})[target['scope']]=dict(
                width=target['width'],checksum=target['checksum'],bits='0')
        single=deepcopy(before)
        for target in targets['targets']:
            row=single['metrics'][target['metric']][target['scope']]
            row['bits']='%x'%(int(row['bits'],16)|(1<<(row['width']-1-target['point']['raw_index'])))
        self.assertTrue(all(r['fresh_latest_hit'] for r in m.measure_targets(before,single,targets)))
        self.assertFalse(any(r['fresh_latest_hit'] for r in m.measure_targets(single,single,targets)))
        target=targets['targets'][0];single['metrics'][target['metric']][target['scope']]['checksum']='wrong'
        with self.assertRaises(ValueError):m.measure_targets(before,single,targets)

    def test_sealed_spike_scalar_counts(self):
        pre=m.life.read_bound(m.runner.PRE/'preflight-manifest.json',m.runner.PRE_SEAL)
        self.assertEqual(m.life.digest(m.runner.PRE/'spike.trace'),pre['pins'][str(m.runner.PRE/'spike.trace')])
        commits=m.proof.s.parse_spike_commits(m.runner.PRE/'spike.trace')
        self.assertEqual(m.shared.reference_counts(commits,pre['symbols']),m.SCALAR_COUNTS)

    def test_scalar_skip_unknown_or_inexact_count_rejected(self):
        counts=m.SCALAR_COUNTS
        result=dict(status='TERMINAL_TOHOST_MATCH',entry='0x0000000080000000',
            rvfi_store_data_layout='unshifted',skipped_unobservable_register_values=0,
            stopped_at_unobservable=None,aligned_vector_faults=[],ara_trap_events=0,
            mismatch=None,terminal_ecall=None,vector_state_compared=False,
            ara_retired_instructions=counts['matched_instructions'],
            ara_committed_instructions=counts['matched_instructions'],
            terminal_tohost=dict(address='0x0000000080001000',write_value='0x1'),**counts)
        m.shared.scalar_exact(result,counts)
        for key,value in (('matched_instructions',1),('matched_scalar_memory_accesses',0),
                          ('skipped_unobservable_register_values',1),('aligned_vector_faults',[1]),('mismatch',{})):
            bad=dict(result);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):m.shared.scalar_exact(bad,counts)

    def test_independent_tracer_exact_two_traps(self):
        rows=[dict(event='retire',cycle='1',pc='0000000080000000',insn='00000013')]
        symbols={'g104_bad_a':0x80002200,'g104_bad_b':0x80002204}
        prefix=' 1ns 1 M 0000000080000000 0 00000013\n'
        text=prefix+'\n'.join('Exception @ abc%d, PC: %016x, Cause: Illegal Instruction,\n\ttval: %016x'%
            (phase,symbols[name],word) for phase,(name,word) in enumerate(zip(('g104_bad_a','g104_bad_b'),m.proof.WORDS)))
        self.assertEqual(m.tracer_exact(text,rows,symbols)['causes'],[2,2])
        for bad in (text.replace('80002204','80002208'),text.replace('Illegal Instruction','Load Fault'),
                    text.replace('0000000042850427','0000000042850407'),text+'\nException @ 80002204'):
            with self.assertRaises(ValueError):m.tracer_exact(bad,rows,symbols)


class ActualTracerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        trace=m.RUN/'trace_hart_0.log';commit=m.RUN/'commit_trace.csv'
        if m.life.digest(trace)!='74e48bf796d5fc06ce0a7db85f2aa506b7e32f6daa530db8e0f5e12b352e6ba2':
            raise ValueError('Actual tracer fixture changed')
        if m.life.digest(commit)!='be80fe8a26a23f4eb5c94e92a085497300decb0bcda2a78096fe7f1f253d0818':
            raise ValueError('Actual retirement fixture changed')
        cls.text=trace.read_text()
        with commit.open() as handle:cls.rows=list(csv.DictReader(handle))
        cls.symbols=m.life.read_bound(m.runner.PRE/'preflight-manifest.json',m.runner.PRE_SEAL)['symbols']

    def test_actual_time_pc_and_tval_contract(self):
        result=m.tracer_exact(self.text,self.rows,self.symbols)
        self.assertEqual(result['exception_pcs'],['0x80002258','0x8000226c'])
        self.assertEqual(result['exception_time_tokens'],['145040000','266760000'])
        self.assertTrue(result['time_tokens_not_interpreted_as_pc'])
        self.assertEqual(result['tvals'],['0x42850407','0x42850427'])

    def test_hex_timestamp_not_architectural_pc(self):
        text=self.text.replace('Exception @ 145040000','Exception @ abcdef')
        self.assertEqual(m.tracer_exact(text,self.rows,self.symbols)['exception_time_tokens'][0],'abcdef')

    def test_time_cannot_impersonate_correct_pc(self):
        text=self.text.replace('Exception @ 145040000, PC: 0000000080002258',
                               'Exception @ 80002258, PC: 000000008000225c')
        with self.assertRaises(ValueError):m.tracer_exact(text,self.rows,self.symbols)

    def test_pc_order_and_tval_association_rejected(self):
        for text in (self.text.replace('0000000080002258, Cause','000000008000226c, Cause'),
                     self.text.replace('tval: 0000000042850407','tval: 0000000042850427'),
                     self.text.replace('Cause: Illegal Instruction','Cause: Load Access Fault',1)):
            with self.assertRaises(ValueError):m.tracer_exact(text,self.rows,self.symbols)

    def test_missing_extra_exception_or_retire_prefix_rejected(self):
        for text in (self.text.replace('Exception @ 145040000','Lost @ 145040000'),
                     self.text+'\nException @ 1, PC: 0000000080002258, Cause: Illegal Instruction,\ntval: 0000000042850407'):
            with self.assertRaises(ValueError):m.tracer_exact(text,self.rows,self.symbols)
        rows=deepcopy(self.rows);retired=next(r for r in rows if r['event']=='retire');retired['insn']='ffffffff'
        with self.assertRaises(ValueError):m.tracer_exact(self.text,rows,self.symbols)


if __name__=='__main__':unittest.main()
