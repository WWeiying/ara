import inspect
import unittest
from unittest.mock import patch
import capture_lookahead_send_ready762 as c


class CaptureTests(unittest.TestCase):
    def test_verifier_adapts_only_identity_and_result_counts(self):
        v = c.verifier()
        constants = repr(v.__code__.co_consts)
        self.assertIn(c.SCHEMA,constants)
        self.assertIn('EXACT_LOOKAHEAD2_NATIVE_ROUNDTRIP_NOT_APPLICATION_APPROVAL',constants)
        original = inspect.getsource(c.prior.verify)
        for guard in ('native.audit_points','native.native_records','life.check','tools.revalidate',
                      'initial.el','reset.el','final-empty.el','cleanup-empty.el','DISPATCHER_FOUR_NATIVE_DONE'):
            self.assertIn(guard,original)

    def test_adapter_rejects_predecessor_drift(self):
        with patch.object(c.inspect,'getsource',return_value='def verify(): pass'):
            with self.assertRaises(Exception): c.verifier()

    def test_proof_missing_or_unsealed_rejected(self):
        with self.assertRaises(Exception): c.bound_proof('0'*64)

    def test_immutable_tcl_global_source_and_all_stages(self):
        text = c.TCL.read_text()
        self.assertIn('uplevel #0 [list source',text)
        for stage in ('initial','applied','reset','reloaded','final'):
            self.assertIn('fx_audit '+stage,text)
        self.assertIn('gui_cov_excl_review -isEmpty',text)
        self.assertIn('cleanup-empty.el',text)

    def test_actual_historical_auxiliary_pins_complete(self):
        book = c.life.read_bound(c.prior.BASE/'admission-manifest.json',c.proof.BASE_SHA)
        pins = c.historical_pins(book)
        members = (c.prior.BASE/'combined-inputs.txt').read_text().splitlines()
        for root in map(c.Path,members[:2]):
            for p in root.rglob('*'):
                if p.is_file(): self.assertEqual(pins[str(p)],c.life.digest(p))

    def test_wrong_auxiliary_provenance_rejected(self):
        with patch.object(c.life,'read_bound',return_value={'schema':'foreign','baseline':762}):
            with self.assertRaises(Exception): c.historical_pins({})


if __name__ == '__main__': unittest.main()
