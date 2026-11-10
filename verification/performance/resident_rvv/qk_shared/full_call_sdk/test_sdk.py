import copy
import csv
import io
import json
from pathlib import Path
import struct
import tempfile
import unittest

import fixture as f
import check as c
import build as b


def log_fixture(fixture):
    lines, begin = [],100

    def emit(tag,values):
        lines.append('SDK_ATTENTION_'+tag+' '+' '.join(
            key+'='+ (format(value,'x') if key in c.HEX else str(value))
            for key,value in values.items()))

    for trial,case in enumerate(f.CASES):
        emit('CALL',dict(trial=trial,requested=case['requested'],d=case['dimension'],
            heads=case['heads'],kvheads=case['kv_heads'],tokens=case['tokens'],begin=begin,
            returned=begin+50,end=begin+60,initial_fcsr=case['initial_flags'],
            initial_vcsr=0,initial_vstart=0,fcsr=fixture['results'][trial]['expected_fcsr'],
            vcsr=0,vstart=0,groups=case['kv_heads'],errors=0))
        rows = case['heads']//case['kv_heads']
        for group in range(case['kv_heads']):
            emit('GROUP',dict(trial=trial,group=group,first_head=group*rows,rows=rows,
                q=0x80001000+group*rows*256,k=0x80010000+group*case['capacity']*256,
                v=0x80030000+group*case['capacity']*256,output=0x80050000+group*rows*512))
        emit('MEMORY',dict(trial=trial,**fixture['memory'][trial]))
        for index,bits in enumerate(fixture['results'][trial]['bits']):
            emit('OUT',dict(trial=trial,index=index,bits=bits))
        begin += 100
    emit('DATA',dict(bytes=fixture['data_bytes'],hash=fixture['data_hash']))
    emit('DONE',dict(calls=3,errors=0))
    return '\n'.join(lines)+'\n'


def perf_fixture(fixture):
    geometry = f.load(c.GEOMETRY,'sdk_test_geometry')
    lines = []
    for seq,command in enumerate(f.commands(),1):
        shape,flags = geometry.geometry(command),c.local_flags(fixture,command)
        active = [lane for lane in range(4) if shape['writes'][lane]]
        for lane in active:
            row = dict(lane=lane,vid=seq%8,tokens=command['tokens'],elements=shape['elements'][lane],
                heads=command['heads'],issued=shape['fma'][lane],returned=shape['fma'][lane],
                writes=len(shape['writes'][lane]),flags=flags if lane==active[0] else 0,error=0)
            if command['mode']=='QK': row['dimensions']=command['dimension']
            lines.append('[RESIDENT_'+command['mode']+'_LANE] '+geometry_fields(row))
        row = dict(shape['counts'],seq=seq,vid=seq%8,cycles=20,error=0,flags=flags)
        lines.append('[RESIDENT_'+command['mode']+'_PERF] '+geometry_fields(row))
    return '\n'.join(lines)+'\n'


def geometry_fields(row):
    return ' '.join(key+'='+ (format(value,'b') if key=='active' else str(value))
                    for key,value in row.items())


def vector_fixture():
    geometry = f.load(c.GEOMETRY,'sdk_test_vector_geometry')
    fields = 'cycle event arch_seq vid lane source insn use_vd vd eew vl vstart addr be wdata nr_lanes vlen_bits'.split()
    output = io.StringIO()
    writer = csv.DictWriter(output,fieldnames=fields)
    writer.writeheader()
    cycle = 0

    def emit(event,**values):
        nonlocal cycle
        row = dict.fromkeys(fields,'0')
        row.update(cycle=cycle,event=event,nr_lanes=4,vlen_bits=1024,insn='00000000')
        row.update(values)
        writer.writerow(row)
        cycle += 1

    emit('config')
    for t in (64,64,9):
        for insn in [0x0205745b]*32+[0x0205345b]*t:
            emit('alloc',insn='%08x'%insn)
    for seq,command in enumerate(f.commands(),1):
        shape = geometry.geometry(command)
        metadata = dict(arch_seq=seq,vid=seq%8,insn='%08x'%shape['opcode'],use_vd=1,
                        vd=0,eew=shape['eew'],vl=shape['vl'],vstart=0)
        emit('alloc',**metadata)
        for lane,words in enumerate(shape['writes']):
            for addr,mask in words.items():
                emit('write',**metadata,lane=lane,source=4,addr=addr,be='%02x'%mask,wdata='0123456789abcdef')
        emit('done',**metadata)
    return output.getvalue()


