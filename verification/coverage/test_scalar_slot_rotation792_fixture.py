"""Actual immutable Spike commits: replace one store, never edit sealed tests."""
from dataclasses import replace
import json
import os
from pathlib import Path
import unittest
import test_scalar_slot_rotation792 as prior


class SlotGold(prior.SlotGold):
    @unittest.skipUnless(os.environ.get('SLOT_PREFLIGHT'),'Actual fixture requested')
    def test_actual_gold(self):
        b=prior.b; p=Path(os.environ['SLOT_PREFLIGHT'])
        m=json.loads((p/'preflight-manifest.json').read_bytes())
        b.shared.check(m['pins']); b.shared.check(m['output_pins'])
        s=b.elf_shape(p/'input.elf'); cs=b.reference(p/'spike.trace',s)
        ledger=b.traps((p/'spike.trace').read_text(),s)
        self.assertEqual(b.validate(cs,s,ledger),m['validation'])
        for symbol in ('slot_records','slot_page','slot_csr','g75_result'):
            bad=list(cs)
            indices=[i for i,c in enumerate(cs) if any(a==s[symbol] and v is not None for a,v in c.memory_accesses)]
            self.assertTrue(indices); i=indices[-1]; c=bad[i]
            bad[i]=replace(c,memory_accesses=tuple((a,v^1 if a==s[symbol] and v is not None else v) for a,v in c.memory_accesses))
            with self.assertRaises(ValueError): b.validate(bad,s,ledger)


if __name__=='__main__': unittest.main()
