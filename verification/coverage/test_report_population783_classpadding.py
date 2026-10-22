import copy
import json
import unittest
import report_population783_classpadding as p


class Union(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=p.life.read_bound(p.LOCAL/'config.json',p.LOCAL_CONFIG_SHA)
        cls.addition=(p.LOCAL/'second.el').read_text()
        cls.base=(p.REPORT/'combined.el').read_text()

    def field(self,name='other',checks=None):
        i=self.c['instances'][0]
        checks=checks or (i['design_module_checksum']+' '+i['toggle_checksum'])
        return 'CHECKSUM: "%s"\nINSTANCE: %s\nToggle %s "logic %s[0:0]"\n'%(checks,i['scope'],name,name)

    def test_actual_sealed_native_union_and_non_toggle_preservation(self):
        result=p.union_gate(self.base,self.addition,self.c)
        old,new=p.stable.semantic(self.base),p.stable.semantic(result)
        self.assertEqual(old[0],new[0])
        a,b=p.engine.physical(old),p.engine.physical(new)
        self.assertTrue(all(b[k]&v==v for k,v in a.items()))
        self.assertEqual(sum(bin(v).count('1') for v in b.values())-sum(bin(v).count('1') for v in a.values()),5316)

    def test_duplicate_existing_direction_rejected(self):
        with self.assertRaises(ValueError):p.union_gate(self.addition,self.addition,self.c)

    def test_duplicate_native_line_rejected_before_set_normalization(self):
        line=next(x for x in self.addition.splitlines() if x.startswith('Toggle '))
        i=self.c['instances'][0]
        text=self.addition+'CHECKSUM: "%s %s"\nINSTANCE: %s\n%s\n'%(i['design_module_checksum'],i['toggle_checksum'],i['scope'],line)
        with self.assertRaises(ValueError):p.union_gate('',text,self.c)

    def test_low10_boundary_not_excluded(self):
        with self.assertRaises(ValueError):p.union_gate('',self.addition.replace('[10]','[9]',1),self.c)

    def test_missing_direction_rejected(self):
        lines=self.addition.splitlines();index=next(i for i,l in enumerate(lines) if l.startswith('Toggle '));del lines[index]
        with self.assertRaises(ValueError):p.union_gate('','\n'.join(lines)+'\n',self.c)

    def test_whole_ancestor_rejected(self):
        scope=self.c['instances'][0]['scope']
        base='CHECKSUM: "1 2"\nINSTANCE: '+scope.rsplit('.',1)[0]+'\n'
        with self.assertRaises(ValueError):p.union_gate(base,self.addition,self.c)

    def test_opaque_toggle_ancestor_rejected(self):
        scope=self.c['instances'][0]['scope']
        base='CHECKSUM: "1 2"\nINSTANCE: '+scope.rsplit('.',1)[0]+'\nToggle unknown\n'
        with self.assertRaises(ValueError):p.union_gate(base,self.addition,self.c)

    def test_strict_fsm_ancestor_retained(self):
        scope=self.c['instances'][0]['scope'].rsplit('.',1)[0]
        base='CHECKSUM: "1 2"\nINSTANCE: '+scope+'\nFsm state_q "2"\nTransition A->B "0->1"\n'
        result=p.union_gate(base,self.addition,self.c)
        self.assertEqual(p.stable.semantic(base)[0],p.stable.semantic(result)[0])
        with self.assertRaises(ValueError):p.union_gate(base.replace('Fsm state_q "2"','Fsm state_q "3"'),self.addition,self.c)

    def test_same_scope_checksum_collision(self):
        with self.assertRaises(ValueError):p.union_gate(self.field(checks='1 2'),self.addition,self.c)

    def test_packed_parent_child_collision(self):
        name=self.c['instances'][0]['signals'][0]['name']+'.child'
        with self.assertRaises(ValueError):p.union_gate(self.field(name),self.addition,self.c)

    def test_receipt_scope_boundaries(self):
        q=p.life.read_bound(p.LOCAL/'capture-result.json',p.LOCAL_QUAL_SHA);p.local_gate(q,self.c)
        for k,v in [('directions',5314),('population_application',True),('raw_serialized_mapping_calibrated',True),
                    ('full_native_typed_complements',False),('official_percentage',80)]:
            bad=dict(q);bad[k]=v
            with self.assertRaises(ValueError):p.local_gate(bad,self.c)

    def test_real_predecessor_config_qualification_and_files(self):
        source,pins,text=p.inherited(p.stable.Reader())
        self.assertEqual(source['population'],783);self.assertEqual(text,self.base)
        self.assertEqual(pins[str(p.REPORT/'qualification.json')],p.REPORT_QUAL_SHA)

    def test_predecessor_semantic_or_population_drift_rejected(self):
        q=p.life.read_bound(p.REPORT/'qualification.json',p.REPORT_QUAL_SHA)
        c=p.life.read_bound(p.REPORT/'config.json',p.REPORT_CONFIG_SHA)
        p.report_gate(q,c)
        for key,value in [('population',782),('raw_reset_final_equal',False),('config_seal','0'*64)]:
            bad=dict(q);bad[key]=value
            with self.assertRaises(ValueError):p.report_gate(bad,c)

    def test_private_unchanged_five_stage_engine(self):
        self.assertIs(p.prepare.__code__,p.engine.prepare.__code__)
        self.assertIs(p.check.__code__,p.engine.check.__code__)
        self.assertIs(p.verify.__code__,p.engine.verify.__code__)
        self.assertIs(p.run.__code__,p.engine.run.__code__)
        self.assertEqual(p.metadata()['additional_direction_count'],23536)
        self.assertEqual(p.metadata()['local_qualifications'][-1]['directions'],5316)


if __name__=='__main__':unittest.main()
