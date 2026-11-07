#!/usr/bin/env python3
"""Host-only admission and mandatory raw-replay negatives; never executes a target."""
from copy import deepcopy
import json
import unittest

import collect_rms_output as c
import check_rms_output as checker
from check_projection_native import checksum


def numerical_fixture():
    p,d=bytes(32768),bytes(8192)
    lines=[checker.original.SCOPE]
    for rows,golden in ((1,d),(4,p)):
        for trial,candidate in enumerate((0,1,1,0)):
            lines.append(f'RMS_NORM_TRIAL rows={rows} trial={trial} candidate={candidate} cycles={200 if candidate else 100} '
                         f'fcsr=9 vcsr=5 vstart=0 checksum={checksum(golden)} errors=0')
    lines.append('RMS_NORM_RESULT trials=8 outputs_checked=40960 boundary_cases=53 sum_cases=10 errors=0')
    text='\n'.join(lines)
    summary='RMS_OUTPUT_CHECK cases=155 vector_calls=110 empty_calls=5 scalar_fallbacks=40 errors=0 digest=12345\n'
    rtl=summary+text;isa=rtl+'\nSPIKE_SOC_EXIT status=0 uart_bytes=1234\n'
    insn=(0b110011<<26)|(1<<25)|(1<<12)|0x57
    trace='cycle,event,arch_seq,insn,vl,vstart,nr_lanes,vlen_bits\n0,config,0,00000000,0,0,4,1024\n'
    trace+=''.join(f'{i},alloc,{i},{insn:08x},128,0,4,1024\n' for i in range(288))
    trace+=''.join(f'{i+1000},alloc,{i+1000},02006027,128,0,4,1024\n' for i in range(458))
    worker=dict(measured=checker.check(rtl,p,d),isa_signature=checker.signature(checker.check(isa,p,d)),activity=checker.activity(trace))
    return rtl,isa,trace,p,d,worker


class CollectionTests(unittest.TestCase):
    def test_actual_worker_admission_negative(self):
        original=c.read(c.WORKER/'result.json');c.admit_worker(original)
        for key,value in [('state','FAIL'),('post_pins_match',False),('performance_measured',False),
                          ('independent_protocol_checked',False),('whole_model',True),('child_pid',123),
                          ('elf_sha256','0'*64),('source_pins_sha256','0'*64)]:
            record=deepcopy(original);record[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):c.admit_worker(record)

    def test_build_admission_negative(self):
        original=c.read(c.BUILD/'build.json');c.admit_build(original)
        for key,value in [('order',[0,1,0,1]),('output_boundary_cases',154),('boundary_cases',52),
                          ('sum_cases',9),('recompiled_objects',3),('reused_objects',13),
                          ('baseline_arithmetic_unchanged',False),('timing_includes_csr_completion',False)]:
            record=deepcopy(original);record[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):c.admit_build(record)

    def test_raw_numerical_activity_replay_mandatory(self):
        args=numerical_fixture();result=c.numerical_replay(*args)
        self.assertEqual(result[0],args[-1]['measured'])
        for i,value in [(0,args[0].replace('errors=0','errors=1',1)),
                        (1,args[1].replace('SPIKE_SOC_EXIT status=0','SPIKE_SOC_EXIT status=1')),
                        (1,args[1].split('SPIKE_SOC_EXIT')[0]),
                        (2,args[2].rsplit('\n',2)[0]+'\n'),(3,args[3][:-4])]:
            changed=list(args);changed[i]=value
            with self.subTest(index=i),self.assertRaises(ValueError):c.numerical_replay(*changed)
        changed=list(args);changed[-1]=deepcopy(args[-1]);changed[-1]['measured']['cases'][0]['call_speedup']+=1
        with self.assertRaises(ValueError):c.numerical_replay(*changed)

    def test_recorded_signature_cannot_replace_replay(self):
        args=list(numerical_fixture());args[-1]=deepcopy(args[-1])
        args[-1]['isa_signature']['output_checks']['digest']+=1
        with self.assertRaises(ValueError):c.numerical_replay(*args)

    def test_full_protocol_agreement_mandatory(self):
        worker=c.read(c.WORKER/'result.json');record=c.read(c.WORKER/'work/uvm_result.json')
        c.protocol_agreement(record,record,worker)
        for key,value in [('status','FAIL'),('elf_sha256','0'*64),('issues',['injected']),
                          ('contract_event_count',0),('sim_image_sha256',{})]:
            changed=deepcopy(record);changed[key]=value
            with self.subTest(key=key),self.assertRaises(ValueError):c.protocol_agreement(changed,record,worker)

    def test_original_commands_and_replacement(self):
        worker=c.read(c.WORKER/'result.json');commands=c.read(c.WORKER/'commands.json')
        c.commands_agreement(commands,worker)
        for i in range(3):
            changed=deepcopy(commands);changed[i]['returncode']=1
            with self.assertRaises(ValueError):c.commands_agreement(changed,worker)
        changed=deepcopy(commands);changed[2]['argv'].remove('--require-axi-write')
        with self.assertRaises(ValueError):c.commands_agreement(changed,worker)
        self.assertEqual(c.replace_object(['a.o','b.o'],'a.o','c.o'),['c.o','b.o'])
        for link in (['b.o'],['a.o','a.o']):
            with self.assertRaises(ValueError):c.replace_object(link,'a.o','c.o')


if __name__=='__main__':unittest.main()
