import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import collect_akv_entropy as c
import run_akv_entropy as r


class RuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = r.life.read_bound(r.PRE/'preflight-manifest.json',r.PRE_SHA)
        cls.blob = r.ELF.read_bytes()
        cls.symbols = cls.pre['symbols']
        cls.model,cls.dry = c.replay(cls.blob,cls.symbols)
        # A model-derived fixture has no observed DUT inputs; mutate it to test rejection gates.
        m = c.Model(cls.blob,cls.symbols)
        cls.rows = []
        seq,retired = 0,0
        while not m.terminal:
            word = int.from_bytes(m.read(m.pc,4),'little')
            cycle = m.steps*10+100
            request = c.isa.base.native.request_instruction(word)
            response = m.csr[word>>20] if word&127 == 0x73 else 64 if word&127 == 0x57 else 0
            effect = m.step()
            def row(event,**kw):
                return dict(event=event,cycle=cycle,order=seq,insn=word,trans_id=0,port=0,
                            rd_wdata=0,trap=0,pc=0,**kw)
            if request:
                cls.rows.append(row('arch_start'))
                a = row('cvx_req'); a['cycle']+=1; cls.rows.append(a)
                if word&127 in (7,0x27,0x5b):
                    a = row('uop_alloc'); a['cycle']+=1; cls.rows.append(a)
                    a = row('uop_done'); a['cycle']+=2; cls.rows.append(a)
                a = row('cvx_resp'); a.update(cycle=cycle+2,rd_wdata=response,trap=effect['trap']); cls.rows.append(a)
                seq += 1
            if not effect['trap']:
                a = dict(effect,event='retire',cycle=cycle+3,order=retired,mem_wdata=effect.get('store_value',0))
                cls.rows.append(a)
                retired += 1
        cls.arch = c.lifecycle(cls.rows,cls.model)
        cls.vector = [dict(event='config',nr_lanes='4',vlen_bits='1024',**{k:'0' for k in
            ('cycle','arch_seq','vid','lane','source','insn','use_vd','vd','eew','vl','vstart','addr','be','wdata')})]
        payloads = {}
        seeds = [s for s,a in cls.arch['allocations'].items() if a['insn']&127 == 7]
        for e in cls.model.vector_effects:
            key = seeds[e['vd']] if e['kind']=='seed' else cls.arch['commands'][4]['seq']
            payloads[key] = (e['vd'],bytes.fromhex(e['data']))
        for key,a in cls.arch['allocations'].items():
            op = a['insn']&127
            use = int(key in payloads)
            vd = payloads[key][0] if use else 0
            base = dict(nr_lanes='4',vlen_bits='1024',arch_seq=str(key),vid=str(a['port']),
                        insn=hex(a['insn']),use_vd=str(use),vd=str(vd),eew='1',
                        vl='64' if op != 0x5b or use else '1',vstart='0',lane='0',source='0',addr='0',be='0',wdata='0')
            cls.vector.append(dict(base,event='alloc',cycle=str(a['cycle'])))
            if use:
                data = payloads[key][1]
                for chunk in range(4):
                    for lane in range(4):
                        word = 0
                        for byte in range(8):
                            slot,within = divmod(byte,2); natural = ((slot&1)<<1)|(slot>>1)
                            word |= data[chunk*32+(natural*4+lane)*2+within]<<(8*byte)
                        cls.vector.append(dict(base,event='write',cycle=str(a['cycle']),source='4',lane=str(lane),
                                               addr=str(vd*4+chunk),be='ff',wdata=hex(word)))
            cls.vector.append(dict(base,event='done',cycle=str(cls.arch['done'][key]['cycle'])))

    def test_complete_native_gold_zero_skip(self):
        _,result = c.replay(self.blob,self.symbols,self.rows)
        self.assertEqual(result['skipped_retirements'],0)
        self.assertEqual(result['matched_retirements'],67572)

    def test_changed_scalar_result_rejected(self):
        rows = copy.deepcopy(self.rows)
        next(x for x in rows if x['event']=='retire' and x['rd'])['rd_wdata'] ^= 1
        with self.assertRaises(ValueError): c.replay(self.blob,self.symbols,rows)

    def test_truncated_scalar_rejected(self):
        with self.assertRaises(ValueError): c.replay(self.blob,self.symbols,self.rows[:-1])

    def test_six_commands_and_tid_reuse(self):
        self.assertEqual(len(self.arch['commands']),6)
        self.assertEqual(self.arch['commands'][1]['validation_error'],3)
        self.assertEqual(self.arch['requests'],270)

    def test_response_duplicate_rejected(self):
        rows = copy.deepcopy(self.rows)
        i = next(i for i,x in enumerate(rows) if x['event']=='cvx_resp')
        rows.insert(i+1,dict(rows[i]))
        with self.assertRaises(ValueError): c.lifecycle(rows,self.model)

    def test_wrong_exception_rejected(self):
        rows = copy.deepcopy(self.rows)
        next(x for x in rows if x['event']=='cvx_resp' and x['trap'])['trap']=0
        with self.assertRaises(ValueError): c.lifecycle(rows,self.model)

    def test_csr_gold_rejected(self):
        rows = copy.deepcopy(self.rows)
        next(x for x in rows if x['event']=='retire' and x['insn']>>20==0xc20)['rd_wdata']=63
        with self.assertRaises(ValueError): c.lifecycle(rows,self.model)

    def test_full_seed_custom_bytes(self):
        self.assertEqual(c.vectors(self.vector,self.model,self.arch)['custom_bytes'],128)

    def test_wrong_missing_late_neighbor_writes(self):
        for kind in ('value','missing','late','neighbor','be'):
            rows = copy.deepcopy(self.vector)
            i = next(i for i,x in enumerate(rows) if x['event']=='write')
            if kind=='value': rows[i]['wdata']=hex(int(rows[i]['wdata'],16)^1)
            elif kind=='missing': rows.pop(i)
            elif kind=='late': rows[i]['cycle']='99999999'
            elif kind=='neighbor': rows[i]['addr']='127'
            else: rows[i]['be']='0'
            with self.assertRaises(ValueError,msg=kind): c.vectors(rows,self.model,self.arch)

    def test_runtime_contract_exact_actual_schema(self):
        log='[ARA_CONTRACT] requests=270 responses=270 exceptions=1 mmu_request_cycles=0 protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0\n'
        self.assertEqual(c.contract(log,270)['resp_stalled'],0)
        for bad in (log.replace('req_stalled=0','req_stalled=1'),log.rstrip()+' foreign=0\n',log+log,
                    log.replace(' resp_stalled=0',''),log.replace('requests=270','requests=0270')):
            with self.assertRaises(ValueError): c.contract(bad,270)

    def test_terminal_types_and_execution_identity(self):
        image,elf,run = Path('/image'),Path('/elf'),Path('/run')
        manifest = dict(pins={'/image':'a','/elf':'b'},command=['/image'])
        start = dict(pid=42,starttime=1,live_identity_verified=True,cwd='/run',exe='/image',
                     executable_sha256='a',input_elf='/elf',elf_sha256='b',command=['/image'],budget_s=600)
        terminal = dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,timeout=False,pid=42,coverage_admitted=False)
        c.terminal_gate(terminal,start,manifest,run,image,elf)
        for key,value in (('returncode',False),('timeout',0),('timeout',True),('pid',True),('pid',43)):
            with self.assertRaises(ValueError): c.terminal_gate(dict(terminal,**{key:value}),start,manifest,run,image,elf)
        with self.assertRaises(ValueError): c.terminal_gate(terminal,dict(start,exe='/foreign'),manifest,run,image,elf)

    def test_formal775_not774_or_duplicate(self):
        ledger = [str(i) for i in range(776)]
        r.check_baseline({'coverage_admitted':True},ledger,ledger[:775])
        for bad in (ledger[:-1],ledger[:-1]+[ledger[1]],ledger[1:]+ledger[:1]):
            with self.assertRaises(ValueError): r.check_baseline({'coverage_admitted':True},bad,ledger[:775])

    def test_prepare_no_simulator(self):
        with patch.object(r.subprocess,'Popen',side_effect=AssertionError('EDA forbidden')):
            output,manifest = r.prepare(r.life.OUT/'akv-entropy-test-prepare-unused')
        self.assertEqual(manifest['expected_requests'],270)
        self.assertFalse(output.exists())
        self.assertFalse(manifest['EDA_launched'])
        self.assertTrue(str(Path(c.__file__).resolve()) in manifest['pins'])

    def test_probe_no_internal_drive(self):
        text = r.PROBE.read_text()
        self.assertNotIn('force',text.split('\n',1)[1])
        self.assertIn('{clk_i rst_ni read_range_fire read_range_vaddr read_range_bytes read_range_tag}',text)

    def wave(self, extra=False, wrong=False, post_edge=False):
        names = ['clk_i','rst_ni','read_range_fire','read_range_vaddr','read_range_bytes','read_range_tag']
        widths = [1,1,1,64,16,8]
        lines = ['$scope module '+part+' $end' for part in c.fixture.SCOPE.split('.')]
        lines += ['$var wire %d %s %s $end'%(width,str(i),name) for i,(width,name) in enumerate(zip(widths,names))]
        lines += ['$upscope $end']*len(c.fixture.SCOPE.split('.'))+['$enddefinitions $end','#0','00','11','02','b0 3','b0 4','b0 5']
        ranges = []
        bases = [self.symbols['entropy_sources']+i*256+64 for i in range(3)]
        for phase in (1,2,3):
            ranges.append((0,self.symbols['entropy_descriptors']+(phase-1)*64,64))
            if phase!=1: ranges += c.fixture.ranges(bases,128)
        if extra: ranges.insert(1,(1,bases[0],128))
        if wrong: ranges[-1] = (3,bases[-1]+0xfffffffe,128)
        for i,(role,address,size) in enumerate(ranges):
            lines += ['#'+str(i*4+1),'00','12','b'+bin(address)[2:]+' 3','b'+bin(size)[2:]+' 4','b'+bin(role<<6)[2:]+' 5',
                      '#'+str(i*4+2),'10']
            if post_edge: lines.append('02')
            lines += ['#'+str(i*4+3),'00','02']
        return '\n'.join(lines)+'\n'

    def test_actual_range_preedge_and_exact_addresses(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'ranges.vcd'
            path.write_text(self.wave(post_edge=True))
            self.assertEqual(len(c.range_wave(path,self.symbols)['accepted_ranges']),9)
            for changes in ({'extra':True},{'wrong':True}):
                path.write_text(self.wave(**changes))
                with self.assertRaises(ValueError): c.range_wave(path,self.symbols)

    def test_wrong_wave_layout_and_unknown_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/'ranges.vcd'
            for text in (self.wave().replace('$var wire 64 3','$var wire 32 3'),
                         self.wave().replace('12\n','x2\n',1)):
                path.write_text(text)
                with self.assertRaises(ValueError): c.range_wave(path,self.symbols)

    def test_independent_raw_or_rejects_stale_or_foreign(self):
        before = dict(design={'shape':'sha'},tests=['old'],metrics={'cond':{'scope':dict(width=3,checksum='1',bits='0x1')}})
        single = dict(design={'shape':'sha'},tests=['new'],metrics={'cond':{'scope':dict(width=3,checksum='1',bits='0x2')}})
        combined = dict(design={'shape':'sha'},tests=['old','new'],metrics={'cond':{'scope':dict(width=3,checksum='1',bits='0x3')}})
        c.independent_or(before,single,combined)
        for value in ('0x1','0x7'):
            bad = copy.deepcopy(combined); bad['metrics']['cond']['scope']['bits']=value
            with self.assertRaises(ValueError): c.independent_or(before,single,bad)


if __name__ == '__main__': unittest.main()
