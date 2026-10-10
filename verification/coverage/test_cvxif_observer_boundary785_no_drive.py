"""Supplement frozen observer evidence without changing its prior packet/tests."""
import hashlib
import json
import re
import unittest
import test_cvxif_observer_boundary785 as prior


def no_drive(sources):
    text = '\n'.join(prior.clean(s) for s in sources)
    forbidden = (r'\b(?:force|release|disable|uvm_driver|uvm_sequencer)\b',
                 r'\buvm_hdl_\w+\s*\(', r'\$(?:deposit|assertoff|assertkill)\b',
                 r'\b(?:import|export)\s*"DPI', r'\bvpi_\w+\s*\(',
                 r'\b(?:vif|dut|ara_tb)(?:\.\w+|\[[^\]]+\])+\s*(?:<=|=(?!=)|\+\+|--)',
                 r'\b(?:vif|dut|ara_tb)(?:\.\w+|\[[^\]]+\])*\.(?:deposit|force|poke|put|write)\s*\(')
    if any(re.search(pattern, text) for pattern in forbidden):
        raise ValueError('Driver/backdrive or check suppression mechanism')
    consumer = prior.clean(sources[2])
    agent = consumer.split('class cvxif_agent #', 1)[1].split('endclass', 1)[0]
    creates = re.findall(r'\b(\w+)#\([^;]*?\)::type_id::create', agent)
    if creates != ['cvxif_monitor']:
        raise ValueError('Monitor-only agent')
    if 'agent.monitor.analysis_port.connect(scoreboard.analysis_export);' not in consumer:
        raise ValueError('Passive scoreboard topology')
    if not all(t in sources[0] for t in ('run_test("ara_cvxif_dut_test");', 'assert (axi_b_ready_i)')):
        raise ValueError('Runtime checks removed')


class NoDriveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sources = [(prior.ROOT/('verification/uvm/'+n)).read_text() for n in
                       ('ara_cvxif_dut_bind.sv', 'ara_cvxif_if.sv', 'ara_cvxif_uvm_pkg.sv')]

    def test_actual_frozen_sources_no_drive(self):
        proof = json.loads(prior.PACKET.read_bytes())
        supplement = json.loads((prior.ROOT/'verification/out/cvxif-observer-boundary785-no-drive-supplement-agent-20261008-01.json').read_bytes())
        self.assertEqual(hashlib.sha256(prior.PACKET.read_bytes()).hexdigest(), supplement['parent_review_sha256'])
        for name, sha in proof['pins'].items():
            if name.startswith('verification/uvm/'):
                self.assertEqual(hashlib.sha256((prior.ROOT/name).read_bytes()).hexdigest(), sha)
        prior.source_gate(*self.sources, [prior.SCOPE, prior.SCOPE+'.cvxif'])
        no_drive(self.sources)
        self.assertEqual(supplement['exact_compiled_boundary'], [
            {k: row[k] for k in ('scope', 'module_checksum', 'toggle_checksum')} for row in proof['exact_scopes']])

    def test_backdrive_mechanisms_rejected(self):
        for mutation in ('force dut.req = 1;', '$deposit(dut.req, 1);',
                         'uvm_hdl_deposit("dut.req", 1);', 'uvm_hdl_force("dut.req", 1);',
                         'vpi_put_value(handle, value, 0, 0);', 'import "DPI-C" function void drive();',
                         'vif.req_ready <= 1;', 'vif.req_trans_id[0] = 1;',
                         'ara_tb.dut.req = 1;', 'dut.req++;', 'vif.poke(1);',
                         'class new_driver extends uvm_driver; endclass'):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                no_drive([*self.sources[:2], self.sources[2]+'\n'+mutation])

    def test_check_suppression_rejected(self):
        for mutation in ('$assertoff;', '$assertkill;', 'disable check_block;'):
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                no_drive([self.sources[0]+'\n'+mutation, *self.sources[1:]])
        with self.assertRaisesRegex(ValueError, 'checks removed'):
            no_drive([self.sources[0].replace('assert (axi_b_ready_i)', ''), *self.sources[1:]])

    def test_no_native_or_percentage_claim(self):
        s = json.loads((prior.ROOT/'verification/out/cvxif-observer-boundary785-no-drive-supplement-agent-20261008-01.json').read_bytes())
        for key in ('EDA_started', 'EL_created', 'RTL_changed', 'coverage_admitted'):
            self.assertFalse(s[key])
        self.assertFalse(s['checks_preservation']['assertion_coverage_excluded'])


if __name__ == '__main__':
    unittest.main()