def legacy_fixture():
    old,expected = c.expected_akv()
    lines,totals = [],c.Counter()
    for seq,expected_row in enumerate(expected,1):
        row = dict.fromkeys(old.PERF_FIELDS,0)
        row.update(expected_row,seq=seq,success=1,busy_cycles=1,
                   context_ready=int(expected_row['command']!=3))
        row['read_payload_bytes'] = row['q_external_bytes']+row['kv_external_bytes']+64*row['v2_full']
        for key in old.SUMMARY_FIELDS-{'records','success_records','fault_records','validation_fault_records'}:
            totals[key] = max(totals[key],row[key]) if key=='read_outstanding_max' else totals[key]+row[key]
        lines.append('[AKV_PERF] '+geometry_fields(row))
    totals.update(records=247,success_records=247,fault_records=0,validation_fault_records=0)
    lines.append('[AKV_PERF_SUMMARY] '+geometry_fields(totals))
    return '\n'.join(lines)+'\n'


def entry_fixture():
    names = b'\0akv_decode_execute\0akv_experimental_attention_execute_v2_native\0'
    offsets = [1,names.index(b'akv_experimental')]
    text_offset, string_offset = 64,72
    sym_offset = (string_offset+len(names)+7)//8*8
    shoff = sym_offset+72
    raw = bytearray(shoff+4*64)
    ident = b'\x7fELF\x02\x01\x01'+bytes(9)
    struct.pack_into('<16sHHIQQQIHHHHHH',raw,0,ident,2,243,1,0x80000100,
                     0,shoff,4,64,56,0,64,4,0)
    struct.pack_into('<II',raw,text_offset,0x13,0x13)
    raw[string_offset:string_offset+len(names)] = names
    for i,offset in enumerate(offsets,1):
        struct.pack_into('<IBBHQQ',raw,sym_offset+i*24,offset,0x12,0,1,0x80000100+(i-1)*4,4)
    sections = [(0,0,0,0,0,0,0,0,0,0),
        (0,1,6,0x80000100,text_offset,8,0,0,2,0),
        (0,2,0,0,sym_offset,72,3,1,8,24),
        (0,3,0,0,string_offset,len(names),0,0,1,0)]
    for i,section in enumerate(sections):
        struct.pack_into('<IIQQQQIIQQ',raw,shoff+i*64,*section)
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['cycle','event','pc','insn','trap'])
    for cycle,pc in enumerate([0x80000100]*6+[0x80000104]*4,1):
        writer.writerow([cycle,'retire','%x'%pc,'00000013',0])
    return bytes(raw),output.getvalue()


class FixtureTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='sdk_attention_host_')
        cls.path = Path(cls.temp.name)
        cls.fixture,cls.pins = f.generate(cls.path)
        cls.log = log_fixture(cls.fixture)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_original_golden_identity(self):
        self.assertEqual(f.sha(self.path/'golden_0.bin'),f.NATIVE_SHA)
        self.assertEqual((self.path/'golden_0.bin').read_bytes(),(self.path/'golden_1.bin').read_bytes())

    def test_derived_new_golden_shape_and_flags(self):
        self.assertEqual((self.path/'golden_2.bin').stat().st_size,576*4)
        self.assertNotEqual(f.sha(self.path/'golden_2.bin'),f.NATIVE_SHA)
        self.assertEqual([r['natural_flags'] for r in self.fixture['results']],[3,3,3])
        self.assertEqual([r['expected_fcsr'] for r in self.fixture['results']],[3,11,3])
        self.assertEqual(self.fixture['results'][2]['reduction_order_checks'],12)

    def test_derived_view_and_active_dimensions(self):
        source,_ = f.inputs()
        q = f.unpack(source[0]['query'],32)
        derived = f.unpack(source[2]['query'],32)
        for h in range(6):
            self.assertEqual(derived[h*128:(h+1)*128],
                             [q[(h%2)*128+(d+7*h)%128] for d in range(128)])
        self.assertEqual(source[2]['key'][65*256:],source[0]['key'][64*256:129*256])
        self.assertEqual(source[2]['value'][65*256:],source[0]['value'][64*256:129*256])
        self.assertNotEqual(source[2]['key'][:65*256],source[2]['key'][65*256:])

    def test_raw_numerical_success(self):
        self.assertEqual(c.numerical(self.log,self.fixture)['output_values'],1088)

    def test_numerical_mutations(self):
        mutations = [self.log.replace('initial_fcsr=8','initial_fcsr=0',1),
            self.log.replace('fcsr=11','fcsr=3',1),self.log.replace('fcsr=11','fcsr=9',1),
            self.log.replace('first_head=3','first_head=0',1),
            self.log.replace('guard_bytes=', 'bad_bytes=',1),
            self.log+self.log.splitlines()[-1]+'\n']
        target = next(line for line in self.log.splitlines() if line.startswith('SDK_ATTENTION_OUT'))
        mutations += [self.log.replace(target,target[:-1]+('0' if target[-1]!='0' else '1'),1),
                      self.log.replace(target+'\n','',1)]
        for text in mutations:
            with self.subTest(text=text[:20]),self.assertRaises(ValueError):
                c.numerical(text,self.fixture)

    def test_group_offsets_reject_double_offset(self):
        line = next(line for line in self.log.splitlines() if 'GROUP trial=2 group=1' in line)
        fields = dict(x.split('=') for x in line.split()[1:])
        altered = line.replace('output='+fields['output'],'output=%x'%(int(fields['output'],16)+1536))
        with self.assertRaises(ValueError):
            c.numerical(self.log.replace(line,altered),self.fixture)

    def test_command_local_flags_and_geometry(self):
        text = perf_fixture(self.fixture)
        self.assertEqual(len(c.resident_performance(text,self.fixture)),22)
        line = next(line for line in text.splitlines() if '_PERF]' in line and 'flags=0' not in line)
        with self.assertRaises(ValueError):
            c.resident_performance(text.replace(line,rewrite_flag(line),1),self.fixture)

    def test_pairs_all_qk_then_pv_and_local_base(self):
        commands = f.commands()
        self.assertEqual(len(commands),22)
        for group in (0,1):
            for tile in (0,64):
                sub = [r for r in commands if r['trial']==2 and r['group']==group and r['tile']==tile]
                self.assertEqual([(r['mode'],r['base'],r['heads']) for r in sub],
                                 [('QK',0,2),('QK',2,1),('PV',0,2),('PV',2,1)])

    def test_vector_work_and_mutations(self):
        path = self.path/'vector.csv'
        text = vector_fixture()
        path.write_text(text)
        self.assertEqual(len(c.vector_work(path)),22)
        for altered in (text.replace('0485705b','0605705b',1),
                        text.replace(',ff,0123456789abcdef',',0f,0123456789abcdef',1),
                        text+'\n'.join(text.splitlines()[-2:])+'\n'):
            path.write_text(altered)
            with self.assertRaises(ValueError):
                c.vector_work(path)

    def test_lifetime_work_and_mutations(self):
        text = legacy_fixture()
        self.assertEqual(c.legacy_work(text)['per_call'],[237,4,6])
        for altered in (text.replace('success=1','success=0',1),
                        text.replace('command=4','command=5',1),
                        text.replace('records=247','records=246',1)):
            with self.assertRaises(ValueError):
                c.legacy_work(altered)

    def test_memory_formula_and_header(self):
        header = (self.path/'fixture.h').read_text()
        self.assertIn('UINT64_C(0xb)',header)
        self.assertEqual(self.fixture['memory'][2]['guard_bytes'],
            512+(768-576)*6+3*(256-96)*2+5*780+32)
        for case,memory in zip(f.CASES,self.fixture['memory']):
            self.assertEqual(memory['guard_hash'],f.fnv(b'\xa5'*f.guard_bytes(case)))

    def test_same_entry_and_no_csr_clear_inside(self):
        source = (b.HERE/'main.c').read_text()
        self.assertEqual(source.count('akv_experimental_attention_execute_v2_native('),1)
        self.assertNotIn('akv_attention_execute_v2_native_auto(',source)
        self.assertNotIn('--wrap',source)
        full_call = source[source.index('static __attribute__((noinline))'):source.index('int main(void)')]
        self.assertNotIn('csrw',full_call)
        self.assertNotIn('csrwi',full_call)
        self.assertIn('.requested=c->requested',full_call)
        self.assertIn('first_head != ctx->visited*rows',source)
        self.assertNotIn('if (batch || first_head)',source)

    def test_build_overlay_whitelist(self):
        self.assertEqual(set(b.OVERLAYS),{'software/akv/src/akv_v2_native_riscv.c',
            'software/akv/experimental/resident_attention/executor.h'})
        for relative,digest in b.OVERLAYS.items():
            self.assertEqual(f.sha(b.FROZEN/relative),digest)
        self.assertNotIn('test_executor.py',' '.join(b.OWN))
        self.assertEqual(b.SDK_COMMIT,'8dc915db8689d801af991676c25b75093bec9a4b')

    def test_actual_elf_entry_counts(self):
        elf,trace = entry_fixture()
        (self.path/'entry.elf').write_bytes(elf)
        (self.path/'commit.csv').write_text(trace)
        self.assertEqual(c.actual_entry(self.path/'commit.csv',self.path/'entry.elf'),
            dict(akv_decode_execute=6,akv_experimental_attention_execute_v2_native=4))

    def test_actual_entry_rejects_missing_extra_wrong_insn(self):
        elf,trace = entry_fixture()
        (self.path/'entry.elf').write_bytes(elf)
        for altered in (trace.replace('80000104','80000108',1),
                        trace.replace('00000013','00000017',1),
                        trace+'11,retire,80000104,00000013,0\r\n'):
            (self.path/'commit.csv').write_text(altered)
            with self.assertRaises(ValueError):
                c.actual_entry(self.path/'commit.csv',self.path/'entry.elf')


def rewrite_flag(line):
    key = line.rsplit('flags=',1)
    return key[0]+'flags='+str(int(key[1])^1)


if __name__ == '__main__':
    unittest.main()
