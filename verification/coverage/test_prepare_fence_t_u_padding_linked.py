import json
import unittest
import prepare_fence_t_u_padding_linked as tool


class LinkedTests(unittest.TestCase):
    def setUp(self):
        self.metadata=json.loads((tool.BUILD/'elf_metadata.json').read_bytes())[0]
        self.blob=(tool.BUILD/'input.elf').read_bytes()

    def test_real_three_sites(self):
        proof=tool.audit(self.metadata,self.blob)
        self.assertEqual(proof['capture_stores_static'],195)
        self.assertEqual(proof['canonical_custom0_sites'],3)

    def test_third_capture_mutation_rejected(self):
        proof=tool.audit(self.metadata,self.blob)
        blob=bytearray(self.blob)
        pos=proof['sites'][2]['resume_file_offset']
        blob[pos:pos+4]=(0x13).to_bytes(4,'little')
        with self.assertRaises(ValueError): tool.audit(self.metadata,blob)

    def test_ecall_mutation_rejected(self):
        symbols={s['Symbol']['Name']['Name']:s['Symbol'] for s in self.metadata['Symbols']}
        pc=symbols['padding_u_ecall']['Value']
        sec=next(s['Section'] for s in self.metadata['Sections']
                 if s['Section']['Address']<=pc<s['Section']['Address']+s['Section']['Size'])
        pos=sec['Offset']+pc-sec['Address']
        blob=bytearray(self.blob);blob[pos:pos+4]=(0x13).to_bytes(4,'little')
        with self.assertRaises(ValueError): tool.audit(self.metadata,blob)


if __name__=='__main__': unittest.main()
