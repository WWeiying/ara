import copy
import unittest
from unittest.mock import patch
import report_population791_inherited785 as owner


class Formal791(unittest.TestCase):
    def setUp(self):
        ledger = ['compile']+['test%d' % i for i in range(791)]
        self.source = dict(input_ledger=ledger,hierarchy_roots=['root'],tool_identity={'fixed':True})
        self.old = dict(input_ledger=ledger[:786],hierarchy_roots=['root'],tool_identity={'fixed':True})
        self.bits = dict(tests=ledger[1:],metrics={m:dict.fromkeys(range(n)) for m,n in
                         dict(line=1892,cond=2023,branch=2155,fsm=92).items()})
        self.chain = [dict(population=i,manifest='historical%d'%i,seal='historical') for i in range(784,792)]
        self.chain[0].update(manifest=str(owner.prior.FORMAL784),seal=owner.prior.FORMAL784_SHA)
        self.chain[-1].update(manifest=str(owner.BASE),seal=owner.BASE_SHA)

    def test_exact791_counts_prefix_membership(self): owner.corpus_gate(self.source,self.bits,self.old)
    def test_same_count_foreign_or_reordered_membership_rejected(self):
        self.bits['tests'][0],self.bits['tests'][1] = self.bits['tests'][1],self.bits['tests'][0]
        with self.assertRaises(ValueError): owner.corpus_gate(self.source,self.bits,self.old)
    def test_duplicate_ledger_rejected(self):
        self.source['input_ledger'][-1] = self.source['input_ledger'][-2]
        with self.assertRaises(ValueError): owner.corpus_gate(self.source,self.bits,self.old)
    def test_prefix_or_tool_root_drift_rejected(self):
        for key in ('input_ledger','tool_identity','hierarchy_roots'):
            old = copy.deepcopy(self.old)
            old[key] = []
            with self.assertRaises(ValueError): owner.corpus_gate(self.source,self.bits,old)
    def test_incomplete_metric_family_rejected(self):
        self.bits['metrics']['line'].pop(0)
        with self.assertRaises(ValueError): owner.corpus_gate(self.source,self.bits,self.old)
    def test_exact_suffix_and_missing_or_foreign_seal(self):
        self.assertEqual(len(owner.suffix_chain(self.chain)),8)
        with self.assertRaises(ValueError): owner.suffix_chain(self.chain[:-1])
        self.chain[-1]['seal'] = 'foreign'
        with self.assertRaises(ValueError): owner.suffix_chain(self.chain)
    def test_foreign_manifest_before_historical_reads(self):
        with self.assertRaises(ValueError): owner.approved(None,owner.BASE,'foreign')
    def test_runtime_reuses_unchanged_successful_engine(self):
        functions = owner.context()
        for function,name in zip(functions,('prepare','check','verify','run')):
            self.assertIs(function.__code__,getattr(owner.prior.population,name).__code__)
        self.assertIs(functions[0].__globals__['stable'].Reader,owner.Reader)


if __name__ == '__main__': unittest.main()
