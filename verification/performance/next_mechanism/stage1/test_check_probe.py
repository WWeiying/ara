import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest

from check_probe import check,node_phase


def node(active=True, phase_id=0):
    members=[]
    for i,name in enumerate(('MUL_MAT','ADD')):
        members.append(dict(graph=1,epoch=7,nodes=2,first=0,last=1,member=i,
                            op=i,op_name=name,type='f32',name=name,ne=[2,1,1,1],
                            elapsed_ns=400 if active and i==0 else None))
    return dict(schema='stage1-node-ns-v1',valid=True,errors=0,active=active,
                phase_id=phase_id,phase='prefill' if phase_id==0 else 'decode',
                clock='CLOCK_MONOTONIC',semantics='software_node_elapsed_ns_no_added_sync',
                records=members,members=2,units=1,graphs=1,
                unit_ns=400 if active else None,phase_ns=1000 if active else None,
                unattributed_ns=600 if active else None)


class ProbeCheckTest(unittest.TestCase):
    def test_fused_time_counted_once(self):
        path,categories=node_phase(node(),0,True)
        self.assertEqual(len(path),2)
        self.assertEqual(categories,{'MUL_MAT+ADD':400})
        self.assertEqual(node_phase(node(False),0,False)[0],path)

    def test_invalid_records_rejected(self):
        good=node()
        variants=[]
        for key,value in [('valid',False),('errors',4),('phase_ns',999),('units',2)]:
            r=copy.deepcopy(good);r[key]=value;variants.append(r)
        r=copy.deepcopy(good);r['records'][1]['elapsed_ns']=100;variants.append(r)
        r=copy.deepcopy(good);r['records'][1]['member']=0;variants.append(r)
        r=copy.deepcopy(good);r['records'].pop();r['members']=1;variants.append(r)
        for r in variants:
            with self.subTest(report=r),self.assertRaises(ValueError):
                node_phase(r,0,True)

    def make_trial(self, directory, mode):
        directory.mkdir()
        inputs=dict(prompt_tokens=[10],fixed_history_tokens=[1],vocabulary=2)
        phases=[dict(phase='prefill',eval_tokens=1,compute_ns=1000,paths={'qk':1}),
                dict(phase='decode',step=0,compute_ns=1000,paths={'qk':1})]
        metrics=dict(kind='fixed_history_replay_not_free_generation',arm='qbs_akv',
                     worker_count=1,kv='f16/f16',single_token_evaluations=1,prompt_tokens=1,
                     phases=phases,prefill_compute_ns=1000,decode_compute_ns=1000,
                     inference_window_ns=5000,model_load_ns=100,context_init_ns=100,
                     logits_records=2,vocabulary=2,greedy_tokens_including_final_prediction=[1,1])
        if mode!='plain':
            metrics.update(node_metadata_capture=True,node_timing_active=mode=='timed',
                           inference_window_includes_probe_export=True)
            for i in range(2):
                (directory/f'nodes_{i}.jsonl').write_text(json.dumps(node(mode=='timed',i)))
        (directory/'inputs.json').write_text(json.dumps(inputs))
        (directory/'metrics.json').write_text(json.dumps(metrics))
        (directory/'exit_code').write_text('0\n')
        (directory/'stdout.log').write_text('STAGE1_PROGRESS prefill tokens=1 ns=1000\n'
            'STAGE1_PROGRESS decode=1/1 ns=1000\nSTAGE1_MODEL_COMPLETED\n')
        with (directory/'logits.bin').open('wb') as f:
            for i in range(2):
                f.write(struct.pack('<6I',0x5142534c,2,i,2,1 if i==0 else 0xffffffff,0))
                f.write(struct.pack('<2f',.25,.5))

    def test_full_data_check_is_not_board_acceptance(self):
        with tempfile.TemporaryDirectory() as temp:
            dirs=[Path(temp)/str(i) for i in range(4)]
            for d,m in zip(dirs,('plain','metadata','timed','plain')):
                self.make_trial(d,m)
            result=check(dirs)
            self.assertTrue(result['perturbation_within_target'])
            self.assertFalse(result['measurement_accepted'])
            self.assertTrue(result['open_gates'])
            with (dirs[1]/'logits.bin').open('ab') as f:
                f.write(b'wrong extra data')
            with self.assertRaisesRegex(ValueError,'Trailing logits'):
                check(dirs)


if __name__=='__main__':
    unittest.main()
