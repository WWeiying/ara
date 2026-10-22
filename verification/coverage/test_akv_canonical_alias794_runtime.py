"""Actual native ELF replay plus focused corruption tests; never opens DUT logs."""
import copy
import json
import shlex
import unittest
import xml.etree.ElementTree as E

import collect_akv_canonical_alias794 as c
import run_akv_canonical_alias794 as r


class Native(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=c.life.read_bound(r.PRE/'preflight-manifest.json',r.PRE_SHA)
        cls.blob=r.ELF.read_bytes();cls.sym=cls.pre['symbols']
        cls.model,cls.dry=c.replay(cls.blob,cls.sym)
        cls.rows=[];cls.arch=None
        # Synthetic trace is explicitly an adapter fixture, not actual DUT evidence.
        m=c.Model(cls.blob,cls.sym);ret=[]
        while not m.terminal:
            e=m.step()
            if not e['trap']:ret.append(dict(e,event='retire',order=len(ret),cycle=10000+len(ret),
                mem_wdata=e.get('store_value',0)))
        for seq,q in enumerate(cls.model.requests):
            cyc=20*seq;word=q['word'];backend=word&127 in (7,0x27,0x5b)
            base=dict(order=seq,insn=word,trans_id=seq%8,pc=0,port=seq%8,rd_wdata=0,trap=0)
            cls.rows.append(dict(base,event='arch_start',cycle=cyc))
            cls.rows.append(dict(base,event='cvx_req',cycle=cyc+1))
            if backend:cls.rows.append(dict(base,event='uop_alloc',cycle=cyc+2))
            if backend:cls.rows.append(dict(base,event='uop_done',cycle=cyc+10))
            cls.rows.append(dict(base,event='cvx_resp',cycle=cyc+12,rd_wdata=q['response_value']))
        cls.rows+=ret;cls.arch=c.lifecycle(cls.rows,cls.model)
        cls.ret=ret

    def test_actual_native_ELF_dry(self):
        self.assertEqual(self.dry['steps'],116614)
        self.assertEqual(len(self.model.commands),10);self.assertEqual(len(self.model.traps),2)
        self.assertEqual(self.model.counts['vstore'],128)
        self.assertFalse(self.dry['native_custom_Spike'])

    def test_full_scalar_fixture(self):
        _,result=c.replay(self.blob,self.sym,self.rows)
        self.assertEqual(result['matched_retirements'],116612)
        self.assertEqual(result['skipped_retirements'],0)

    def test_scalar_fault_PC_negative(self):
        rows=copy.deepcopy(self.rows);row=next(v for v in rows if v['event']=='retire' and v['pc']==self.sym['akva_site_0']);row['pc']+=4
        with self.assertRaisesRegex(ValueError,'pc mismatch'):c.replay(self.blob,self.sym,rows)

    def test_native_command_opcode_negative(self):
        bad=bytearray(self.blob)
        from io import BytesIO
        from elftools.elf.elffile import ELFFile
        seg=next(s for s in ELFFile(BytesIO(self.blob)).iter_segments() if s['p_type']=='PT_LOAD' and
            s['p_vaddr']<=self.sym['akva_site_0']<s['p_vaddr']+s['p_filesz'])
        bad[seg['p_offset']+self.sym['akva_site_0']-seg['p_vaddr']]^=0x80
        with self.assertRaisesRegex(ValueError,'custom sites'):c.Model(bytes(bad),self.sym)

    def test_full_regions_negative(self):
        for name in ('akva_pages','entropy_snapshots','entropy_csrs','akva_traps','akva_leaf','akva_restored'):
            bad=dict(self.model.memory);bad[self.sym[name]]^=1
            with self.subTest(name=name),self.assertRaises(ValueError):c.case.validate_memory(bad,self.sym)

    def test_backend_owner_negative(self):
        rows=copy.deepcopy(self.rows);next(v for v in rows if v['event']=='uop_done')['port']^=1
        with self.assertRaises(ValueError):c.lifecycle(rows,self.model)

    def vector_rows(self):
        names=('cycle','arch_seq','vid','lane','source','insn','use_vd','vd','eew','vl','vstart','addr','be','wdata')
        config={k:'0' for k in names};config.update(event='config',nr_lanes='4',vlen_bits='1024')
        rows=[config];seeds=[s for s,x in self.arch['allocations'].items() if x['insn']&127==7]
        effects={seeds[e['vd']] if e['kind']=='seed' else self.arch['commands'][e['phase']]['seq']:e for e in self.model.vector_effects}
        commands={x['seq']:x for x in self.arch['commands']}
        for seq,alloc in self.arch['allocations'].items():
            word=alloc['insn'];op=word&127;cmd=commands.get(seq)
            use=int(cmd['write_bytes']>0) if cmd else int(op==7)
            vd=cmd['vd'] if cmd and use else (word>>7&31 if use else 0)
            row=dict(config,event='alloc',cycle=str(alloc['cycle']),arch_seq=str(seq),vid=str(alloc['port']),
                insn='%08x'%word,use_vd=str(use),vd=str(vd),eew='1',vl=str(64 if op!=0x5b or use else 1))
            rows.append(row)
            if seq in effects:
                data=bytes.fromhex(effects[seq]['data'])
                for chunk in range(4):
                    for lane in range(4):
                        b=bytearray()
                        for byte in range(8):
                            slot,within=divmod(byte,2);natural=((slot&1)<<1)|(slot>>1)
                            b.append(data[chunk*32+(natural*4+lane)*2+within])
                        rows.append(dict(row,event='write',cycle=str(alloc['cycle']+1),lane=str(lane),source='4',
                            addr=str(vd*4+chunk),be='ff',wdata='%016x'%int.from_bytes(b,'little')))
            rows.append(dict(row,event='done',cycle=str(self.arch['done'][seq]['cycle'])))
        return rows

    def test_native_vector_all_bytes(self):
        self.assertEqual(c.vectors(self.vector_rows(),self.model,self.arch),dict(seed_bytes=4096,custom_bytes=768,
            full_frames=4,snapshot_bytes=16384,unknown_or_skipped_bytes=0))

    def test_native_vector_corruption_missing_duplicate(self):
        for mode in ('data','source','missing','duplicate','neighbor','eew','owner'):
            rows=self.vector_rows();i=next(i for i,x in enumerate(rows) if x['event']=='write' and x['arch_seq'] in
                {str(k['seq']) for k in self.arch['commands']})
            if mode=='missing':rows.pop(i)
            elif mode=='duplicate':rows.insert(i,dict(rows[i]))
            else:
                field,value={'data':('wdata','0'),'source':('source','3'),'neighbor':('addr','0'),
                    'eew':('eew','2'),'owner':('vid',str((int(rows[i]['vid'])+1)%8))}[mode]
                rows[i][field]=value
            with self.subTest(mode=mode),self.assertRaises(ValueError):c.vectors(rows,self.model,self.arch)

    def test_extra_command_negative(self):
        rows=copy.deepcopy(self.rows);row=next(v for v in rows if v['event']=='cvx_resp' and v['insn']&127==0x5b);rows.insert(rows.index(row)+1,copy.deepcopy(row))
        with self.assertRaises(ValueError):c.lifecycle(rows,self.model)

    def wave(self):
        samples=[]
        def blank():return {k:0 for k in c.WIDTHS}|{'rst_ni':1}
        for n,cmd in enumerate(self.arch['commands']):
            slot=n%5;phase=n//5;b=blank()
            a=self.sym['entropy_descriptors']+64*phase if slot==0 else slot-1 if slot in (1,2,3) else 0
            b.update(command_fire=1,command_i=(0,2,2,2,3)[slot],command_id_i=self.arch['allocations'][cmd['seq']]['port'],
                command_vd_i=cmd['word']>>7&31,command_selector_i=a,command_descriptor_address_i=a)
            samples.append((b,dict(b)))
            if slot==0:
                for role in range(4):
                    va=self.sym['entropy_descriptors']+64*phase if role==0 else c.case.static.ALIASES[phase][role-1]+64
                    pa=va if role==0 else self.sym['akva_pages']+(role-1)*4096+64;size=64 if role==0 else 128
                    b=blank();b.update(read_range_fire=1,read_range_vaddr=va,read_range_bytes=size,read_range_tag=role<<6)
                    samples.append((b,dict(b)))
                    b=blank();b.update({'i_read_engine.translation_complete':1,'i_read_engine.mmu_req_o':1,
                        'i_read_engine.mmu_valid_i':1,'i_read_engine.en_ld_st_translation_i':1,'i_read_engine.plan_state_q':2,
                        'i_read_engine.mmu_vaddr_o':va,'i_read_engine.mmu_paddr_i':pa})
                    a=dict(b);a.update({'i_read_engine.ar_addr_q':pa,'i_read_engine.ar_cursor_vaddr_q':va,'i_read_engine.ar_chunk_bytes_q':size})
                    samples.append((b,a))
                    b=blank();b.update(axi_ar_valid_o=1,axi_ar_ready_i=1)
                    b.update({'i_read_engine.ar_addr_q':pa,'i_read_engine.ar_cursor_vaddr_q':va,'i_read_engine.ar_chunk_bytes_q':size})
                    samples.append((b,dict(b)))
            b=blank();b.update(success_valid_o=1,context_ready_o=int(slot!=4));samples.append((b,dict(b)))
        return samples

    def test_complete_MMU_AR_fixture(self):
        got=c.sample_gate(self.wave(),self.sym,self.arch)
        self.assertEqual(got['actual_accepted_translation_count'],8)

    def test_translation_negatives(self):
        for key in ('i_read_engine.mmu_req_o','i_read_engine.mmu_valid_i','i_read_engine.en_ld_st_translation_i',
                    'i_read_engine.mmu_vaddr_o','i_read_engine.mmu_paddr_i'):
            samples=self.wave();b,a=next(p for p in samples if p[0]['i_read_engine.translation_complete']);b[key]^=1
            with self.subTest(key=key),self.assertRaises(ValueError):c.sample_gate(samples,self.sym,self.arch)

    def test_unknown_accepted_PA(self):
        samples=self.wave();b,a=next(p for p in samples if p[0]['i_read_engine.translation_complete']);b['i_read_engine.mmu_paddr_i']=None
        with self.assertRaises(ValueError):c.sample_gate(samples,self.sym,self.arch)

    def test_postcapture_drift(self):
        samples=self.wave();b,a=next(p for p in samples if p[0]['i_read_engine.translation_complete']);a['i_read_engine.ar_addr_q']^=16
        with self.assertRaises(ValueError):c.sample_gate(samples,self.sym,self.arch)

    def test_AR_missing_duplicate_wrongPA(self):
        for mode in ('missing','duplicate','wrong'):
            samples=self.wave();i=next(i for i,p in enumerate(samples) if p[0]['axi_ar_valid_o'])
            if mode=='missing':samples.pop(i)
            elif mode=='duplicate':samples.insert(i,copy.deepcopy(samples[i]))
            else:samples[i][0]['i_read_engine.ar_addr_q']^=4096
            with self.subTest(mode=mode),self.assertRaises(ValueError):c.sample_gate(samples,self.sym,self.arch)

    def test_engine_owner_selector_negatives(self):
        for key in ('command_id_i','command_vd_i','command_selector_i','command_descriptor_address_i'):
            samples=self.wave();samples[0][0][key]^=1
            with self.subTest(key=key),self.assertRaises(ValueError):c.sample_gate(samples,self.sym,self.arch)

    def test_contract_no_custom_faults(self):
        row=dict(requests=198,responses=198,exceptions=0,mmu_request_cycles=8,protocol_errors=0,outstanding=0,req_stalled=0,resp_stalled=0)
        def log(r):return '[ARA_CONTRACT] '+' '.join('%s=%s'%p for p in r.items())
        self.assertEqual(c.contract(log(row),198),row)
        for k in ('exceptions','protocol_errors','outstanding','responses'):
            bad=dict(row);bad[k]+=1
            with self.subTest(key=k),self.assertRaises(ValueError):c.contract(log(bad),198)

    def test_probe_exact_objects(self):
        text=r.PROBE.read_text();names=text.split('foreach name {',1)[1].split('}',1)[0].split()
        self.assertEqual(set(names),set(c.WIDTHS));self.assertEqual(len(names),len(c.WIDTHS))
        self.assertNotIn('force ',text)

    def test_native_XML_identity(self):
        run=c.life.OUT/'alias-fixture';cmd=['/simv','+PRELOAD=/input.elf']
        sim=E.fromstring('<test><srctest seed="1" teststatus="unknown" starttime="1" finishtime="2"/></test>')
        sim[0].set('workdir',str(run));sim[0].set('cmdline',shlex.join(cmd))
        args=E.fromstring('<vcm_args compvdbpath="/compile"/>')
        for metric in ('line','cond','fsm','tgl','branch'):E.SubElement(args,'vcm_arg_data',vcm_opt='-cm '+metric)
        c.native_identity(sim,args,run,cmd,'/compile')
        for key,value in (('workdir','/foreign'),('cmdline','/wrong'),('finishtime','0')):
            bad=copy.deepcopy(sim);bad[0].set(key,value)
            with self.subTest(key=key),self.assertRaises(ValueError):c.native_identity(bad,args,run,cmd,'/compile')

    def test_terminal_typed_timeout_identity(self):
        out=c.life.OUT/'alias-fixture';m=dict(pins={str(c.life.IMAGE):'i',str(r.ELF):'e'},command=['simv'],timeout_s=900)
        started=dict(pid=4,starttime=10,exe=str(c.life.IMAGE),cwd=str(out),executable_sha256='i',input_elf=str(r.ELF),
            elf_sha256='e',command=['simv'],budget_s=900,live_identity_verified=True)
        status=dict(status='SIMULATION_EXITED_NOT_ADMITTED',returncode=0,timeout=False,pid=4,coverage_admitted=False)
        c.terminal(status,started,m,out,r.ELF)
        for key,value in (('timeout',0),('returncode',False),('pid',True)):
            bad=dict(status);bad[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):c.terminal(bad,started,m,out,r.ELF)
        bad=dict(started,budget_s=600)
        with self.assertRaises(ValueError):c.terminal(status,bad,m,out,r.ELF)


if __name__=='__main__':unittest.main()
