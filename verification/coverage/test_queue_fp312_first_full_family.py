"""Source-first identity is not a captured local qualification."""
import unittest
import queue_fp312_first_full_family as m


class Family(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.item=m.family()

    def test_exact_actual_reference_and_source_typed_EL(self):
        i=self.item;m.life.check(i['source_pins']);m.contract(i['config'])
        self.assertEqual(len(i['canonical']),312)
        self.assertEqual(sum(len(rows) for rows in i['reference'].values()),1360)
        self.assertEqual(sum(len(rows) for rows in i['targets'].values()),312)
        self.assertEqual(m.records(i['el'],i['config']),i['canonical'])

    def test_no_local_receipt_or_launch_promotion(self):
        i=self.item
        self.assertFalse(i['local_qualified']);self.assertIsNone(i['qualification_seal'])
        self.assertFalse(i['config']['launch_authorized']);self.assertFalse(i['population_application'])
        self.assertEqual(i['qualification_origin'],'SOURCE_PROVEN_FIRST_FULL_SESSION')
        self.assertEqual(i['EL_origin'],'SOURCE_TYPED_DECLARATION_NOT_NATIVE_CAPTURE')

    def test_shared_checksum_cannot_move_ALU_fields_to_MFPU(self):
        i=self.item
        with self.assertRaises(ValueError):m.records(i['el'].replace('i_operand_queue_alu_a','i_operand_queue_mfpu_a',1),i['config'])
        for scope,names in i['signals'].items():
            if 'i_operand_queue_mfpu_' in scope:
                self.assertEqual(set(names),m.native.source.FP8)
                self.assertFalse(any(n.startswith(('fp16','fp32')) for n in names))


if __name__=='__main__':unittest.main()
