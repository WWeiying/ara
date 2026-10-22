import unittest
from unittest.mock import patch
import collect_itlb_asid_exec_bulk_axi as a


def fixture(req='0'*281, resp='0'*84, child=False, width=281):
    root=a.core.support.old.CORE
    decl={root+'.noc_req_o':dict(width=width,code='q'),
          root+'.noc_resp_i':dict(width=84,code='s')}
    if child:decl[root+'.noc_req_o.ar_valid']=dict(width=1,code='bad')
    yield 'declarations',decl
    yield 10,dict(q=req,s=resp),dict(q=req,s=resp)


class PackedAXI(unittest.TestCase):
    def test_actual_historical_source_chain(self):
        self.assertEqual(len(a.source_contract()),8)

    def test_source_hash_drift_rejected(self):
        with patch.object(a.life,'read_bound',return_value={}):
            with self.assertRaises(KeyError):a.source_contract()

    def test_layout_covers_all_parent_bits_exactly(self):
        for width,fields in a.layouts().values():
            bits=[i for hi,lo in fields.values() for i in range(lo,hi+1)]
            self.assertEqual(sorted(bits),list(range(width)))

    def test_known_offsets_not_roundtrip_self_consistency(self):
        root=a.core.support.old.CORE
        req=(0xa<<96)|(0x123456789abcdef0<<32)|(7<<24)|(3<<21)|(1<<19)|2
        resp=(1<<82)|(1<<72)|(0xa<<68)|(0xfeed0123456789ab<<4)|2
        it=iter(a.project(iter(fixture(format(req,'0281b'),format(resp,'084b')))))
        _,decl=next(it);_,before,after=next(it)
        def val(port,field):return int(before[decl[root+'.'+port+'.'+field]['code']],2)
        self.assertEqual(val('noc_req_o','ar.id'),10)
        self.assertEqual(val('noc_req_o','ar.addr'),0x123456789abcdef0)
        self.assertEqual(val('noc_req_o','ar.len'),7)
        self.assertEqual(val('noc_req_o','ar.size'),3)
        self.assertEqual(val('noc_req_o','ar_valid'),1)
        self.assertEqual(val('noc_resp_i','ar_ready'),1)
        self.assertEqual(val('noc_resp_i','r.data'),0xfeed0123456789ab)
        self.assertEqual(val('noc_resp_i','r.last'),1)
        self.assertEqual(before,after)

    def test_preedge_state_not_overwritten_by_postedge(self):
        it=iter(fixture());head=next(it)
        projected=iter(a.project(iter([head,(10,dict(q='0'*281,s='0'*84),
            dict(q='0'*279+'10',s='0'*84))])))
        _,decl=next(projected);_,before,after=next(projected)
        code=decl[a.core.support.old.CORE+'.noc_req_o.ar_valid']['code']
        self.assertEqual(before[code],'0');self.assertEqual(after[code],'1')

    def test_ambiguous_child_rejected(self):
        with self.assertRaisesRegex(ValueError,'Ambiguous'):list(a.project(iter(fixture(child=True))))

    def test_wrong_parent_width_rejected(self):
        with self.assertRaisesRegex(ValueError,'parent'):list(a.project(iter(fixture(width=280))))

    def test_invalid_encoding_rejected(self):
        for req in ('0'*280,'2'+'0'*280):
            with self.assertRaisesRegex(ValueError,'encoding'):list(a.project(iter(fixture(req=req))))

    def test_unknown_bits_remain_unknown(self):
        it=iter(a.project(iter(fixture(req='x'*281))))
        _,decl=next(it);_,before,_=next(it)
        self.assertEqual(before[decl[a.core.support.old.CORE+'.noc_req_o.ar_valid']['code']],'x')


if __name__=='__main__':unittest.main()
