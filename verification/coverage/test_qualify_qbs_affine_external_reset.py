import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import qualify_qbs_affine_external_reset as q


class AffineTests(unittest.TestCase):
    def test_exact_native_host_and_analytic_gold(self):
        items = q.native()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]['result_bits'][0], 0)
        self.assertEqual(items[1]['result_bits'][0], q.inherited.integer_single(1280))

    def test_actual_elf_all_eight_seed_snapshot_sites(self):
        symbols, data, sites = q.adapter().elf_view()
        inputs = q.native()
        for phase in (0, 1):
            regions = q.regions(phase, symbols, data, inputs)
            self.assertEqual(len(regions['actual']), 4224)
            self.assertEqual(len(regions['weights']) + len(regions['activation']), 3776)
            self.assertEqual(len(sites[phase]), 8)
            import struct
            self.assertEqual(list(struct.unpack('<12Q', regions['csr_packet'][32:128])),
                             [8,16,0,2,8,5]*2)
        self.assertEqual((q.descriptor(8) >> 4) & 15, 1)

    def test_actual_terminal_gold_labels_and_contract(self):
        p = q.life.OUT / 'qbs-affine-aux-external-reset-old-image-745-agent-20261007-01/run.vcs.log'
        self.assertEqual(q.software(p)['requests'], 51)

    def test_unknown_fatal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / 'run.log'
            src = q.life.OUT / 'qbs-affine-aux-external-reset-old-image-745-agent-20261007-01/run.vcs.log'
            p.write_text(src.read_text() + '\nUVM_FATAL @ 1: failure\n')
            with self.assertRaises(ValueError): q.software(p)

    def test_no_zero_gain_qualification_is_admission(self):
        self.assertNotEqual(q.BASE_SHA, q.run.BASE_SHA)
        self.assertEqual(q.BASE.name, 'external-reset-fpu-half-offline-admitted-746-agent-20261007-01')

    def test_wrong_descriptor_domain_rejected(self):
        for value in (7, True, '8'):
            with self.assertRaises(ValueError): q.descriptor(value)

    def waveform(self, allocated=0, retained=1, guard='1'):
        target = q.run.SCOPE[len('ara_tb.'):] + '.entry_state_q[0]'
        valid = q.run.SCOPE[len('ara_tb.'):] + '.entry_valid_q[0]'
        selection = q.run.configuration('aux')
        events = [('declarations', {selection['ext_target']: dict(code='s'), selection['ext_guard']: dict(code='g')})]
        events += [(100, {'s': format(retained, '03b'), 'g':'0'}, {'s': format(allocated, '03b'), 'g': guard})]
        return events, selection

    def test_slot_reuse_exact_stage_to_dot(self):
        events, selection = self.waveform()
        with patch.object(q, 'FunctionType', return_value=lambda path: iter(events)):
            self.assertEqual(q.slot_reuse(Path('/mock'), selection, 50)['allocated_state'], 0)

    def test_slot_wrong_state_rejected(self):
        for allocated, retained, guard in [(1,1,'1'),(0,2,'1'),(0,1,'0')]:
            events, selection = self.waveform(allocated, retained, guard)
            with patch.object(q, 'FunctionType', return_value=lambda path: iter(events)):
                with self.assertRaises(ValueError): q.slot_reuse(Path('/mock'), selection, 50)

    def test_actual_mda_and_packed_bit_projection(self):
        source = q.life.OUT / 'qbs-affine-wave-mda-diagnostic-746-agent-20261007-01/external-reset.vcd'
        with tempfile.TemporaryDirectory() as tmp:
            selected = Path(tmp) / 'selected.vcd'
            binding = q.selected_wave(source, selected, q.run.configuration('aux'))
            self.assertEqual(binding['guard_width'], 16)
            window = q.reset_wave.audit(selected, q.run.configuration('aux'))
            self.assertEqual(window['actual_stage'], 1)
            self.assertEqual(q.slot_reuse(selected, q.run.configuration('aux'), window['release_timestamp'])['allocated_state'], 0)


if __name__ == '__main__': unittest.main()
