import copy
import csv
import tempfile
import unittest
from pathlib import Path
from types import FunctionType
import qualify_gap113_cached_reset as q


class Epochs(unittest.TestCase):
    def fixture(self):
        commits = [dict(cycle=str(c), event='retire', order=str(o), trap='0')
                   for c,o in ((1,0),(2,1),(1,0),(2,1))]
        vectors = [dict(cycle=str(c),event=e) for c,e in ((0,'config'),(2,'reset'),(1,'alloc'))]
        return commits,vectors

    def test_two_epochs(self):
        epochs, cycle=q.split_epochs(*self.fixture())
        self.assertEqual(cycle,2); self.assertEqual(len(epochs),2)
        self.assertEqual(epochs[1][1][0]['event'],'config')

    def test_missing_reset(self):
        c,v=self.fixture(); v.pop(1)
        with self.assertRaises(ValueError): q.split_epochs(c,v)

    def test_extra_reset(self):
        c,v=self.fixture();v.append(dict(v[1]))
        with self.assertRaises(ValueError): q.split_epochs(c,v)

    def test_wrong_boundary(self):
        c,v=self.fixture();v[1]['cycle']='1'
        with self.assertRaises(ValueError): q.split_epochs(c,v)

    def test_trap(self):
        c,v=self.fixture();c[1]['trap']='1'
        with self.assertRaises(ValueError): q.split_epochs(c,v)

    def test_missing_retire(self):
        c,v=self.fixture();c[3]['order']='2'
        with self.assertRaises(ValueError): q.split_epochs(c,v)

    def test_partial_csv(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'trace.csv';p.write_text('cycle,event,order\n1,retire\n')
            with self.assertRaises(ValueError):q.read_csv(p)

    def test_full_frozen_cached_fixture(self):
        cached=q.run.cached; adapter=cached.qualifier(q.RUN_SEAL)
        view=adapter.adapter();symbols,data,sites=view.elf_view();native=adapter.independent_native()
        audit=adapter.runtime(view,symbols,data,sites,native)
        self.assertEqual(audit['full_vrf_bytes'],8192)
        self.assertEqual(audit['checks'],41)
        self.assertEqual(audit['csr_values'],24)
        self.assertEqual(audit['source_guard_bytes'],7328)

    def test_full_fixture_corrupt_native_reject(self):
        adapter=q.run.cached.qualifier(q.RUN_SEAL);view=adapter.adapter()
        symbols,data,sites=view.elf_view();native=adapter.independent_native()
        native[0]['result_bits'][0]^=1
        with self.assertRaises(ValueError):adapter.runtime(view,symbols,data,sites,native)

    def first_epoch(self, mutation=None):
        cf,cr=q.read_csv(q.run.RUN/'commit_trace.csv')
        vf,vr=q.read_csv(q.run.RUN/'vector_trace.csv')
        epochs,_=q.split_epochs(cr,vr);cr,vr=epochs[0]
        adapter=q.run.cached.qualifier(q.RUN_SEAL);view=adapter.adapter()
        symbols,data,sites=view.elf_view()
        if mutation=='owner':
            row=next(r for r in vr if r['event']=='write');row['vid']=str(int(row['vid'])+1)
        if mutation=='completion':
            row=dict(next(r for r in vr if r['event']=='alloc' and int(r['insn'],16)==adapter.WORD))
            row['event']='done';vr.append(row)
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);q.write_csv(p/'vector_trace.csv',vf,vr)
            return q.cancelled_epoch(p,cr,vr,adapter,symbols,sites)

    def test_actual_cancelled_seed_full_bytes(self):
        self.assertEqual(self.first_epoch()['seed_bytes_checked'],4096)

    def test_cancelled_epoch_wrong_owner(self):
        with self.assertRaises(ValueError):self.first_epoch('owner')

    def test_cancelled_epoch_completion(self):
        with self.assertRaises(ValueError):self.first_epoch('completion')


if __name__=='__main__':unittest.main()
