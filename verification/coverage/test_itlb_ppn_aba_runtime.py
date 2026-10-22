import copy
import csv
import io
from pathlib import Path
import subprocess
import shlex
import tempfile
from types import SimpleNamespace
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch

import build_itlb_ppn_aba as pre
import collect_itlb_ppn_aba as c
import run_itlb_ppn_aba as r

PREFLIGHT=pre.OUT/'itlb-ppn-aba-preflight792-agent-20261008-01/preflight.json'
SEAL='8c7d34e4009f76b0e415a6900793d4e359a3fb7f118bbd96d66cd61112fbcb85'


def accepted():
    return [dict(phase=p,entry=e,vpn=pre.prior.shared.vpn(0,e),
        ppn=pre.PAGES[p==1]>>12,pte=((pre.PAGES[p==1]>>12)<<10)|0x4b,
        asid=[0x5555,0xaaaa,0x5555][p]) for p in range(3) for e in range(16)]


def csr_fixture():
    gold=[];rows=[]
    for i in range(6):
        word=((8 if i%2==0 else 15)<<20)|((i+1)<<7)|0x2073
        gold.append(SimpleNamespace(instruction=word,pc=0x80002000+4*i,gpr_writes={i+1:i+7}))
        base=dict(event='',insn=hex(word)[2:],pc=hex(gold[-1].pc)[2:],rd=str(i+1),
                  rd_wdata=hex(i+7)[2:],trap='0',mem_rmask='0',mem_wmask='0',
                  trans_id=str(i%2),order=str(i),cycle='0')
        # Independent starts may precede the prior instruction's retirement.
        for event,cycle in [('arch_start',i*10),('cvx_req',i*10+1),
                            ('cvx_resp',i*10+5),('retire',i*10+15)]:
            rows.append(dict(base,event=event,cycle=str(cycle)))
    return sorted(rows,key=lambda x:int(x['cycle'])),gold


class AcceptedSlots(unittest.TestCase):
    def test_exact_actual_entries_aba(self):c.accepted_gate(accepted())

    def test_duplicate_slot_not_inferred_from_calls(self):
        rows=accepted();rows[15]['entry']=14
        with self.assertRaisesRegex(ValueError,'slot'):c.accepted_gate(rows)

    def test_missing_extra_updates(self):
        for rows in (accepted()[:-1],accepted()+[accepted()[0]]):
            with self.assertRaises(ValueError):c.accepted_gate(rows)

    def test_wrong_pte_ppn_flags_asid_vpn(self):
        for key in ('pte','ppn','asid','vpn'):
            rows=accepted();rows[17][key]^=1
            with self.assertRaises(ValueError):c.accepted_gate(rows)

    def test_no_old_icache_a_return_as_b(self):
        rows=accepted()
        for row in rows[16:32]:
            row['ppn']=pre.PAGES[0]>>12;row['pte']=(row['ppn']<<10)|0x4b
        with self.assertRaises(ValueError):c.accepted_gate(rows)

    def test_phase_order_cannot_be_relabelled(self):
        rows=accepted();rows[0],rows[16]=rows[16],rows[0]
        with self.assertRaisesRegex(ValueError,'A/B/A'):c.accepted_gate(rows)


class ReadonlyCSR(unittest.TestCase):
    def test_realistic_overlapping_retirements(self):
        rows,gold=csr_fixture();self.assertEqual(len(c.csr_lifecycle(rows,gold)['records']),6)

    def test_wrong_pc_value_word(self):
        for key in ('pc','rd_wdata','insn'):
            rows,gold=csr_fixture();row=next(x for x in rows if x['event']=='retire')
            row[key]=hex(int(row[key],16)^4)[2:]
            with self.assertRaises(ValueError):c.csr_lifecycle(rows,gold)

    def test_late_or_missing_response(self):
        for missing in (False,True):
            rows,gold=csr_fixture();response=next(x for x in rows if x['event']=='cvx_resp')
            if missing:rows.remove(response)
            else:response['cycle']='99'
            with self.assertRaises(ValueError):c.csr_lifecycle(rows,gold)

    def test_duplicate_pending_tid_or_response(self):
        for event in ('arch_start','cvx_resp'):
            rows,gold=csr_fixture();index=next(i for i,x in enumerate(rows) if x['event']==event)
            rows.insert(index+1,dict(rows[index]))
            with self.assertRaises(ValueError):c.csr_lifecycle(rows,gold)


