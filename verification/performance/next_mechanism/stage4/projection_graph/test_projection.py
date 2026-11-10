import csv
import io
from pathlib import Path
import subprocess
import tempfile
import unittest

import contract as c
import build as b
import check as check


ORACLE=dict(output_hash=0x1122334455667788,packed_hash=0x8877665544332211)


def firmware_log():
    lines=['STAGE4_CHAIN_SCOPE trials=4 m=4 k=1536 q=1536 v=256 key=256 cache_both=1 parallel_both=1 full_ggml=0']
    for trial,arm in enumerate(c.ORDER):
        for part,n in enumerate(c.WIDTHS):
            for _ in range(n//32):
                # Sequence is global, not reset at a trial/part boundary.
                index=sum(line.startswith('[QBS_PERF] ') for line in lines)
                weight=32*6*(210 if part==1 else 144)
                row=dict(seq=index+1,m=4,n=32,vlen=1024,lanes=4,success=1,fault=0,
                    validation_fault=0,validation_error=0,read_fault=0,weight_bytes=weight,
                    activation_bytes=7008,payload_bytes=16+weight+7008,tiles=48,
                    useful_pairs=196608,pair_capacity=196608,dot_active_cycles=6144,
                    accumulator_updates=768,activation_access=0,context_fill_count=0,
                    context_reuse_count=0,context_reuse_block_count=0,context_read_bytes=0,
                    activation_axi_bytes_saved=0,context_replay_cycles=0,
                    context_replay_compute_overlap_cycles=0,context_validation_fault_count=0,
                    busy_cycles=7000,fp_uop_issue=2304 if part==1 else 3072)
                row.update({key:7000 if key=='phase_compute_cycles' else 0 for key in check.PHASES})
                lines.append('[QBS_PERF] '+' '.join(k+'='+str(v) for k,v in row.items()))
        row=dict(id=trial,candidate=arm,tag=3+arm,admit=6000,prep=60000 if arm else 65000,
            execute=500000,total=566100 if arm else 571100,queries=3,hits=2,misses=1,stores=1,
            producers=1,compared=49152,copied=45600,retained=0,fcsr=17,vcsr=5,vstart=0,
            output_hash=ORACLE['output_hash'],packed_hash=ORACLE['packed_hash'],errors=0)
        lines.append('STAGE4_CHAIN_TRIAL '+' '.join(k+'='+
            (format(v,'x') if k.endswith('_hash') else str(v)) for k,v in row.items()))
    lines += ['STAGE4_CHAIN_DONE trials=4 commands=256 outputs_per_trial=8192 errors=0',
              'Core Test *** SUCCESS ***','UVM_ERROR : 0','UVM_FATAL : 0']
    return '\n'.join(lines)+'\n'


def vector_log():
    fields='cycle event arch_seq vid insn use_vd vd eew vl vstart nr_lanes vlen_bits lane source addr be wdata'.split()
    stream=io.StringIO();writer=csv.DictWriter(stream,fieldnames=fields);writer.writeheader()
    cycle=0

    def emit(event,**values):
        nonlocal cycle
        row=dict.fromkeys(fields,'0');row.update(cycle=cycle,event=event,nr_lanes=4,vlen_bits=1024)
        row.update(values);writer.writerow(row);cycle+=1

    emit('config')
    for seq in range(1,257):
        base=dict(arch_seq=seq,vid=seq%8,insn='06b5045b',use_vd=1,vd=8,eew=2,vl=128,vstart=0)
        emit('alloc',**base)
        for lane in range(4):
            for address in range(32,48):
                emit('write',**base,lane=lane,addr=address,source=4,be='ff',wdata='0123456789abcdef')
        emit('done',**base)
    return stream.getvalue()


ENTRIES={name:dict(pc=0x80000000+4*i,end=0x80000004+4*i,insn=0x13)
         for i,name in enumerate(c.ENTRIES)}


def commit_log():
    lines=['cycle,event,pc,insn,trap'];cycle=0
    for arm in c.ORDER:
        for name in [c.ENTRIES[arm]]+[c.ENTRIES[2]]*64:
            row=ENTRIES[name];cycle+=1
            lines.append(f'{cycle},retire,{row["pc"]:x},{row["insn"]:x},0')
    return '\n'.join(lines)+'\n'


class ProjectionTest(unittest.TestCase):
    def test_frozen_real_data_and_subgroup_sums(self):
        pins=c.data_contract();self.assertGreater(len(pins),8)
        self.assertEqual(c.check_prepared_bytes((c.BASE/'activation_q8k_m4.bin').read_bytes())['bytes'],7008)

    def test_prepared_sum_mutation(self):
        raw=bytearray((c.BASE/'activation_q8k_m4.bin').read_bytes());raw[1040]^=1
        with self.assertRaisesRegex(ValueError,'subgroup sum'): c.check_prepared_bytes(raw)

    def test_log_strong_baseline(self):
        result=check.check_log(firmware_log(),ORACLE)
        self.assertEqual(result['commands'],256)
        self.assertEqual(result['outputs_checked_by_target'],32768)
        self.assertFalse(result['full_ggml'])

    def test_cache_and_producer_mutations(self):
        text=firmware_log()
        for before,after in (('tag=3','tag=2'),('parallel_both=1','parallel_both=0'),
            ('hits=2','hits=1'),('misses=1','misses=3'),('producers=1','producers=3'),
            ('retained=0','retained=31584'),('compared=49152','compared=0')):
            with self.subTest(before=before),self.assertRaises(ValueError):
                check.check_log(text.replace(before,after,1),ORACLE)

    def test_flags_outputs_and_duplicates(self):
        text=firmware_log()
        for changed in (text.replace('fcsr=17','fcsr=1',1),text.replace('vstart=0','vstart=1',1),
            text.replace('output_hash=1122334455667788','output_hash=1122334455667789',1),
            text.replace('errors=0','errors=1',1),text+text.splitlines()[-4]+'\n'):
            with self.assertRaises(ValueError): check.check_log(changed,ORACLE)

    def test_missing_native_work_or_phase_corruption(self):
        text=firmware_log()
        line=next(x for x in text.splitlines() if x.startswith('[QBS_PERF]'))
        for changed in (text.replace(line+'\n','',1),text.replace('activation_access=0','activation_access=1',1),
            text.replace('weight_bytes=27648','weight_bytes=27504',1),
            text.replace('phase_compute_cycles=7000','phase_compute_cycles=6999',1)):
            with self.assertRaises(ValueError): check.check_log(changed,ORACLE)

    def test_arithmetic_work_unchanged_across_arms(self):
        text=firmware_log();rows=text.splitlines()
        starts=[i for i,x in enumerate(rows) if x.startswith('[QBS_PERF]')]
        rows[starts[64]]=rows[starts[64]].replace('fp_uop_issue=3072','fp_uop_issue=3073')
        with self.assertRaisesRegex(ValueError,'Arithmetic work'):
            check.check_log('\n'.join(rows),ORACLE)

    def test_vector_exact_alloc_write_done(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'vector.csv';p.write_text(vector_log())
            self.assertEqual(check.check_vector(p),dict(commands=256,result_bytes=131072,alloc_write_done_checked=True))

    def test_vector_missing_mask_and_qbacc_mutations(self):
        text=vector_log()
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'vector.csv'
            for changed in (text.replace(',ff,0123456789abcdef',',0f,0123456789abcdef',1),
                            text.replace('06b5045b','16b5045b',1),
                            '\n'.join(text.splitlines()[:-1])+'\n'):
                p.write_text(changed)
                with self.assertRaises(ValueError): check.check_vector(p)

    def test_fixed_api_and_no_active_helper_import(self):
        source=(Path(__file__).parent/'producer.cpp').read_text()
        self.assertIn('::quantize<true>',source)
        self.assertIn('qbs_experimental_m4_preflight::quantize',source)
        self.assertNotIn('software/qbs/experimental',source)
        self.assertEqual(c.ORDER,(0,1,1,0))
        self.assertEqual(c.SDK_COMMIT,'d3d92ad72a3cabb91e8c333186160ae422f0866b')

    def test_frozen_candidate_gate_rejects_active_root_path(self):
        with tempfile.TemporaryDirectory() as temp:
            p=Path(temp)/'helper.h';receipt=Path(temp)/'receipt.json'
            p.write_text('not a real candidate\n');receipt.write_text('{"state":"PASS"}\n')
            with self.assertRaisesRegex(ValueError,'frozen OUT'):
                b.frozen_candidate(p,c.sha(p),receipt,c.sha(receipt))

    def test_no_generic_oracle_fork_in_target(self):
        root=Path(__file__).parent
        self.assertIn('qbs_ref_execute',(root/'oracle.c').read_text())
        self.assertNotIn('qbs_ref_execute',(root/'main.cpp').read_text())
        self.assertIn('key.producer_tag=candidate?4u:3u',(root/'main.cpp').read_text())
        self.assertNotIn('pthread',(root/'build.py').read_text())

    def test_generic_fallback_is_exact_frozen_production_body(self):
        generic=c.GENERIC.read_text()
        body=generic.split('extern "C" {',1)[1].rsplit('}',1)[0].strip()
        production=subprocess.check_output(['git','-C',str(c.LLAMA),'show',
            c.LLAMA_COMMIT+':ggml/src/ggml-cpu/repack.cpp'],text=True)
        self.assertIn(body,production)

    def test_actual_entry_order_not_cache_labels(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'commit.csv';path.write_text(commit_log())
            got=check.check_entries(path,ENTRIES)
            self.assertEqual(got['counts'],dict(zip(c.ENTRIES,(2,2,256))))

    def test_entry_missing_extra_mispc_insn_and_trap(self):
        text=commit_log();rows=text.splitlines()
        mutations=('\n'.join(rows[:-1])+'\n',text+rows[-1]+'\n',
            text.replace('retire,80000000','retire,80000010',1),
            text.replace(',13,0',',93,0',1),text.replace(',13,0',',13,1',1),
            text.replace('retire,80000000','allocate,80000000',1))
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'commit.csv'
            for changed in mutations:
                path.write_text(changed)
                with self.assertRaises(ValueError):check.check_entries(path,ENTRIES)

    def test_entry_arm_order_and_clock_mutations(self):
        text=commit_log()
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'commit.csv'
            for changed in (text.replace('retire,80000000','retire,80000004',1),
                            text.replace('2,retire,','0,retire,',1)):
                path.write_text(changed)
                with self.assertRaises(ValueError):check.check_entries(path,ENTRIES)

    def test_roi_one_time_setup_excluded_dynamic_cache_included(self):
        self.assertIn('dynamic cache allocation/copy/free',c.ROI_INCLUDED)
        for item in ('one-time device_query','cache object constructor','buffer initialization'):
            self.assertIn(item,c.ROI_EXCLUDED)

    def test_compiler_bare_tool_name_uses_fixed_path(self):
        name=subprocess.check_output(['/usr/bin/gcc','-print-prog-name=as'],text=True).strip()
        self.assertEqual(b.located_path(name),Path('/usr/bin/as').resolve(strict=True))
        self.assertEqual(b.located_path('/usr/bin/gcc'),Path('/usr/bin/gcc').resolve(strict=True))
        with self.assertRaises(FileNotFoundError):b.located_path('stage4_nonexistent_tool')


if __name__=='__main__': unittest.main()
