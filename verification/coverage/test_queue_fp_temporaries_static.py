import unittest
import queue_fp_temporaries_static as audit


class ConstantTemporaries(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = (audit.ROOT/'hardware/src/lane/operand_queue.sv').read_text()

    def test_frozen_source_contract(self):
        self.assertTrue(audit.source_contract(self.source)['nonzero_writers_gated_by_FPU'])

    def test_extra_writer_rejected(self):
        with self.assertRaises(ValueError):
            audit.source_contract(self.source+'\nassign fp32 = ibuf_operand;\n')

    def test_disabled_gate_removed_rejected(self):
        with self.assertRaises(ValueError):
            audit.source_contract(self.source.replace('if (FPUSupport != FPUSupportNone)', 'if (1)'))

    def test_nonzero_default_rejected(self):
        with self.assertRaises(ValueError):
            audit.source_contract(self.source.replace("fp32 = '0;", "fp32 = '1;"))

    def test_only_exact_internal_fields(self):
        self.assertEqual(len(audit.fields()),21)
        self.assertFalse(any(n.startswith(('operand','cmd','mask','valid','ready')) for n in audit.fields()))


if __name__=='__main__': unittest.main()
