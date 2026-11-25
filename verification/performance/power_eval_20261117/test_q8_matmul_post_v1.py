"""Host fixtures only; none are measurement activity."""
import copy
import tempfile
import unittest
from pathlib import Path

import q8_matmul_post_v1 as m


def frames():
    rows = {}
    def put(cycle, **values):
        rows.setdefault((cycle+15)*10000, {}).update(values)
    initial = {key: '0' for key in m.PATHS}
    initial.update(reset='1',ack='00',pc='0',writeback='0',compute_state='0011')
    put(1446, **initial)
    for cycle in range(1446,44480):
        put(cycle,clock='0',qbs_clock='0')
        if cycle < 44479:
            rows.setdefault((cycle+15)*10000+5000, {}).update(clock='1',qbs_clock='1')
    for cycle,pc,csr in ((15988,0x80001864,15988),(44479,0x80001884,44479)):
        put(cycle,pc=bin(pc)[2:],ack='01',writeback=bin(csr)[2:])
        if cycle < 44479:
            put(cycle+1,ack='00')
    for i in range(8):
        put(16000+3000*i,command='1')
        put(16001+3000*i,command='0')
        put(17000+3000*i,success='1')
        put(17001+3000*i,success='0')
    return sorted(rows.items())


class PhaseTests(unittest.TestCase):
    def setUp(self):
        self.parent = dict(first_cycle=1446,last_cycle=44479,
            vcd_evidence=dict(first_tick=14610000,timescale_fs=100))
        self.frames = frames()

    def test_exact_span_and_commands(self):
        phase = m.phase_bounds(self.frames,self.parent)
        self.assertEqual(phase['cycles'],28491)
        self.assertEqual(phase['gate_minus_rtl']['duration'],0)
        proof = m.audit_phase(self.frames,phase)
        self.assertEqual(len(proof['rises']['command']),8)
        self.assertFalse(proof['gate_protocol_proof'])

    def test_measured_gate_offset_not_rtl_crop(self):
        shifted = [(tick+10000,change) for tick,change in self.frames]
        phase = m.phase_bounds(shifted,dict(self.parent,last_cycle=44480))
        self.assertEqual(phase['first_cycle'],15989)
        self.assertEqual(phase['gate_minus_rtl']['end_cycle'],1)

    def test_missing_end_rejected(self):
        with self.assertRaisesRegex(ValueError,'Missing/ambiguous'):
            m.phase_bounds(self.frames[:-1],self.parent)

    def test_unknown_csr_rejected(self):
        rows = copy.deepcopy(self.frames)
        rows[-1][1]['writeback'] = 'x'
        with self.assertRaisesRegex(ValueError,'contains X'):
            m.phase_bounds(rows,self.parent)

    def test_critical_x_rejected(self):
        rows = copy.deepcopy(self.frames)
        rows[-2][1]['qbs_state'] = 'x'
        with self.assertRaisesRegex(ValueError,'Critical gate phase X'):
            m.audit_phase(rows,m.phase_bounds(rows,self.parent))

    def test_incomplete_commands_rejected(self):
        rows = [(tick,{k:v for k,v in change.items() if k != 'success'}) for tick,change in self.frames]
        with self.assertRaises(ValueError):
            m.audit_phase(rows,m.phase_bounds(rows,self.parent))

    def test_wrong_elf_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'bad.elf'
            p.write_bytes(bytes(256))
            with self.assertRaisesRegex(ValueError,'ELF64'):
                m.elf_pcs(p)

    def test_actual_frozen_elf_boundary_opcodes(self):
        p = m.OUT/'power_legacy_q8_successor_20261117_01/operator.elf'
        self.assertEqual(m.elf_pcs(p)['0x80001864'],'0xc00029f3')

    def test_status_replaces_only_mutable_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'status.json'
            m.update_status(p,dict(state='WAITING'))
            m.update_status(p,dict(state='AUDITING'))
            self.assertEqual(m.read(p)['state'],'AUDITING')
            self.assertFalse(p.with_suffix('.next').exists())


if __name__ == '__main__':
    unittest.main()
