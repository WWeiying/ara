import unittest
from unittest.mock import patch
import report_population784_rr190 as p


class Union(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=p.life.read_bound(p.LOCAL/'config.json',p.LOCAL_SHA)
        cls.extra=(p.LOCAL/'second.el').read_text()
        cls.base=(p.REPORT/'combined.el').read_text()

    def test_actual_native_union_preserves_all_old_metrics(self):
        text=p.union_gate(self.base,self.extra,self.c)
        old,new=p.stable.semantic(self.base),p.stable.semantic(text)
        self.assertEqual(old[0],new[0])
        oldmask,newmask=p.engine.physical(old),p.engine.physical(new)
        self.assertTrue(all(newmask[k]&v==v for k,v in oldmask.items()))
        self.assertEqual(sum(bin(v).count('1') for v in newmask.values())-
                         sum(bin(v).count('1') for v in oldmask.values()),22528)

    def test_overlap_rejected(self):
        with self.assertRaises(ValueError):p.union_gate(self.extra,self.extra,self.c)

    def test_missing_direction_rejected(self):
        lines=self.extra.splitlines();del lines[next(i for i,l in enumerate(lines) if l.startswith('Toggle '))]
        with self.assertRaises(ValueError):p.union_gate('', '\n'.join(lines)+'\n',self.c)

    def test_duplicate_native_rejected(self):
        with self.assertRaises(ValueError):p.union_gate('',self.extra+self.extra,self.c)

    def base_field(self,name,checks=None):
        i=self.c['instances'][0]
        return 'CHECKSUM: "%s"\nINSTANCE: %s\nToggle %s "logic %s[0:0]"\n'%(
            checks or i['design_module_checksum']+' '+i['toggle_checksum'],i['scope'],name,name)

    def test_checksum_conflict_rejected(self):
        with self.assertRaises(ValueError):p.union_gate(self.base_field('other','1 2'),self.extra,self.c)

    def test_packed_parent_rejected(self):
        name=self.c['instances'][0]['signals'][0]['name'].rsplit('.',1)[0]
        with self.assertRaises(ValueError):p.union_gate(self.base_field(name),self.extra,self.c)

    def test_opaque_ancestor_rejected_but_proved_fsm_preserved(self):
        scope=self.c['instances'][0]['scope'].rsplit('.',1)[0]
        header='CHECKSUM: "1 2"\nINSTANCE: '+scope+'\n'
        with self.assertRaises(ValueError):p.union_gate(header,self.extra,self.c)
        base=header+'Fsm state_q "2"\nTransition A->B "0->1"\n'
        self.assertEqual(p.stable.semantic(p.union_gate(base,self.extra,self.c))[0],p.stable.semantic(base)[0])
        with self.assertRaises(ValueError):p.union_gate(base.replace('Fsm state_q "2"','Fsm state_q "3"'),self.extra,self.c)

    def test_actual_parent_report_authority(self):
        c,_,text=p.inherited(p.stable.Reader())
        self.assertEqual(c['population'],783)
        self.assertEqual(text,self.base)
        self.assertEqual(p.metadata()['additional_direction_count'],46064)

    def test_actual_rr_coordinates_and_bounded_zero_gate(self):
        q=p.life.read_bound(p.native.SOURCE,p.native.SOURCE_SHA)
        groups=p.target_groups(q,self.c,'missing_coordinates')
        self.assertEqual(len(groups),30)
        self.assertEqual(sum(len(g['positions']) for g in groups.values()),22528)
        for g in groups.values():
            row=dict(width=g['width'],checksum=g['checksum'],bits='0')
            p.population.zero_row(row,g['width'],g['checksum'],g['positions'])
            pos=g['positions'][0]
            row['bits']=hex(1<<(g['width']-1-pos))
            with self.assertRaises(ValueError):p.population.zero_row(row,g['width'],g['checksum'],g['positions'])
            row.update(bits='0',checksum='0')
            with self.assertRaises(ValueError):p.population.zero_row(row,g['width'],g['checksum'],g['positions'])

    def test_duplicate_source_coordinate_rejected(self):
        q=p.life.read_bound(p.native.SOURCE,p.native.SOURCE_SHA)
        q=dict(q,candidates=[*q['candidates'],q['candidates'][0]])
        with self.assertRaises(ValueError):p.target_groups(q,self.c,'missing_coordinates')

    def test_no_783_prepare_or_fork(self):
        c=p.life.read_bound(p.REPORT/'config.json',p.REPORT_SHA)
        fake=(dict(input_ledger=c['input_ledger']),{},'',dict(tests=list(range(783))),[],{})
        with patch.object(p.population,'approved',return_value=fake),patch.object(p,'inherited',return_value=(c,{},'')):
            with self.assertRaises(ValueError):p.approved(None,p.previous.BASE,p.previous.BASE_SHA)

    def test_unchanged_engine_and_no_launch_in_context(self):
        funcs=p.context(p.previous.BASE,'0'*64)
        for fn,name in zip(funcs,('prepare','check','verify','run')):
            self.assertIs(fn.__code__,getattr(p.engine,name).__code__)


class Formal785(unittest.TestCase):
    def fixture(self):
        ledger=['design']+['test%d'%i for i in range(785)]
        chain=[dict(population=783,manifest=str(p.previous.BASE),seal=p.previous.BASE_SHA),
               dict(population=784,manifest=str(p.FORMAL784),seal=p.FORMAL784_SHA),
               dict(population=785,manifest='/synthetic/785/admission-manifest.json',seal='5'*64)]
        return dict(input_ledger=ledger),dict(tests=list(range(785))),chain,dict(input_ledger=ledger[:784])

    def test_exact785_prefix_and_two_suffixes(self):
        source,bits,chain,old=self.fixture()
        p.population_gate(source,bits,chain,old)
        self.assertEqual([r['population'] for r in p.suffix_chain(chain)],[784,785])
        self.assertEqual(p.metadata()['additional_direction_count'],46064)

    def test_intermediate784_and_missing_or_duplicate_suffix_rejected(self):
        source,bits,chain,old=self.fixture()
        with self.assertRaises(ValueError):
            p.population_gate(dict(input_ledger=source['input_ledger'][:-1]),
                              dict(tests=bits['tests'][:-1]),chain[:-1],old)
        for bad in (chain[:-1],chain[:1]+chain[2:],chain+[chain[-1]],chain[:1]+list(reversed(chain[1:]))):
            with self.assertRaises(ValueError):p.suffix_chain(bad)

    def test_source_zero_checks_all_families_and_exact_scopes(self):
        families=[(f,{f:dict(width=8,checksum='17',positions=[2,3])})
                  for f in ('RR190','CLASS_PADDING','FPNEW90')]
        rows={f:dict(width=8,checksum='17',bits='0') for f,_ in families}
        p.suffix_rows(rows,families)
        for f,_ in families:
            bad={k:dict(v) for k,v in rows.items()};bad[f]['bits']='20'
            with self.assertRaises(ValueError):p.suffix_rows(bad,families)
        with self.assertRaises(ValueError):p.suffix_rows(dict(rows,foreign=rows['RR190']),families)

    def test_prefix_or_ancestor_change_rejected(self):
        source,bits,chain,old=self.fixture()
        source['input_ledger'][42]='foreign'
        with self.assertRaises(ValueError):p.population_gate(source,bits,chain,old)
        source,bits,chain,old=self.fixture();chain[0]['seal']='0'*64
        with self.assertRaises(ValueError):p.population_gate(source,bits,chain,old)

    def test_formal784_path_and_seal_cannot_be_replaced(self):
        for key,value in (('manifest','/synthetic/other784/admission-manifest.json'),('seal','0'*64)):
            source,bits,chain,old=self.fixture();chain[1][key]=value
            with self.assertRaises(ValueError):p.population_gate(source,bits,chain,old)


if __name__=='__main__':unittest.main()
