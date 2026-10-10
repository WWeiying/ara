from dataclasses import replace
import unittest
from unittest.mock import patch

import qualify_gap102b_preflight_v3 as m
from test_build_gap102b_preflight_v2 import fixture


def real_fixture():
    rows,symbols,text=fixture()
    data=m.images()
    i=next(i for i,r in enumerate(rows) if r.pc==symbols["g102b_mac"])
    values=dict(rows[i].vector_writes)
    values[10]=int.from_bytes(data["before"][1280:1408],"little")
    rows[i]=replace(rows[i],vector_writes=values)
    return rows,symbols,text


class SuccessorTests(unittest.TestCase):
    def test_exact_preserved_declaration(self):
        result=m.validate(*real_fixture())
        self.assertEqual(result["vector_register_declarations"],43)
        self.assertEqual(result["preserved_declaration_bytes_checked"],128)
        self.assertEqual(result["active_result_bytes"],4)

    def test_preserved_register_not_skipped(self):
        rows,symbols,text=real_fixture()
        i=next(i for i,r in enumerate(rows) if r.pc==symbols["g102b_mac"])
        values=dict(rows[i].vector_writes);values[10]^=1
        rows[i]=replace(rows[i],vector_writes=values)
        with self.assertRaises(ValueError):m.validate(rows,symbols,text)

    def test_wrong_missing_and_extra_declaration(self):
        for reg in (10,11,13):
            rows,symbols,text=real_fixture()
            i=next(i for i,r in enumerate(rows) if r.pc==symbols["g102b_mac"])
            values=dict(rows[i].vector_writes)
            if reg==10:values.pop(10)
            else:values[reg]=0
            rows[i]=replace(rows[i],vector_writes=values)
            with self.assertRaises(ValueError):m.validate(rows,symbols,text)

    def test_csr_guard_and_target_byte_corruption(self):
        for name,offset in (("g102b_dump",1536),("g102b_dump",4088),("g102b_source_dump",504),("g102b_csr",16)):
            rows,symbols,text=real_fixture();memory=list(rows[-1].memory_accesses)
            i=next(i for i,(a,v) in enumerate(memory) if a==symbols[name]+offset)
            a,v=memory[i];memory[i]=(a,v^1);rows[-1]=replace(rows[-1],memory_accesses=tuple(memory))
            with self.assertRaises(ValueError):m.validate(rows,symbols,text)

    def test_no_launcher_or_rebuild_in_successor(self):
        from pathlib import Path
        source=Path(m.__file__).read_text()
        self.assertNotIn("subprocess",source)
        self.assertNotIn("frozen.main(",source)


if __name__=="__main__":unittest.main()