class RealInputs(unittest.TestCase):
    def native_fixture(self):
        out=pre.OUT/'never';record=dict(output=str(out),command=r.command(PREFLIGHT.parent/'input.elf',out))
        sim=ET.Element('test');ET.SubElement(sim,'srctest',cmdline=shlex.join(record['command']),
            workdir=str(out),seed='1',teststatus='unknown',starttime='100',finishtime='200')
        args=ET.Element('vcm_args',compvdbpath='/frozen/design.vdb')
        for metric in ('line','cond','branch','fsm','tgl'):ET.SubElement(args,'vcm_arg_data',vcm_opt='-cm '+metric)
        return sim,args,record

    def test_native_VDB_identity_exact_unknown_not_PASS(self):
        sim,args,record=self.native_fixture()
        self.assertEqual(c.native_identity(sim,args,record,'/frozen/design.vdb')['XML_teststatus'],'unknown')

    def test_native_foreign_command_seed_workdir_status(self):
        for key,value in [('cmdline','/foreign/simv'),('seed','2'),('workdir','/foreign'),('teststatus','PASS')]:
            sim,args,record=self.native_fixture();sim[0].set(key,value)
            with self.assertRaises(ValueError):c.native_identity(sim,args,record,'/frozen/design.vdb')

    def test_native_foreign_design_missing_metric_or_duplicate_test(self):
        for kind in ('design','metric','duplicate'):
            sim,args,record=self.native_fixture()
            if kind=='design':args.set('compvdbpath','/foreign')
            elif kind=='metric':args.remove(args[0])
            else:ET.SubElement(sim,'srctest')
            with self.assertRaises(ValueError):c.native_identity(sim,args,record,'/frozen/design.vdb')

    def test_plaintext_inputs_schema_not_json(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'inputs.txt';design=Path(d)/'design.vdb';vdb=Path(d)/'test.vdb'
            c.write_single_inputs(p,design,vdb)
            self.assertEqual(p.read_bytes(),(str(design)+'\n'+str(vdb)+'\n').encode())
            self.assertEqual(p.read_text().splitlines(),[str(design),str(vdb)])
            with self.assertRaises(FileExistsError):c.write_single_inputs(p,design,vdb)

    def test_inputs_foreign_newline_or_relative_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for path in (Path('relative'),Path(d)/'bad\n.vdb'):
                with self.assertRaises(ValueError):c.write_single_inputs(Path(d)/'inputs',path,Path(d)/'vdb')

    def test_actual_source_layout_and_parent_type(self):
        pins=c.source_layout()
        self.assertIn(str(pre.ROOT/'hardware/deps/cva6/core/cva6_mmu/cva6_mmu.sv'),pins)
        self.assertEqual(c.axi.layouts()['noc_req_o'][0],281)
        self.assertEqual(c.axi.layouts()['noc_resp_i'][0],84)
        content=(0x801aa<<10)|0x4b
        packed=(1<<188)|(content<<64)
        self.assertEqual(int(c.axi.core.support.packed_field(format(packed,'0189b'),'content'),2),content)

    def test_actual_spike_reference_and_elf_overlap_proof(self):
        q=pre.life.read_bound(PREFLIGHT,SEAL)
        symbols,layout=pre.elf_contract(PREFLIGHT.parent/'input.elf')
        self.assertEqual(symbols,q['symbols'])
        self.assertEqual([x['address'] for x in layout['pages']],list(pre.PAGES))
        ref=pre.reference(PREFLIGHT.parent/'spike.trace',symbols)
        self.assertEqual(pre.architecture.reference_counts(ref,symbols),q['counts'])
        self.assertEqual(len(ref),37340)
        self.assertEqual(q['software_checks'],3846)

    def test_actual_full_prepare_without_eda(self):
        out=pre.OUT/'itlb-ppn-aba-host-test-never-run'
        self.assertFalse(out.exists())
        record=r.prepared_record(PREFLIGHT,SEAL,out)
        self.assertEqual(r.validate(record),out)
        self.assertEqual(record['baseline_count'],792)
        for path in (c.CONVERTER,r.PROBE,pre.BASE/'combined-inputs.txt'):
            self.assertIn(str(path),record['pins'])
        self.assertFalse(out.exists())
        for key,value in [('service','foreign.service'),('timeout_s',True),
                          ('baseline_count',791),('automatic_retry',True)]:
            bad=copy.deepcopy(record);bad[key]=value
            with self.assertRaises(ValueError):r.validate(bad)

    def test_command_bounded_frozen_no_fsdb(self):
        cmd=r.command(PREFLIGHT.parent/'input.elf',pre.OUT/'never')
        self.assertEqual(cmd[0],str(pre.life.IMAGE))
        self.assertIn('+NO_FSDB',cmd);self.assertIn('line+cond+fsm+tgl+branch',cmd)
        self.assertIn('+ntb_random_seed=1',cmd)
        self.assertEqual(cmd[-1],str(r.PROBE))

    def test_native_ownership_foreign_cgroup(self):
        out=pre.OUT/'never';cmd=r.command(PREFLIGHT.parent/'input.elf',out)
        image=str(pre.life.IMAGE.resolve());original=r.os.readlink
        def readlink(path):
            if isinstance(path,Path) and path.parent==Path('/proc/123'):
                return image if path.name=='exe' else str(out)
            return original(path)
        def text(path,*args,**kwargs):
            if path.name=='cgroup':return '0::/system.slice/foreign.service\n'
            return '1 (simv) '+' '.join(['0']*20)
        with patch.object(r.os,'readlink',side_effect=readlink),patch.object(Path,'read_text',text),\
             patch.object(Path,'read_bytes',return_value=b'\0'.join(x.encode() for x in cmd)+b'\0'):
            with self.assertRaisesRegex(ValueError,'service'):r.ownership(123,out,cmd)


class TclEntry(unittest.TestCase):
    def execute(self,count='1'):
        mock='''proc show {args} {}\nproc dump {args} {
          if {[lindex $args 0] eq "-file"} {return fid}
          if {[lindex $args 0] ne "-add" || [lrange $args end-2 end] ne "-depth 0 -aggregates"} {error "bad dump"}
          return COUNT
        }\nproc run {} {puts MOCK_RUN}\n'''.replace('COUNT',count)
        return subprocess.run(['tclsh'],input=mock+'source {'+str(r.PROBE)+'}\n',
                              text=True,capture_output=True,check=False)

    def test_full_standalone_entry_all13_observation_objects(self):
        result=self.execute();self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        lines=result.stdout.splitlines()
        self.assertEqual(sum(x.startswith('ITLB_EXEC_OBJECT ') for x in lines),13)
        self.assertEqual(lines.count('ITLB_EXEC_READY'),1)
        self.assertIn('MOCK_RUN',lines)
        text=r.PROBE.read_text()
        for command in ('\nforce ','\nstop ','\ndeposit '):self.assertNotIn(command,text)

    def test_missing_invalid_dump_rejected_before_run(self):
        for count in ('0','-1','unknown'):
            result=self.execute(count)
            self.assertEqual(result.returncode,1)
            self.assertIn('ITLB_EXEC_ERROR',result.stdout)
            self.assertNotIn('MOCK_RUN',result.stdout)


class PackedWavePipeline(unittest.TestCase):
    def fixture(self,path,wrong_ppn=False,postedge_unknown=False,width=189):
        fields={'ara_tb.clk':1,'ara_tb.rst_n':1,
                c.original.CORE+'.noc_req_o':281,c.original.CORE+'.noc_resp_i':84}
        for name,w in [('update_i',width),('replace_en',16),('lu_hit_o',1),('lu_access_i',1),
                       ('lu_asid_i',16),('lu_vaddr_i',64),('plru_tree_q',30),('flush_i',1),('s_st_enbl_i',1)]:
            fields[c.SCOPE+'.'+name]=w
        ids={name:'x'+str(i) for i,name in enumerate(fields)}
        lines=['$timescale 100fs $end']
        for name,w in fields.items():
            components=name.split('.')
            lines.extend('$scope module '+s+' $end' for s in components[:-1])
            lines.append('$var reg '+str(w)+' '+ids[name]+' '+components[-1]+' $end')
            lines.extend('$upscope $end' for _ in components[:-1])
        lines.extend(['$enddefinitions $end','#0'])
        def emit(values):
            for name,value in values.items():
                bits='x'*fields[name] if value=='x' else format(value,'0'+str(fields[name])+'b')
                lines.append(bits+ids[name] if fields[name]==1 else 'b'+bits+' '+ids[name])
        emit(dict.fromkeys(fields,0))
        for i,row in enumerate(accepted()):
            pte=row['pte'] ^ (0x400 if wrong_ppn and i==17 else 0)
            packet=(1<<188)|(row['vpn']<<159)|(row['asid']<<143)|(1<<128)|(pte<<64)
            lines.append('#'+str(i*10+1))
            emit({'ara_tb.clk':0,'ara_tb.rst_n':1,c.SCOPE+'.update_i':packet,
                  c.SCOPE+'.replace_en':1<<row['entry'],c.SCOPE+'.plru_tree_q':i,
                  c.SCOPE+'.lu_asid_i':row['asid'],c.SCOPE+'.lu_vaddr_i':pre.address(row['phase'],i%16)})
            lines.append('#'+str(i*10+5))
            emit({'ara_tb.clk':1,c.SCOPE+'.update_i':'x' if postedge_unknown else 0})
        lines.append('#481')
        emit({'ara_tb.clk':0,c.SCOPE+'.update_i':0,c.SCOPE+'.lu_hit_o':1,
              c.SCOPE+'.lu_access_i':1,c.SCOPE+'.s_st_enbl_i':1})
        lines.append('#485');emit({'ara_tb.clk':1})
        path.write_text('\n'.join(lines)+'\n')

    def test_full_source_bound_native_packed_preedge_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'fixture.vcd';self.fixture(p,postedge_unknown=True)
            result=c.waveform(p)
            self.assertEqual(len(result['accepted_full_PTEs']),48)
            self.assertTrue(result['pre_timebucket_sampling'])
            self.assertTrue(result['actual_all16_A_B_A'])
            self.assertEqual(result['accepted_full_PTEs'][17]['ppn'],0x801aa)
            self.assertFalse(result['serialized_direction_order_calibrated'])

    def test_full_native_packed_wrong_ppn_or_width_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for args in ({'wrong_ppn':True},{'width':190}):
                p=Path(d)/'fixture.vcd';self.fixture(p,**args)
                with self.assertRaises(ValueError):c.waveform(p)


if __name__=='__main__':unittest.main()
