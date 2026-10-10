"""Static source-role/EL checks only; no EDA or exclusion creation."""
import csv
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
PACKET = ROOT / 'verification/out/cvxif-observer-boundary785-source-review-agent-20261008-01.json'
SCOPE = 'ara_tb.dut.i_ara_soc.i_system.i_ara_cvxif_dut_bind'


def clean(text):
    return re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.S)


def source_gate(bind, interface, consumer, scopes):
    if scopes != [SCOPE, SCOPE + '.cvxif']:
        raise ValueError('Exact observer scope boundary')
    b, i, c = map(clean, (bind, interface, consumer))
    header = b.split(') (', 1)[1].split(');', 1)[0]
    if len(re.findall(r'\binput\b', header)) != 41 or re.search(r'\b(output|inout|ref)\b', header):
        raise ValueError('Input-only bind owner')
    assignments = re.findall(r'\bassign\s+([^=;]+)=([^;]+);', b)
    if len(assignments) != 43 or any(not re.fullmatch(r'cvxif\.\w+\s*', lhs) for lhs, _ in assignments):
        raise ValueError('Private interface assignment destinations')
    if len(re.findall(r'\bbind\s+ara_system\s+ara_cvxif_dut_bind\b', b)) != 1:
        raise ValueError('Exact bind target')
    cb = i.split('clocking monitor_cb', 1)[1].split('endclocking', 1)[0]
    if re.search(r'\b(output|inout)\b', cb):
        raise ValueError('Input-only monitor clocking')
    if re.search(r'\bvif(?:\.\w+)+\s*(?:<=|=(?!=))', c) or re.search(r'\b(force|release|uvm_driver)\b', b+i+c):
        raise ValueError('No DUT/interface driver')


class BoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = json.loads(PACKET.read_bytes())
        cls.sources = [(ROOT / ('verification/uvm/' + n)).read_text() for n in
                       ('ara_cvxif_dut_bind.sv', 'ara_cvxif_if.sv', 'ara_cvxif_uvm_pkg.sv')]

    def test_frozen_pins_and_compiled_source_closure(self):
        for name, sha in self.p['pins'].items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(), sha)
        old = json.loads((ROOT/'verification/out/cvxif-passive-bind-testbench-scope-source-review770-agent-20261007-01.json').read_bytes())
        for path, sha in old['pins'].items():
            if any(s in path for s in ('verilog.design.xml', 'verilog.sourceinfo.xml', 'tgl.verilog.shape.xml')):
                self.assertEqual(hashlib.sha256(Path(path).read_bytes()).hexdigest(), sha)
        book = json.loads((ROOT/'verification/out/repaired-aligned-build-20260930-01/build-source-pins.json').read_bytes())
        for name in ('ara_cvxif_dut_bind.sv', 'ara_cvxif_if.sv', 'ara_cvxif_uvm_pkg.sv'):
            path = ROOT/'verification/uvm'/name
            self.assertEqual(book[str(path)], hashlib.sha256(path.read_bytes()).hexdigest())
        for row in self.p['exact_scopes']:
            prior = next(x for x in old['compiled_scopes'] if x['scope'] == row['scope'])
            self.assertEqual(prior['module'], row['module'])
            self.assertEqual(prior['toggle_checksum'], row['toggle_checksum'])
            self.assertEqual(prior['design_module_checksum'], row['module_checksum'])
            self.assertEqual(prior['source_file_id'], row['source_file_id'])

    def test_passive_source_role(self):
        source_gate(*self.sources, [SCOPE, SCOPE+'.cvxif'])

    def test_active_port_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Input-only'):
            source_gate(self.sources[0].replace('input logic', 'output logic', 1), *self.sources[1:], [SCOPE, SCOPE+'.cvxif'])

    def test_functional_destination_rejected(self):
        with self.assertRaisesRegex(ValueError, 'destinations'):
            source_gate(self.sources[0].replace('assign cvxif.req_valid', 'assign acc_req.req_valid'), *self.sources[1:], [SCOPE, SCOPE+'.cvxif'])

    def test_clocking_output_rejected(self):
        with self.assertRaisesRegex(ValueError, 'clocking'):
            source_gate(self.sources[0], self.sources[1].replace('input rst_ni,', 'output rst_ni,'), self.sources[2], [SCOPE, SCOPE+'.cvxif'])

    def test_consumer_driver_rejected(self):
        with self.assertRaisesRegex(ValueError, 'driver'):
            source_gate(*self.sources[:2], self.sources[2]+'\nvif.req_ready = 1;', [SCOPE, SCOPE+'.cvxif'])

    def test_functional_or_recursive_scope_rejected(self):
        for scopes in ([SCOPE.rsplit('.', 1)[0]], [SCOPE+'*'], [SCOPE, SCOPE+'.cvxif_fu']):
            with self.assertRaisesRegex(ValueError, 'boundary'):
                source_gate(*self.sources, scopes)

    def test_actual_EL_not_whole_and_overlap_exact(self):
        import report_global777_compact as native
        report = ROOT/self.p['EL_review']['report']
        q = json.loads((report/'qualification.json').read_bytes())
        self.assertEqual(q['population'], 785)
        self.assertEqual(q['status'], 'CURRENT_ADMITTED_POPULATION_COMPACT_FIVE_PHASE_VERIFIED')
        for filename in ('combined.el', 'applied.el'):
            text = (report/filename).read_text()
            if filename == 'applied.el':
                self.assertEqual(q['output_pins'][str(report/filename)], self.p['pins'][str((report/filename).relative_to(ROOT))])
            for row in self.p['exact_scopes']:
                blocks = [b for b in text.split('CHECKSUM:') if 'INSTANCE: '+row['scope']+'\n' in b]
                self.assertTrue(blocks)
                other, masks = native.semantic(''.join('CHECKSUM:'+b for b in blocks))
                self.assertFalse(any(x[-1] == 'WHOLE_SCOPE' for x in other))
                self.assertEqual(len(masks), 10)
                self.assertEqual(sum(bin(v).count('1') for v in masks.values()), row['existing_EL_direction_bits'])

    def test_ranking_partial_masks_are_not_new_capacity(self):
        rank = json.loads((ROOT/'verification/out/dynamic-toggle785-static-ranking-agent-20261008-01.json').read_bytes())
        for target in self.p['exact_scopes']:
            row = next(x for x in rank['ranking'] if x['scope'] == target['scope'])
            self.assertEqual(row['remaining_binary_positions'], target['raw_rank_missing_serialized_positions'])
            partial = [x for x in row['objects'] if x['partial_EL_direction_binding_HOLD']]
            self.assertEqual(len(partial), 5)
            self.assertTrue(all('payload' in x['name'] for x in partial))
        self.assertIsNone(self.p['EL_review']['incremental_native_gain'])

    def test_historical_native_inventory_not_whole_qualification(self):
        capture = ROOT/self.p['native_evidence']['existing_successful_capture']
        for index, count in ((0, 41), (1, 45)):
            path = capture/('native_before_%d.tsv' % index)
            receipt = json.loads((ROOT/self.p['native_evidence']['closed_padding_receipt']).read_bytes())
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), receipt['pins'][str(path)])
            with path.open() as f: rows = list(csv.DictReader(f, delimiter='\t'))
            self.assertEqual(len(rows), count)
            self.assertEqual(len({x['name'] for x in rows}), count)
        for key in ('EDA_started', 'RTL_changed', 'coverage_admitted', 'EL_created', 'assertion_coverage_excluded'):
            self.assertFalse(self.p['proposed_boundary'][key])
        self.assertFalse(self.p['native_evidence']['prior_whole_qualified'])


if __name__ == '__main__':
    unittest.main()
