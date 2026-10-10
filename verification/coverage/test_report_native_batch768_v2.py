import copy
import json
import tempfile
from pathlib import Path
import unittest
import report_native_batch768_v2 as r

DIRECTORIES=dict(tlb726='tlb-rvh0-726-native-agent-20261007-02',
                 accum66='qbs-accum66-native-agent-20261007-01',fixed120='cva6-fixed120-native768-agent-20261007-01')


class SuccessorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Immutable source-prepared configs/candidates only; no active GUI output read.
        cls.configs={key:json.loads((r.life.OUT/name/'config.json').read_bytes()) for key,name in DIRECTORIES.items()}
        cls.texts={key:(r.life.OUT/name/'candidate.el').read_text() for key,name in DIRECTORIES.items()}
        cls.values={key:r.parse(key,cls.texts[key],c) for key,c in cls.configs.items()}

    def test_actual_prepared_exact_parsers_without_qualification_claim(self):
        self.assertEqual({k:len(v) for k,v in self.values.items()},dict(tlb726=8448,accum66=4224,fixed120=4396))

    def test_changed_annotation_rejected(self):
        for key,c in self.configs.items():
            text=self.texts[key].replace('ANNOTATION: "','ANNOTATION: "FOREIGN ',1)
            with self.subTest(key=key),self.assertRaises(ValueError):r.parse(key,text,c)

    def test_wrong_checksum_extra_field_and_missing_direction_rejected(self):
        for key,c in self.configs.items():
            text=self.texts[key]
            for bad in (text.replace('CHECKSUM: "','CHECKSUM: "0',1),text+'Toggle foreign "logic foreign"\n',
                        '\n'.join(line for n,line in enumerate(text.splitlines()) if n!=next(
                            n for n,line in enumerate(text.splitlines()) if line.startswith('Toggle')))+'\n'):
                with self.subTest(key=key),self.assertRaises(ValueError):r.parse(key,bad,c)

    def test_partial_fixed_result_cannot_expand_to_low_architectural_bits(self):
        c=self.configs['fixed120'];text=self.texts['fixed120']
        low=next(s for i in c['instances'] for s in i['signals'] if len(s['bits'])<s['left']-s['right']+1)
        scope=next(i['scope'] for i in c['instances'] if low in i['signals'])
        # Add precisely a retained bit; all otherwise legitimate native records remain.
        lines=['CHECKSUM: "'+i['design_module_checksum']+' '+i['toggle_checksum']+'"' for i in c['instances'] if i['scope']==scope]
        lines+=['INSTANCE: '+scope,'ANNOTATION: "'+r.FIXED_ANNOTATION+'"',
                'Toggle '+low['name']+' [0] "logic '+low['native_label']+'"']
        with self.assertRaises(ValueError):r.parse('fixed120',text+'\n'+'\n'.join(lines)+'\n',c)

    def test_shared_partition_retains_complete766_and_all_static_new_sets(self):
        c=json.loads((r.life.OUT/'native-batch-full768-prepared-agent-20261007-01/config.json').read_bytes())
        original=(Path(c['output'])/'combined.el').read_text()
        for key,cfg in self.configs.items():
            names={i['scope']:sorted(s.get('signal',s.get('name')) for s in i.get('targets',i.get('signals',[])))
                   for i in cfg['instances']}
            c['new_families'][key]=dict(config=cfg,signals=names)
        ns=r.private_namespace();text=original+''.join(self.texts.values())
        union=ns['records'](text,c)
        for key,value in self.values.items():self.assertEqual(union.pop(key),value)
        self.assertEqual(union,json.loads((Path(c['output'])/'config.json').read_bytes())['expected_union'])
        # Real serialized objects use bracketed indices; source-prepared only, not native PASS.
        self.assertIn('content_q[0].gpte',self.texts['tlb726'])

    def test_missing_or_source_only_qualification_cannot_prepare_or_run(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'never-created'
            with self.assertRaises(ValueError):r.prepare(out,{})
            self.assertFalse(out.exists())
            p=Path(tmp)/'qualification.json';p.write_text(json.dumps(dict(status='SOURCE_CANDIDATE',population_application=False)))
            with self.assertRaises(ValueError):r.replay_qualified('tlb726',p,r.life.digest(p))
            self.assertFalse(out.exists())

    def test_registry_and_full_verifier_are_closed(self):
        self.assertEqual(set(r.REGISTRY),{'tlb726','accum66','fixed120'})
        with self.assertRaises(ValueError):r.parse('unknown','',{})
        ns=r.namespace();self.assertIn('audit_six',ns['verify'].__code__.co_names)
        self.assertIn('audit_observers',ns['verify'].__code__.co_names)
        self.assertNotEqual(r.TCL,r.frozen.TCL)


if __name__=='__main__':unittest.main()
