import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch
import admit_btb_ring as a


def ledger(count=778):
    return ['/fixed/design.vdb']+['/historical/%d/code.vdb'%i for i in range(count)]


def row(bits='0x0',width=8992,checksum='1574888635'):
    return dict(bits=bits,width=width,checksum=checksum)


class Prefix(unittest.TestCase):
    def test_explicit_latest778_and_original777(self):
        ld=ledger();a.prefix(dict(tests=ld[1:]),ld,ld[:778],779)

    def test_allow_explicit777_for778_not_false779(self):
        ld=ledger(777);a.prefix(dict(tests=ld[1:]),ld,ld,778)
        with self.assertRaises(ValueError):a.prefix(dict(tests=ld[1:]),ld,ld,779)

    def test_reject_reordered_changed_prefix_duplicate(self):
        ld=ledger()
        for bad in ([ld[0],ld[2],ld[1],*ld[3:]],ld[:20]+['/foreign/code.vdb']+ld[21:],ld[:-1]+[ld[1]]):
            with self.assertRaises(ValueError):a.prefix(dict(tests=bad[1:]),bad,ld[:778],779)

    def test_candidate_already_member_population_type(self):
        ld=ledger();ld[-1]=str(a.RUN/'code.vdb')
        with self.assertRaises(ValueError):a.prefix(dict(tests=ld[1:]),ld,ld[:778],779)
        ld=ledger()
        for n in (True,778,780):
            with self.assertRaises(ValueError):a.prefix(dict(tests=ld[1:]),ld,ld[:778],n)


class Gain(unittest.TestCase):
    def test_latest_suffix_overlap_not_recounted(self):
        s=a.core.BTB
        result=a.rebase(row(),[{s:row('0x3')}],{s:row('0x7')},778)
        self.assertEqual(result['new_positions'],1);self.assertEqual(result['new_serialized_positions'],[8989])
        self.assertTrue(result['historical777_gain_not_recounted'])

    def test_zero_latest_gain_reject(self):
        s=a.core.BTB
        with self.assertRaisesRegex(ValueError,'No fresh'):a.rebase(row(),[{s:row('0x7')}],{s:row('0x7')},778)

    def test_suffix_count_shape_checksum_reject(self):
        s=a.core.BTB
        for samples in ([],[{s:row('0x1',8991)}],[{s:row('0x1',checksum='0')}]):
            with self.assertRaises(ValueError):a.rebase(row(),samples,{s:row('0x7')},778)

    def test_actual777_gain6156_scope_and_target5960(self):
        q=json.loads((a.QUAL/'toggle-gain.json').read_bytes())
        result=a.rebase(q['before'],[],{a.core.BTB:q['single']},777)
        self.assertEqual(result['new_positions'],6156)
        prediction=json.loads((a.life.OUT/'btb-target-ring-preflight777-agent-20261007-03/prediction.json').read_bytes())
        positions={p for obj in prediction['objects'] for p in obj['missing_positions']}
        self.assertEqual(len(set(result['new_serialized_positions'])&positions),5960)


class Native(unittest.TestCase):
    def values(self):
        folder=a.RUN/'code.vdb/snps/coverage/db/testdata'/a.core.runner.CASE
        def xml(name):return a.ET.fromstring(a.gzip.decompress((folder/name).read_bytes()))
        record=a.life.read_bound(a.RUN.with_name(a.RUN.name+'.prepared.json'),a.PREPARED_SHA)
        design=str(a.life.OUT/'repaired-aligned-build-20260930-01/sim/simv.vdb')
        return xml('siminfo.xml'),xml('vcmArguments.xml'),record['command'],design

    def test_actual_siminfo_unknown_full_command_and_seed1(self):
        self.assertEqual(a.native_identity(*self.values())['XML_teststatus'],'unknown')

    def test_foreign_workdir_seed_cmd_status_time(self):
        for k,v in (('workdir','/foreign'),('seed','0'),('cmdline','/bin/true'),('teststatus','pass'),('starttime','0')):
            values=self.values();values[0].find('srctest').set(k,v)
            with self.assertRaises(ValueError):a.native_identity(*values)

    def test_native_missing_metric_foreign_compilation(self):
        for mode in ('metric','design'):
            sim,args,command,design=self.values()
            if mode=='metric':args.remove(next(n for n in args.findall('vcm_arg_data') if n.get('vcm_opt')))
            else:args.set('compvdbpath','/foreign.vdb')
            with self.assertRaises(ValueError):a.native_identity(sim,args,command,design)


class OR(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        manifest=a.life.read_bound(a.core.pre.BASE/'admission-manifest.json',a.core.pre.BASE_SHA)
        p=a.core.pre.BASE/'combined-bits.json'
        cls.before=a.life.read_bound(p,manifest['output_pins'][str(p)])
        q=a.life.read_bound(a.QUAL/'qualification.json',a.Q_SHA);p=a.QUAL/'single-bits.json'
        cls.single=a.life.read_bound(p,q['output_pins'][str(p)])

    def test_actual_full6162_independent_or(self):
        after=a.full_union(self.before,self.single)
        self.assertEqual(len(after['tests']),778)
        self.assertEqual(sum(map(len,after['metrics'].values())),6162)

    def test_foreign_design_shape_universe_and_duplicate(self):
        for kind in ('design','width','checksum','scope','duplicate'):
            single=copy.deepcopy(self.single)
            if kind=='design':single['design']={}
            elif kind=='duplicate':single['tests']=[self.before['tests'][0]]
            else:
                metric=next(iter(single['metrics']));scope=next(iter(single['metrics'][metric]))
                if kind=='scope':single['metrics'][metric].pop(scope)
                elif kind=='width':single['metrics'][metric][scope]['width']+=1
                else:single['metrics'][metric][scope]['checksum']='wrong'
            with self.assertRaises(ValueError):a.full_union(self.before,single)

    def test_mathematical_or_mutation_reject(self):
        correct=a.bitmap.combine(self.before,self.single)
        metric=next(iter(correct['metrics']));scope=next(iter(correct['metrics'][metric]))
        correct['metrics'][metric][scope]['bits']=hex(int(correct['metrics'][metric][scope]['bits'],16)^1)
        with patch.object(a.bitmap,'combine',return_value=correct):
            with self.assertRaisesRegex(ValueError,'OR'):a.full_union(self.before,self.single)

    def test_actual_qualification_dependency_pins_cover_collector(self):
        q=a.life.read_bound(a.QUAL/'qualification.json',a.Q_SHA)
        for module in (a.case,a.case.prior,a.core,a.core.runner,a.core.pre):
            p=Path(module.__file__).resolve();self.assertEqual(q['input_pins'][str(p)],a.life.digest(p))

    def test_live_admit_requires_explicit_authorization(self):
        args=['admit_btb_ring.py','admit','--baseline','/tmp/base','--baseline-seal','x',
              '--output',str(a.life.OUT/'not-created-test'),'--seal','x']
        with patch('sys.argv',args),patch.object(a,'evaluate') as evaluate:
            with self.assertRaisesRegex(ValueError,'authorization'):a.main()
            evaluate.assert_not_called()
        self.assertFalse((a.life.OUT/'not-created-test').exists())


if __name__=='__main__':unittest.main()
