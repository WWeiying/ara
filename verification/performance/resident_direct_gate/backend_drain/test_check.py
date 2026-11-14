"""Synthetic checker tests only; never classified as DUT execution evidence."""
import copy
import unittest

from check import audit, InvalidEvidence, InsufficientWindow
from fixture import CASES, fixture


def example():
    _, payload = fixture()
    golden = dict(cases=copy.deepcopy(CASES), expected={k: v.hex() for k, v in payload.items()})
    commit, vector, symbols = [], [], {}
    vector.append(dict(event='config', cycle=0, nr_lanes=4, vlen_bits=1024))
    for i, (name, case) in enumerate(CASES.items()):
        seq, base = i * 3, 100 + i * 100
        last = base + len(payload[name]) // 32
        response = base + 1 if case['early'] else last + 1
        arrival = response + 1
        csr_response = max(last + 1, arrival + 1)
        words = [case['insn'], (0xc20 << 20) | (2 << 12) | (case['csr_rd'] << 7) | 0x73,
                 (1 << 25) | (11 << 15) | ((case['eew'] + 4) << 12) | (case['vd'] << 7) | 0x27]
        for j, (suffix, start, finish) in enumerate((('issue', base, response),
                ('csr', arrival, csr_response), ('save', csr_response, csr_response + 1))):
            pc = 0x80000100 + i * 64 + j * 4
            symbols[name + '_' + suffix] = dict(pc=pc, insn=words[j])
            commit += [dict(event='arch_start', cycle=start, order=seq+j, trans_id=seq+j, insn=words[j]),
                       dict(event='cvx_req', cycle=finish, trans_id=seq+j, insn=words[j]),
                       dict(event='cvx_resp', cycle=finish, trans_id=seq+j, trap=0,
                            rd_wdata=case['vl'] if j == 1 else 0),
                       dict(event='retire', cycle=finish+2, order=seq+j, pc=pc, insn=words[j],
                            rd_wdata=case['vl'] if j == 1 else 0, trap=0)]
        meta = dict(arch_seq=seq, vid=0, insn=case['insn'], vd=case['vd'], eew=case['eew'],
                    vl=case['vl'], vstart=0, use_vd=1, nr_lanes=4, vlen_bits=1024)
        vector.append(dict(meta, event='alloc', cycle=base))
        for event, cycle in (('uop_alloc', base), ('uop_done', last + 1)):
            commit.append(dict(event=event, cycle=cycle, order=seq, port=0, trans_id=seq, insn=case['insn']))
        size = 1 << case['eew']
        # Forward interleave from logical bytes, independent of checker inverse.
        for word in range(len(payload[name]) // 32):
            lane_words = [bytearray(8) for _ in range(4)]
            for element in range(32 // size):
                lane, rank = element % 4, element // 4
                physical = ([0, 2, 1, 3][rank] if size == 2 else rank) * size
                source = word * 32 + element * size
                lane_words[lane][physical:physical+size] = payload[name][source:source+size]
            for lane in range(4):
                vector.append(dict(meta, event='write', cycle=base+word+1, lane=lane, source=4,
                                   addr=case['vd']*4+word, be=255,
                                   wdata=int.from_bytes(lane_words[lane], 'little')))
        vector.append(dict(meta, event='done', cycle=last+1))
    log = 'Core Test *** SUCCESS ***\nDRAIN_PAYLOAD_END\n'
    for name, raw in payload.items():
        log += (f'DRAIN_CHECK name={name} elements={len(raw)//(4 if name=="qk" else 2):08x} '
                f'checked={len(raw)+128:08x} mismatches=00000000 first=ffffffff actual=00 expected=00\n')
    for i, c in enumerate(CASES.values()):
        log += f'DRAIN_OBS index={i:02x} vl={c["vl"]:016x} fcsr=0000000000000001 vstart=0000000000000000\n'
    commit.sort(key=lambda r: r['cycle'])
    vector.sort(key=lambda r: r['cycle'])
    return commit, vector, log, golden, symbols


class CheckerTest(unittest.TestCase):
    def test_same_edge_completion_csr_and_save_allowed(self):
        result = audit(*example())
        self.assertEqual(result['state'], 'BACKEND_ONLY_CHECKED')
        self.assertEqual(result['cases']['row']['csr_response'], result['cases']['row']['backend_done'])
        self.assertEqual(result['cases']['row']['save_first_offer'], result['cases']['row']['csr_response'])

    def test_reject_corrupt_actual_evidence(self):
        for mutation in ('data', 'missing', 'duplicate', 'be', 'address', 'identity', 'late_write',
                         'csr_early', 'resident_early', 'save_early', 'done', 'pc', 'vl',
                         'guard', 'flags', 'trap', 'missing_retire'):
            with self.subTest(mutation=mutation):
                c, v, log, gold, sym = example()
                w = next(r for r in v if r['event'] == 'write')
                if mutation == 'data': w['wdata'] ^= 1
                elif mutation == 'missing': v.remove(w)
                elif mutation == 'duplicate': v.append(copy.deepcopy(w))
                elif mutation == 'be': w['be'] = 254
                elif mutation == 'address': w['addr'] = 0
                elif mutation == 'identity': w['arch_seq'] = 999
                elif mutation == 'late_write': w['cycle'] = 190
                elif mutation in ('csr_early', 'resident_early', 'save_early'):
                    seq = {'csr_early': 1, 'resident_early': 6, 'save_early': 2}[mutation]
                    event = 'arch_start' if mutation == 'save_early' else 'cvx_resp'
                    for r in c:
                        if r['event'] == event and r.get('trans_id') == seq:
                            r['cycle'] = 101 if mutation != 'resident_early' else 301
                elif mutation == 'done':
                    v[:] = [r for r in v if not (r['event'] == 'done' and r['arch_seq'] == 0)]
                elif mutation == 'pc': sym['row_issue']['pc'] += 4
                elif mutation == 'vl': gold['cases']['row']['vl'] = 64
                elif mutation == 'guard': log = log.replace('mismatches=00000000', 'mismatches=00000001', 1)
                elif mutation == 'flags': log = log.replace('fcsr=0000000000000001', 'fcsr=0000000000000000', 1)
                elif mutation == 'trap': log += 'DRAIN_TRAP mcause=0000000000000002\n'
                elif mutation == 'missing_retire':
                    c[:] = [r for r in c if not (r['event'] == 'retire' and r['pc'] == sym['pv_save']['pc'])]
                with self.assertRaises(InvalidEvidence):
                    audit(c, v, log, gold, sym)

    def test_arrival_not_handshake_and_missing_window_is_insufficient(self):
        for event in ('arch_start', 'cvx_resp'):
            with self.subTest(event=event):
                c, v, log, gold, sym = example()
                # CSR handshake remains after last write. Only its first offer proves waiting.
                tid = 1 if event == 'arch_start' else 0
                for r in c:
                    if r['event'] == event and r.get('trans_id') == tid:
                        r['cycle'] = 108
                if event == 'cvx_resp':
                    for r in c:
                        if r['event'] == 'arch_start' and r.get('trans_id') == 1:
                            r['cycle'] = 108
                with self.assertRaises(InsufficientWindow):
                    audit(c, v, log, gold, sym)


if __name__ == '__main__':
    unittest.main(verbosity=2)
