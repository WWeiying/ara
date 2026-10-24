"""Checker rejection tests with synthetic CSV, never RTL acceptance evidence."""
import csv
from pathlib import Path
import tempfile
import unittest
from shared_wave import profile, script
from sharedwave_checker import check_cycles, command_order


def fixture():
    aliases = [s['alias'] for s in profile()['signals']]
    rows, qbs = [], 0

    def row(owner=None, fire=None, terminal=False, fault=False):
        data = {a: '0' for a in aliases}
        data.update(reset_n='1', normal_vlsu_idle='1', ar_hold_empty='1',
                    reader_range_ready_o='1', akv_context_ready_q='1',
                    activation_context_valid_q='1')
        if fire:
            data[fire + '_command_fire'] = '1'
            data['reader_counters_clear_i'] = '1'
        if owner:
            data[owner + '_active_q'] = '1'
            data[owner + '_read_range_ready'] = '1'
            if terminal:
                data[owner + '_terminal'] = '1'
                data[owner + ('_fault_valid' if owner == 'qbs' and qbs == 2 else '_success_valid')] = '1'
            if fault:
                data['reader_fault_valid_o'] = data[owner + '_read_fault_valid'] = '1'
                data['reader_fault_ready_i'] = data[owner + '_read_fault_ready'] = '1'
                data['reader_fault_kind_o'] = data[owner + '_read_fault_kind'] = '5'
        if owner or fire:
            data['reader_clk_en'] = '1'
        data['time_100fs'] = str((len(rows) + 1) * 10000)
        rows.append(data)

    for owner, _command in command_order():
        row(fire=owner)
        if owner == 'qbs':
            qbs += 1
        row(owner=owner, fault=owner == 'qbs' and qbs == 2)
        row(owner=owner, terminal=True)
        row()
    # Exercise selected payload/tag and backpressure comparisons on a FULL.
    first = rows[1]
    first.update(reader_busy_o='1', akv_read_busy='1',
        reader_range_valid_i='1', akv_read_range_valid='1',
        reader_range_vaddr_i='1000', akv_read_range_vaddr='1000',
        reader_range_bytes_i='80', akv_read_range_bytes='80',
        reader_range_tag_i='41', akv_read_range_tag='41',
        reader_axi_ar_valid_o='1', reader_axi_ar_ready_i='1',
        reader_data_valid_o='1', akv_read_data_valid='1',
        reader_data_ready_i='1', akv_read_data_ready='1',
        reader_data_o='feed', akv_read_data='feed',
        reader_data_strb_o='ffff', akv_read_data_strb='ffff',
        reader_data_offset_o='20', akv_read_data_offset='20',
        reader_data_tag_o='41', akv_read_data_tag='41',
        reader_completion_valid_q='1', akv_read_completion_valid='1',
        reader_completion_ready_i='1', akv_read_completion_ready='1',
        reader_completion_tag_o='41', akv_read_completion_tag='41')
    return rows


class SharedWaveTests(unittest.TestCase):
    def check(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'cycles.csv'
            with path.open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            return check_cycles(path)

    def test_complete_fixture(self):
        result = self.check(fixture())
        self.assertEqual(result['zero_read_commands'], 63)
        self.assertEqual(len(result['terminals']), 71)

    def test_topology(self):
        paths = [s['path'] for s in profile()['signals']]
        self.assertFalse(any('/i_qbs_engine/i_read_engine/' in p or
                             '/i_akv_engine/i_read_engine/' in p for p in paths))
        self.assertTrue(any('/i_shared_reader/i_read_engine/' in p for p in paths))
        self.assertIn('dump -close', script())
        with self.assertRaises(ValueError):
            script(500001)

    def test_counter_clear_required(self):
        rows = fixture()
        rows[0]['reader_counters_clear_i'] = '0'
        with self.assertRaisesRegex(ValueError, 'Counter reset'):
            self.check(rows)

    def test_inactive_payload_rejected(self):
        rows = fixture()
        rows[1]['qbs_read_data'] = 'bad'
        with self.assertRaisesRegex(ValueError, 'Inactive endpoint'):
            self.check(rows)

    def test_clock_required(self):
        rows = fixture()
        rows[0]['reader_clk_en'] = '0'
        with self.assertRaisesRegex(ValueError, 'clock disabled'):
            self.check(rows)

    def test_early_owner_release(self):
        rows = fixture()
        rows[2]['akv_active_q'] = '0'
        with self.assertRaisesRegex(ValueError, 'disappeared'):
            self.check(rows)

    def test_pending_write_at_admission(self):
        rows = fixture()
        rows[0]['akv_context_write_busy'] = '1'
        with self.assertRaisesRegex(ValueError, 'Pending context write'):
            self.check(rows)

    def test_sample_gap(self):
        rows = fixture()
        rows[2]['time_100fs'] = str(int(rows[2]['time_100fs']) + 1)
        with self.assertRaisesRegex(ValueError, 'Missing settled'):
            self.check(rows)

    def test_resident_external_reads(self):
        rows = fixture()
        # Second command is a local AKV LOAD, which must not access external RAM.
        rows[5]['reader_axi_ar_valid_o'] = '1'
        rows[5]['reader_axi_ar_ready_i'] = '1'
        with self.assertRaisesRegex(ValueError, 'inherited external reads'):
            self.check(rows)

    def test_foreign_context_changes(self):
        rows = fixture()
        index = next(i for i, r in enumerate(rows) if r['qbs_active_q'] == '1')
        rows[index]['akv_context_q_base_q'] = '100'
        with self.assertRaisesRegex(ValueError, 'Foreign owner changed'):
            self.check(rows)

    def test_unowned_activity(self):
        for field in ('axi_ar_valid_o', 'mmu_req_o', 'range_valid_i', 'busy_o',
                      'data_ready_i', 'completion_ready_i', 'fault_ready_i'):
            with self.subTest(field=field):
                rows = fixture()
                rows[3]['reader_' + field] = '1'
                rows[3]['reader_clk_en'] = '1'
                with self.assertRaisesRegex(ValueError, 'without owner'):
                    self.check(rows)

    def test_selected_payload_routing(self):
        for field in ('data', 'data_tag', 'completion_tag', 'range_tag', 'data_ready'):
            with self.subTest(field=field):
                rows = fixture()
                rows[1]['akv_read_' + field] = '0'
                with self.assertRaisesRegex(ValueError, 'routing'):
                    self.check(rows)

    def test_invalid_active_payload_may_be_unknown(self):
        rows = fixture()
        # The second FULL-active sample is not a valid payload transfer.
        for field in ('data_o', 'data_strb_o', 'data_offset_o', 'data_tag_o',
                      'completion_tag_o', 'fault_kind_o', 'fault_vaddr_o', 'fault_tag_o'):
            rows[2]['reader_' + field] = 'x'
        for field in ('data', 'data_strb', 'data_offset', 'data_tag',
                      'completion_tag', 'fault_kind', 'fault_vaddr', 'fault_tag'):
            rows[2]['akv_read_' + field] = 'x'
        self.check(rows)


if __name__ == '__main__':
    unittest.main()
