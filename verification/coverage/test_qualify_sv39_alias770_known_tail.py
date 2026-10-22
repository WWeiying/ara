from dataclasses import replace
import copy
import json
import unittest
import xml.etree.ElementTree as ET
import qualify_sv39_alias770_known_tail as q
from test_qualify_sv39_alias770_terminal import ArchitectureTests


class KnownTailTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reference=q.prior.run.reference.prior.build.parse_spike_commits(q.prior.run.PRE/'spike.trace')
        cls.writers=q.writer_shape(cls.reference)

    def native_fixture(self):
        activities={};mapping={};row=0
        for seq,c in enumerate(self.writers):
            mapping[seq]=next(i for i,x in enumerate(self.reference) if x is c)
            a=q.prior.vc.ArchActivity(instruction=c.instruction);activities[seq]=a
            groups=[]
            if seq in (4,5):groups.append((3,128,{min(c.vector_writes):int.from_bytes(b'\x5a'*128,'little')},0))
            groups.append((4 if c.instruction&0x7f==7 else 0,c.vector_vl*c.vector_sew//8,c.vector_writes,20))
            for source,active,values,offset in groups:
                for reg,value in sorted(values.items()):
                    for word in range(4):
                        for lane in range(4):
                            positions=[word*32+q.prior.vc._deshuffle_byte(lane*8+b,4,0 if seq<4 else 3) for b in range(8)]
                            enabled=[b for b,p in enumerate(positions) if (reg-min(values))*128+p<active]
                            if not enabled:continue
                            self.assertEqual(enabled,list(range(8)))
                            data=sum(((value>>(8*p))&255)<<(8*b) for b,p in enumerate(positions))
                            a.writes.append(q.prior.vc.VectorWrite(row=row,cycle=seq*100+offset+word,
                                arch_seq=seq,vid=seq%8,lane=lane,source=source,instruction=c.instruction,
                                eew=0 if seq<4 else 3,addr=reg*4+word,be=255,data=data,known_be=255));row+=1
        return activities,mapping

    def test_actual_program_source_derived_counts(self):
        intervals=q.intervals(self.reference)
        self.assertEqual(sum(r['active'] for r in intervals),7360)
        self.assertEqual(sum(r['maintenance'] for r in intervals),256)
        self.assertEqual(sum(r['merged'] for r in intervals),7488)
        a,m=self.native_fixture();r=q.native_exact(a,m,self.reference)
        self.assertEqual(r['accepted_write_bytes'],7616)

    def test_frozen_source_and_full_reshuffle_negative(self):
        text=q.DISPATCH.read_text();proof=q.source_contract(text)
        book=q.life.read_bound(q.life.OUT/'repaired-aligned-build-20260930-01/build-source-pins.json',
            '6d29e3ee19e7ac361d7a875b2acaacb6c9d17b4a976491538e9c6f5c918b761b')
        self.assertEqual(q.life.digest(q.DISPATCH),book[str(q.life.ROOT/'hardware/src/ara_dispatcher.sv')])
        for statement in proof['statements']:
            with self.subTest(statement=statement):
                with self.assertRaises(ValueError):q.source_contract(text.replace(statement,'REMOVED'))

    def test_actual_program_vector_records(self):
        fixture=ArchitectureTests();fixture.reference=self.reference
        r=fixture.vector();r['compared_bytes']=7488
        for record,interval in zip(r['instructions'],q.intervals(self.reference)):
            record['compared_bytes']=interval['merged']
        q.vector_exact(r,self.reference)
        r['instructions'][6]['compared_bytes']=128
        with self.assertRaises(ValueError):q.vector_exact(r,self.reference)

    def test_native_corrupt_unknown_source_EEW_prestate_and_result(self):
        for change in ({'known_be':127},{'source':1},{'eew':1},{'data':0}):
            with self.subTest(change=change):
                a,m=self.native_fixture();a[4].writes[0]=replace(a[4].writes[0],**change)
                with self.assertRaises(ValueError):q.native_exact(a,m,self.reference)
        a,m=self.native_fixture();a[4].writes[-1]=replace(a[4].writes[-1],data=0)
        with self.assertRaises(ValueError):q.native_exact(a,m,self.reference)

    def test_native_missing_duplicate_tail_extra_owner(self):
        a,m=self.native_fixture();a[4].writes.pop(0)
        with self.assertRaises(ValueError):q.native_exact(a,m,self.reference)
        a,m=self.native_fixture();a[4].writes.insert(0,a[4].writes[0])
        with self.assertRaises(ValueError):q.native_exact(a,m,self.reference)
        a,m=self.native_fixture();a[6].writes.insert(0,replace(a[4].writes[0],arch_seq=6,instruction=a[6].instruction))
        with self.assertRaises(ValueError):q.native_exact(a,m,self.reference)

    def test_scalar_compressed_memory_fullprogram_and_corruption(self):
        fixture=ArchitectureTests();fixture.reference=self.reference
        fixture.pre=json.loads((q.prior.run.PRE/'preflight.json').read_bytes())
        rows=fixture.retire_fixture();r=q.scalar_memory_exact(rows,self.reference)
        self.assertGreater(r['compressed_memory_accesses'],0)
        victim=next(x for x in rows if int(x['insn'],16)&3!=3 and int(x['mem_wmask'],16))
        victim['mem_wdata']=hex(int(victim['mem_wdata'],16)^1)
        with self.assertRaises(ValueError):q.scalar_memory_exact(rows,self.reference)
        rows=fixture.retire_fixture()
        victim=next(x for x in rows if int(x['insn'],16)&3!=3 and int(x['mem_rmask'],16))
        victim['mem_addr']=hex(int(victim['mem_addr'],16)+8)
        with self.assertRaises(ValueError):q.scalar_memory_exact(rows,self.reference)

    def test_siminfo_exact_and_command_cwd_incomplete_extra_reject(self):
        info=ET.Element('siminfo');node=ET.SubElement(info,'srctest',dict(
            cmdline=__import__('shlex').join(q.prior.run.command(q.prior.RUN)),
            workdir=str(q.prior.RUN),starttime='1',finishtime='2'))
        q.siminfo_exact(info,q.prior.run.command(q.prior.RUN))
        for key,value in (('cmdline','false'),('workdir','/tmp'),('finishtime','0'),('starttime','0')):
            bad=copy.deepcopy(info);bad[0].set(key,value)
            with self.assertRaises(ValueError):q.siminfo_exact(bad,q.prior.run.command(q.prior.RUN))
        info.append(copy.deepcopy(node))
        with self.assertRaises(ValueError):q.siminfo_exact(info,q.prior.run.command(q.prior.RUN))


if __name__=='__main__':unittest.main()
