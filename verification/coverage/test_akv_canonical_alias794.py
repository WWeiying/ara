import copy
import json
import os
from pathlib import Path
import struct
import unittest
import xml.etree.ElementTree as E
import preflight_akv_canonical_alias794 as p


class Alias(unittest.TestCase):
    def symbols(self):return {n:0x80010000+i*0x10000 for i,n in enumerate(p.NAMES)}
    def memory(self):
        s=self.symbols();m={}
        for name,data in p.expected(s).items():
            for i,b in enumerate(data):m[s[name]+i]=b
        for name in ('akva_saved','akva_restored'):
            for i in range(64):m[s[name]+i]=0
        return s,m
    def test_canonical(self):
        for phase in p.static.ALIASES:
            for va in phase:self.assertTrue(p.static.canonical(va));self.assertEqual(va&4095,0)
        self.assertFalse(p.static.canonical(1<<39))
    def test_two_samePA_mappings(self):
        s,m=self.memory();rows=p.validate_memory(m,s)
        self.assertEqual([r['pa'] for r in rows[:3]],[r['pa'] for r in rows[3:]])
    def test_full_oracle_corruption(self):
        s,m=self.memory()
        for name in ('akva_pages','entropy_snapshots','entropy_csrs','entropy_descriptors','akva_root','akva_traps','g75_result','akva_restored'):
            bad=dict(m);bad[s[name]]^=1
            with self.subTest(name=name),self.assertRaises(ValueError):p.validate_memory(bad,s)
    def test_wrong_PTE_and_permission(self):
        s,m=self.memory();vpn=p.static.ALIASES[0][0]>>12;addr=s['akva_leaf']+(vpn&511)*8
        for word in (0,((s['akva_pages']+4096)>>12<<10)|0xc7,(s['akva_pages']>>12<<10)|0xd7):
            bad=dict(m)
            for i,b in enumerate(struct.pack('<Q',word)):bad[addr+i]=b
            with self.assertRaises(ValueError):p.translate(bad,(8<<60)|(s['akva_root']>>12),p.static.ALIASES[0][0]+64) if word!=(((s['akva_pages']+4096)>>12<<10)|0xc7) else p.validate_memory(bad,s)
    def test_parameterized_definition_strict(self):
        d=E.fromstring('<root><srcdef id="-1" name="engine"><srcinst id="1" name="top"/></srcdef></root>')
        i=E.fromstring('<root><instance_data name="top" chksum="5"/></root>')
        s=E.fromstring('<root><tgldef name="engine ( parameter P=1 ) " id="-1" chksum="5"><tglinst id="1" name="top"/></tgldef></root>')
        self.assertEqual(p.static.definitions(d,i,s,['top'])['top']['checksum'],'5')
        for attr,value in (('id','2'),('name','other')):
            bad=copy.deepcopy(s);bad[0][0].set(attr,value)
            with self.assertRaises(ValueError):p.static.definitions(d,i,bad,['top'])
    @unittest.skipUnless(os.environ.get('AKV_ALIAS_PREFLIGHT'),'Actual fixture explicitly requested')
    def test_actual(self):
        path=Path(os.environ['AKV_ALIAS_PREFLIGHT']);m=json.loads((path/'preflight-manifest.json').read_bytes())
        p.old.shared.check(m['pins']);p.old.shared.check(m['output_pins'])
        self.assertEqual(m['validation']['checks'],4247);self.assertEqual(m['validation']['ecalls'],2)


if __name__=='__main__':unittest.main()
