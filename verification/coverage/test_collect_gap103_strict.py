import copy
import json
from pathlib import Path
from types import SimpleNamespace
import unittest

import collect_gap103_strict as m
from ara_verify.vector_commit import _deshuffle_byte


def fixture():
    images = m.proof.images()
    initial = b''.join(bytes([0x40+r])*128 for r in range(32))
    rows, refs = [], []
    cycle = 0

    def stage(seq, insn, cfg, image, positions):
        nonlocal cycle
        use, vd, eew, vl, start = cfg
        cycle += 2
        base = dict(arch_seq=str(seq), vid='0', insn='%08x' % insn,
                    nr_lanes='4', vlen_bits='1024', use_vd=str(use),
                    vd=str(vd), eew=str(eew), vl=str(vl), vstart=str(start))
        rows.append(dict(base, event='alloc', cycle=str(cycle)))
        words = {}
        inverse = {_deshuffle_byte(p, 4, eew): p for p in range(32)}
        for reg, byte in sorted(positions):
            p = inverse[byte % 32]
            key = (reg*4+byte//32, p//8)
            be, data = words.get(key, (0, 0))
            words[key] = (be | (1 << (p % 8)),
                          data | (image[reg*128+byte] << (8*(p % 8))))
        for (addr, lane), (be, data) in sorted(words.items()):
            rows.append(dict(base, event='write', cycle=str(cycle+1),
                             addr=str(addr), lane=str(lane), source='0',
                             be='%02x' % be, wdata='%016x' % data))
        cycle += 2
        rows.append(dict(base, event='done', cycle=str(cycle)))

    def region(regs):
        return {(r,b) for r in regs for b in range(128)}

    for reg in range(32):
        insn = 0x5e02c057 | (reg << 7)
        stage(reg, insn, (1,reg,0,128,0), initial, region([reg]))
        refs.append(SimpleNamespace(instruction=insn, pc=0x80002000+4*reg,
                                    vector_writes={reg: 0}))
    stage(32, 0x02006407, (1,8,2,256,0), images['seeded'], region(range(8,16)))
    refs.append(SimpleNamespace(instruction=0x02006407, pc=0x80002200,
                                vector_writes={r:0 for r in range(8,16)}))
    stage(33, 0x02005607, (1,12,1,256,0), images['before'], region(range(12,16)))
    refs.append(SimpleNamespace(instruction=0x02005607, pc=0x80002204,
                                vector_writes={r:0 for r in range(12,16)}))
    stage(34, m.proof.WORD, (0,0,1,129,0), images['before'], set())
    stage(34, m.proof.WORD, (0,10,1,64,0), images['before'], set())
    stage(34, m.proof.WORD, (1,12,2,32,0), images['before'], region([12]))
    stage(34, m.proof.WORD, (1,8,1,13,0), images['before'], {(8,b) for b in range(26)})
    stage(34, m.proof.WORD, (1,8,1,129,13), images['after'],
          {(8+i//128,i%128) for i in range(26,258)})
    stage(34, m.proof.WORD, (1,10,1,64,1), images['after'], {(10,b) for b in range(2,128)})
    stage(34, m.proof.WORD, (1,11,1,64,0), images['after'], region([11]))
    refs.append(SimpleNamespace(instruction=m.proof.WORD, pc=m.NARROW_PC,
                                vector_writes={8:0,9:0,10:0}))
    return rows, refs


def comparison(audit):
    result = dict(status='PASS', compared_instructions=35,
                  compared_bytes=audit['compared_bytes'],
                  skipped_unknown_bytes=audit['supplemented_preservation_bytes'],
                  non_bit_exact_instructions=0, unobservable_instructions=0,
                  nr_lanes=4, vlen_bits=1024, selected_index=None,
                  stopped_at_spike_index=None, trapped_requests=[],
                  incomplete_requests=[], unretired_requests=[], first_mismatch=None)
    result['instructions'] = [dict(status='PASS', unknown_write_bytes=0,
        mismatch_count=0, first_mismatch=None, arch_seq=r['arch_seq'],
        instruction=r['instruction'], pc=r['pc'], uops=r['uops'],
        write_events=r['write_events'], compared_bytes=r['compared_bytes'],
        skipped_unknown_bytes=r['supplemented_preservation_bytes']) for r in audit['records']]
    return result


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.rows, self.refs = fixture()

    def test_exact_independent_transport(self):
        audit = m.transport_exact(self.rows, self.refs)
        self.assertEqual(audit['compared_bytes'], 6016)
        self.assertEqual(audit['supplemented_preservation_bytes'], 256)
        self.assertFalse(audit['physical_traffic_inferred_from_spike'])
        m.vector_exact(comparison(audit), audit)

    def corrupt(self, predicate):
        row = next(r for r in self.rows if r['event']=='write' and predicate(r))
        bit = next(b for b in range(8) if int(row['be'],16) & (1 << b))
        row['wdata'] = '%016x' % (int(row['wdata'],16) ^ (1 << (8*bit)))
        with self.assertRaises(ValueError):
            m.transport_exact(self.rows, self.refs)

    def test_source_maintenance_corruption_rejected(self):
        self.corrupt(lambda r: r['arch_seq']=='34' and r['vd']=='12')

    def test_prefix_corruption_rejected(self):
        self.corrupt(lambda r: r['arch_seq']=='34' and r['vl']=='13')

    def test_active_corruption_rejected(self):
        self.corrupt(lambda r: r['arch_seq']=='34' and r['vstart']=='13')

    def test_tail_preservation_corruption_rejected(self):
        self.corrupt(lambda r: r['arch_seq']=='34' and r['vd']=='11')

    def test_missing_granted_byte_rejected(self):
        row = next(r for r in self.rows if r['event']=='write')
        row['be'] = '%02x' % (int(row['be'],16) & (int(row['be'],16)-1))
        with self.assertRaises(ValueError): m.transport_exact(self.rows,self.refs)

    def test_unknown_granted_byte_rejected(self):
        next(r for r in self.rows if r['event']=='write')['wdata'] = 'xxxxxxxxxxxxxxxx'
        with self.assertRaises(ValueError): m.transport_exact(self.rows,self.refs)

    def test_wrong_configuration_rejected(self):
        self.rows[0]['nr_lanes']='8'
        with self.assertRaises(ValueError): m.transport_exact(self.rows,self.refs)

    def test_wrong_reference_identity_rejected(self):
        self.refs[-1].instruction ^= 1
        with self.assertRaises(ValueError): m.transport_exact(self.rows,self.refs)

    def test_per_record_unknown_rejected(self):
        audit = m.transport_exact(self.rows,self.refs)
        result = comparison(audit)
        result['instructions'][-1]['unknown_write_bytes']=1
        with self.assertRaises(ValueError): m.vector_exact(result,audit)

    def test_per_record_skip_cannot_hide_behind_top(self):
        audit = m.transport_exact(self.rows,self.refs)
        result = comparison(audit)
        result['instructions'][-1]['skipped_unknown_bytes']=0
        with self.assertRaises(ValueError): m.vector_exact(result,audit)

    def test_reference_scalar_counts(self):
        pre = m.life.read_bound(m.runner.PRE/'preflight-manifest.json',m.runner.PRE_SEAL)
        self.assertEqual(m.life.digest(Path(pre['input_spike_trace'])),pre['pins'][pre['input_spike_trace']])
        commits = m.proof.s.parse_spike_commits(Path(pre['input_spike_trace']))
        self.assertEqual(m.reference_counts(commits,pre['symbols']),m.SCALAR_COUNTS)


class ContractTests(unittest.TestCase):
    def test_target_measurement_is_not_assumed(self):
        targets = json.loads((m.runner.PRE/'target-before.json').read_text())
        before = {'metrics':{}}
        for target in targets['targets']:
            before['metrics'].setdefault(target['metric'],{})[target['scope']] = dict(
                width=target['width'],checksum=target['checksum'],bits='0')
        single = copy.deepcopy(before)
        self.assertFalse(any(r['hit_single'] for r in m.measure_targets(before,single,targets)))
        for target in targets['targets']:
            point = single['metrics'][target['metric']][target['scope']]
            point['bits'] = '%x'%(int(point['bits'],16) | (1 << (point['width']-1-target['point']['raw_index'])))
        self.assertTrue(all(r['hit_single'] for r in m.measure_targets(before,single,targets)))
        with self.assertRaises(ValueError): m.measure_targets(single,single,targets)
        bad = copy.deepcopy(single)
        target = targets['targets'][0]
        bad['metrics'][target['metric']][target['scope']]['checksum'] = 'mismatched'
        with self.assertRaises(ValueError): m.measure_targets(before,bad,targets)

    def events(self):
        common = dict(trans_id='0',order='0',pc='00000000',insn='%08x'%m.proof.WORD,
                      trap='0',port='0',cycle='10')
        rows = [dict(common,event=e) for e in
                ('arch_start','cvx_req','uop_alloc','uop_done','cvx_resp','retire')]
        rows[4].update(order='-1',insn='00000000')
        rows[-1].update(pc='%x'%m.NARROW_PC,cycle='20')
        vectors = [dict(event=e,arch_seq='0',vid='0',cycle='10',insn=common['insn'],
                        use_vd='1',vd='8',eew='1',vl='129',vstart='13',nr_lanes='4',vlen_bits='1024')
                   for e in ('alloc','write','done')]
        return rows,vectors,{'g103_narrow':m.NARROW_PC}

    def test_pc_zero_start_exact_retirement(self):
        rows,vectors,symbols = self.events()
        self.assertEqual(m.lifecycle(rows,vectors,symbols)['original_narrow_vstart'],13)

    def test_retirement_wrong_pc_premature_duplicate(self):
        rows,vectors,symbols = self.events()
        for field,value in (('pc','800023a8'),('cycle','9')):
            bad = copy.deepcopy(rows); bad[-1][field]=value
            with self.assertRaises(ValueError): m.lifecycle(bad,vectors,symbols)
        with self.assertRaises(ValueError): m.lifecycle(rows+[rows[-1]],vectors,symbols)

    def test_exact_original_configuration(self):
        rows,vectors,symbols = self.events()
        for key,value in (('vstart','0'),('vl','128'),('eew','2'),('vd','12'),('use_vd','0')):
            bad = copy.deepcopy(vectors)
            for row in bad: row[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError): m.lifecycle(rows,bad,symbols)

    def test_missing_response_completion_or_wrong_placeholder(self):
        rows,vectors,symbols = self.events()
        bad = copy.deepcopy(rows); bad[4]['insn']=bad[0]['insn']
        for rr,vv in ((bad,vectors),(rows[:4]+rows[5:],vectors),(rows,vectors[:-1])):
            with self.assertRaises(ValueError): m.lifecycle(rr,vv,symbols)

    def observations(self):
        words = dict(m.proof.expected_words())
        words.update({('g75_trap',i*8):0 for i in range(3)})
        words.update({('g75_result',0):1245,('g75_result',4):0,('num_failed',0):0,('tohost',0):1})
        names = {name for name,_ in words} | {'trap_fail'}
        symbols = {name:0x90000000+i*0x10000 for i,name in enumerate(sorted(names))}
        ordered = [x for x in words.items() if x[0][0]!='tohost']+[(('tohost',0),1)]
        rows = []
        for i,((name,offset),value) in enumerate(ordered):
            width = 4 if name in ('g75_result','num_failed') else 8
            address = symbols[name]+offset
            rows.append(dict(event='retire',order=str(i),trap='0',pc='80000000',
                insn='00003023' if width==8 else '00002023',mem_addr='%x'%address,
                mem_wmask='%x'%(((1<<width)-1)<<(address&7)),mem_wdata='%x'%value))
        return rows,symbols

    def test_complete_software_snapshot_oracle(self):
        rows,symbols = self.observations()
        self.assertEqual(m.observed(rows,symbols)['checks'],1245)

    def test_each_declared_word_corruption_rejected(self):
        rows,symbols = self.observations()
        # One pass for every declared snapshot/guard/CSR/recovery word.
        for i in range(len(rows)):
            bad = copy.deepcopy(rows)
            bad[i]['mem_wdata']='%x'%(int(bad[i]['mem_wdata'],16)^1)
            with self.subTest(index=i),self.assertRaises(ValueError): m.observed(bad,symbols)

    def test_missing_byte_and_postterminal_rejected(self):
        rows,symbols = self.observations()
        bad = copy.deepcopy(rows); bad[0]['mem_wmask']='1'
        with self.assertRaises(ValueError): m.observed(bad,symbols)
        extra = dict(rows[0],order=str(len(rows)))
        with self.assertRaises(ValueError): m.observed(rows+[extra],symbols)

    def test_scalar_unknown_skip_or_counts_rejected(self):
        expected = m.SCALAR_COUNTS
        result = dict(status='TERMINAL_TOHOST_MATCH',entry='0x0000000080000000',
            rvfi_store_data_layout='unshifted',skipped_unobservable_register_values=0,
            stopped_at_unobservable=None,aligned_vector_faults=[],ara_trap_events=0,
            mismatch=None,terminal_ecall=None,vector_state_compared=False,
            ara_retired_instructions=expected['matched_instructions'],
            ara_committed_instructions=expected['matched_instructions'],
            terminal_tohost=dict(address='0x0000000080001000',write_value='0x1'),**expected)
        m.scalar_exact(result,expected)
        for key,value in (('matched_scalar_writes',0),('skipped_unobservable_register_values',1),
                          ('stopped_at_unobservable',1),('mismatch',{})):
            bad = dict(result); bad[key]=value
            with self.assertRaises(ValueError): m.scalar_exact(bad,expected)


if __name__ == '__main__':
    unittest.main()
