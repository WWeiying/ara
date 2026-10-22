"""Use actual first EL, not a fabricated native signature fixture."""
import json
import unittest
import qualify_dwc_points742_v2 as v


class ActualFormatTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = v.inventory(json.loads(v.base.REVIEW.read_bytes()))
        cls.text = (v.FAILED / 'first.el').read_text()

    def reject(self, text):
        self.assertNotEqual(text, self.text)
        with self.assertRaises(ValueError): v.parse_el(text, self.c)

    def test_actual_native_pairs_and_states(self):
        r = v.parse_el(self.text, self.c)
        self.assertEqual(sum(x[0] == 'fsm' for x in r), 31)
        self.assertEqual(sum(x[0] == 'tgl' for x in r), 168)

    def test_missing_direction(self):
        self.reject(self.text.replace('Toggle 1to0 b_fifo_full "logic b_fifo_full"\n', '', 1))

    def test_extra_direction(self):
        self.reject(self.text.replace('Toggle 1to0 b_fifo_full', 'Toggle 0to1 b_fifo_full', 1))

    def test_missing_state(self): self.reject(self.text.replace('State ABSORB_W "3"\n', '', 1))
    def test_wrong_encoded_state(self): self.reject(self.text.replace('State ABSORB_W "3"', 'State ABSORB_W "0"', 1))
    def test_interface(self): self.reject(self.text.replace('b_fifo_full', 'slv_req_i.aw_valid'))
    def test_width(self): self.reject(self.text.replace('counter_q[8:0]', 'counter_q[7:0]', 1))
    def test_checksum(self): self.reject(self.text.replace('897524028', '897524029', 1))
    def test_duplicate(self): self.reject(self.text + self.text)
    def test_protected_normal_state(self): self.reject(self.text + 'State R_FEEDTHROUGH "1"\n')
    def test_protected_normal_arc(self): self.reject(self.text + 'Transition R_RESET->R_FEEDTHROUGH "0->1"\n')

    def test_original_missing_final_stays_hold(self):
        self.assertEqual(json.loads((v.FAILED / 'status.json').read_bytes())['status'], 'HOLD')
        self.assertFalse((v.FAILED / 'final-empty.el').exists())


if __name__ == '__main__': unittest.main()
