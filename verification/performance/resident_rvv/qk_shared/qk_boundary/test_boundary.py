#!/usr/bin/env python3
"""Host contracts/mutations, optionally bound to the newly built real ELF."""
import argparse
import copy
import csv
import json
from pathlib import Path
import tempfile
import unittest

import cases
import check
import elf
import generate as g
import run

BUILD = None


def synthetic_contract():
    c = dict(symbols={}, words={})
    def symbol(name, address, size=0):
        c['symbols'][name] = dict(address=address, size=size, type=2 if size else 0)
    symbol('qk_issue', 0x80001000, 0x304)
    for i, field in enumerate(check.READS):
        symbol('qk_read_' + field, 0x80001020 + i * 8)
        c['words'][elf.pc(c, 'qk_read_' + field)] = check.CSRS[field] << 20 | 6 << 7 | 0x2073
    for i, (name, word) in enumerate(cases.WORDS.items()):
        symbol(name, 0x80001100 + 8 * i); c['words'][elf.pc(c, name)] = word
    symbol('qk_resume', 0x80001120)
    symbol('qk_read_traps', 0x800012e0)
    symbol('qk_issue_return', 0x80001300)
    symbol('boundary_trap', 0x80002000, 0xd0)
    symbol('akv_experimental_resident_qk', 0x80003000, 16)
    symbol('qk_helper_fcsr_pc', 0x80004000)
    symbol('qk_pv_pc', 0x80005000)
    for p in (elf.pc(c, 'qk_issue'), elf.pc(c, 'qk_read_traps'), elf.pc(c, 'qk_issue_return'),
              *range(0x80002000, 0x800020d0, 4), *range(0x80003000, 0x80003010, 4)):
        c['words'].setdefault(p, 0x13)
    for _, off, csr, rd in check.TRAP:
        c['words'][0x80002000 + off] = csr << 20 | rd << 7 | 0x2073
    c['words'][0x800020b8] = 0x30200073
    c['words'][0x80003004] = cases.QK
    c['words'][0x80004000] = 0x00302573
    c['words'][0x80005000] = cases.PV
    return c


def fixture(v, c):
    text = ['QK_BOUNDARY_BEGIN cases=23 vlenb=128 data=' + v['data_identity_sha256']]
    records, specs = [], cases.attempts(v['cases'])
    for s in specs:
        off = s['error'] and s['kind'] in ('fs_off', 'vs_off')
        rm = 5 if s['error'] and s['kind'] == 'frm' else s['rm']
        start = int(s['error'] and s['kind'] == 'vstart')
        before = rm << 5 | s['initial_flags']
        pc = next(elf.pc(c, n) for n, w in cases.WORDS.items() if w == s['instruction'])
        status = 0x680 if off and s['kind'] == 'fs_off' else 0x6080 if off else 0x6680
        r = dict(id=s['id'], phase=s['phase'], d=s['dimension'], heads=s['heads'], tokens=s['tokens'],
                 base=s['query_base'], rm=s['rm'], before_fcsr=before, before_vstart=start,
                 after_fcsr=before if s['error'] else s['expected_fcsr'], after_vstart=start,
                 traps=s['error'], cause=2 if s['error'] else 0, pc=pc if s['error'] else 0, mtval=0,
                 trap_fcsr=before if s['error'] and not off else 0, trap_vstart=start if not off else 0,
                 unexpected=0, guard_errors=0, before_mstatus=status, after_mstatus=status,
                 trap_mstatus=(status & ~0x80) | 0x1800 if s['error'] else 0,
                 before_vl=0 if s['mode'] in (1, 2) else 128,
                 before_vtype=0xc0 if s['mode'] == 1 else 1 << 63 if s['mode'] == 2 else 0xd2,
                 trap_csrs_valid=int(s['error'] and not off))
        r.update(after_vl=r['before_vl'], after_vtype=r['before_vtype'])
        records.append(r)
        if s['id'] == 0:
            text.append('QK_BOUNDARY_PV id=0 fcsr=0 bits=' + '3e00' * 64)
        text.append('QK_BOUNDARY_CASE ' + ' '.join(k + '=' + (f'{r[k]:016x}' if k in check.HEX else str(r[k])) for k in check.FIELDS))
        data = v['destination_pattern'] if s['error'] else s['expected']
        text.append(f'QK_BOUNDARY_DATA id={s["id"]} phase={s["phase"]} kind=' +
                    ('dest32' if s['error'] else 'result') + ' bits=' + ''.join(f'{x:08x}' for x in data))
        if s['id'] == 0:
            text.append('QK_BOUNDARY_HELPER id=0 fcsr=' + str(s['qk_flags']) + ' guard_errors=0 bits=' +
                        ''.join(f'{x:08x}' for x in s['expected']))
            text.append('QK_BOUNDARY_PV id=1 fcsr=0 bits=' + '3e00' * 64)
    text.append('PV_BOUNDARY_COMPAT qbs_fcsr=0 rvv_fcsr=0 qbs=' +
                ''.join(f'{x:08x}' for x in [0x43800000, 0x44000000, 0x44400000] + [0] * 29) +
                ' rvv=' + ''.join(f'{0x10203041 + 3 * i:08x}' for i in range(32)))
    text.append('QK_BOUNDARY_DONE cases=23 successes=24 rejected=12 helper=1 pv=2 compat=1 errors=0')
    return '\n'.join(text) + '\n', specs, records


def cpu_rows(v, specs, records, c):
    result, cycle, order, arch = [], 0, 0, 0
    def row(pc, word=None, value=0, rd=None, event='retire'):
        nonlocal cycle, order, arch
        cycle += 10
        word = c['words'].get(pc, 0x13) if word is None else word
        result.append(dict(cycle=str(cycle), event=event, order=str(order if event == 'retire' else arch),
             port='0', trans_id='0', pc=f'{pc:016x}', insn=f'{word:08x}',
             rd=str((word >> 7) & 31 if rd is None else rd), rd_wdata=f'{value:016x}',
             mem_addr='0', mem_rmask='00', mem_wmask='00', mem_wdata='0', trap='0'))
        if event == 'retire': order += 1
        else: arch += 1
    def context(word): row(0x70000000, word)
    def pv():
        row(elf.pc(c, 'qk_pv_pc'), cases.PV, event='arch_start')
        row(elf.pc(c, 'qk_pv_pc'), cases.PV)
    index = 0
    for original in v['cases']:
        context(cases.FILL)
        if original['id'] == 0: pv()
        if original['kind'] == 'no_context': context(cases.RELEASE)
        for _ in range(2 if original['rejection'] else 1):
            s, record = specs[index], records[index]; index += 1
            row(elf.pc(c, 'qk_issue'))
            for field in check.READS[:5]: row(elf.pc(c, 'qk_read_' + field), value=record[field], rd=6)
            off = s['error'] and s['kind'] in ('fs_off', 'vs_off')
            fault = next(elf.pc(c, n) for n, w in cases.WORDS.items() if w == s['instruction'])
            if not off: row(fault, s['instruction'], event='arch_start')
            if s['error']:
                trap = elf.pc(c, 'boundary_trap')
                values = {trap + offset: (record[field], rd) for field, offset, _, rd in check.TRAP}
                values.update({trap + off: (value, rd) for off, rd, value in
                    ((0x6c, 6, 2), (0x78, 28, fault), (0x80, 28, 1),
                     (0x8c, 28, 0), (0x9c, 6, elf.pc(c, 'qk_resume')))})
                for pc in range(trap, trap + 0xbc, 4):
                    first = 0x40 if s['kind'] == 'fs_off' else 0x4c
                    if off and trap + first <= pc < trap + 0x6c: continue
                    value, rd = values.get(pc, (0, (c['words'][pc] >> 7) & 31))
                    row(pc, value=value, rd=rd)
            else: row(fault, s['instruction'])
            for field in check.READS[5:]: row(elf.pc(c, 'qk_read_' + field), value=record[field], rd=6)
            row(elf.pc(c, 'qk_read_traps'), value=s['error'], rd=10)
            row(elf.pc(c, 'qk_issue_return'))
            if original['kind'] == 'no_context' and s['error']: context(cases.FILL)
        if original['id'] == 0:
            lo, hi = elf.extent(c, 'akv_experimental_resident_qk')
            row(lo)
            qpc = next(pc for pc in range(lo, hi, 4) if c['words'][pc] == cases.QK)
            row(qpc, cases.QK, event='arch_start'); row(qpc, cases.QK); row(hi - 4)
            row(elf.pc(c, 'qk_helper_fcsr_pc'), value=specs[0]['qk_flags'], rd=10)
            pv()
        context(cases.RELEASE)
    context(cases.QBS); context(cases.VADD)
    return result


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def uop(spec, seq=1, begin=10, vd=0, vl=128, eew=2, source=4, data=None, vid=0):
    data = cases.writes(spec) if data is None else data
    rows = []
    for event, cycle, lane, addr, mask, value in [
        ('alloc', begin, 0, 0, 0, 0),
        *[('write', begin + 1 + i // 4, lane, addr, be, value)
          for i, ((lane, addr), (value, be)) in enumerate(data.items())],
        ('done', begin + 2 + (len(data) + 3) // 4, 0, 0, 0, 0)]:
        rows.append(dict(cycle=str(cycle), event=event, arch_seq=str(seq), vid=str(vid), lane=str(lane),
             source=str(source), insn=f'{spec["instruction"]:08x}', use_vd='1', vd=str(vd), eew=str(eew),
             vl=str(vl), vstart='0', addr=str(addr), be=f'{mask:02x}', wdata=f'{value:016x}', nr_lanes='4', vlen_bits='1024'))
    return rows


class Boundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        g.verify(g.ANCHORS)
        ref = g.load(g.REFERENCE, 'qk_arch_host_reference').OrderedReference(g.LIB)
        rows = g.construct(ref, g.raw16(g.DATA / 'decode_query_f16.bin'), g.raw16(g.DATA / 'decode_key.bin'))
        cls.v = dict(schema=cases.SCHEMA, cases=rows, destination_pattern=cases.destination(), data_identity_sha256='abc123')
        cls.c = elf.contract((BUILD / 'resident_qk_boundary.elf').read_bytes()) if BUILD else synthetic_contract()
        cls.text, cls.specs, cls.records = fixture(cls.v, cls.c)
        cls.cpu = cpu_rows(cls.v, cls.specs, cls.records, cls.c)

    def architecture(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'commit.csv'; write_csv(p, rows)
            return check.architecture(p, self.specs, self.records, self.c)

    def test_plan(self):
        self.assertEqual(len(self.v['cases']), 23); self.assertEqual(len(self.specs), 35)
        self.assertEqual(sum(s['error'] for s in self.specs), 12)
        normal = self.v['cases'][:6]
        self.assertEqual({s['tokens'] for s in normal}, {1, 2, 3, 9, 17, 64})
        self.assertEqual({s['dimension'] for s in normal}, {64, 96, 128})
        self.assertEqual({s['rm'] for s in normal}, set(range(5)))

    def test_control(self):
        self.assertEqual(cases.control(128, 2, 64, 6), 63 | 64 | 128 | 6 << 9)
        for args in ((32, 1, 1, 0), (64, 3, 1, 0), (64, 1, 0, 0), (64, 1, 65, 0), (64, 1, 1, 8)):
            with self.assertRaises(ValueError): cases.control(*args)

    def test_dynamic_query_bounds_not_abi_reject(self):
        s = next(s for s in self.v['cases'] if s['kind'] == 'query_bounds')
        self.assertEqual(s['rejection'], 'backend')
        self.assertEqual(s['context_queries'], 7)
        self.assertEqual(s['bad_control'], s['control'])
        bad_base = (s['bad_control'] >> 9) & 7
        self.assertEqual(bad_base + s['heads'], 8)
        self.assertGreater(bad_base + s['heads'], s['context_queries'])
        self.assertEqual(s['recovery']['query_base'] + s['recovery']['heads'], 7)
        for row in self.v['cases']:
            if row['rejection'] == 'backend':
                command = row['bad_control']
                self.assertEqual(command >> 12, 0)
                self.assertNotEqual((command >> 7) & 3, 3)
                self.assertLessEqual(((command >> 9) & 7) + 1 + ((command >> 6) & 1), 8)

    def test_independent_special_flags(self):
        v = {s['kind']: s for s in self.v['cases']}
        self.assertEqual(v['snan']['qk_flags'], 16)
        self.assertEqual(v['qnan']['qk_flags'], 0)
        self.assertEqual(v['poison_subnormal']['qk_flags'], 0)
        self.assertEqual(v['rounding']['qk_flags'], 1)

    def test_numerical(self): check.numerical(self.text, self.v, self.c)

    def test_bad_raw_output(self):
        text = self.text.replace('kind=result bits=', 'kind=result bits=ffffffff', 1)
        with self.assertRaises(ValueError): check.numerical(text, self.v, self.c)

    def test_missing_nx(self):
        s = next(s for s in self.specs if s['kind'] == 'rounding')
        text = self.text.replace('after_fcsr=' + str(s['expected_fcsr']) + ' ',
                                 'after_fcsr=' + str(s['expected_fcsr'] & ~1) + ' ')
        with self.assertRaises(ValueError): check.numerical(text, self.v, self.c)

    def test_fs_off_mutation(self):
        with self.assertRaises(ValueError):
            check.numerical(self.text.replace('before_mstatus=0000000000000680', 'before_mstatus=0000000000006680'), self.v, self.c)

    def test_duplicate_terminal(self):
        with self.assertRaises(ValueError): check.numerical(self.text + self.text.splitlines()[-1] + '\n', self.v, self.c)

    def test_actual_retire_convention(self):
        trace = self.architecture(self.cpu)
        self.assertEqual(len(trace['qk']), 36); self.assertEqual(len(trace['pv']), 2)
        self.assertEqual(sum(w['spec']['error'] for w in trace['qk']), 12)

    def test_missing_trap_csr(self):
        pc = elf.pc(self.c, 'boundary_trap') + 0x1c
        rows = copy.deepcopy(self.cpu)
        rows.pop(next(i for i, r in enumerate(rows) if int(r['pc'], 16) == pc))
        with self.assertRaises(ValueError): self.architecture(rows)

    def test_wrong_trap_pc(self):
        rows = copy.deepcopy(self.cpu); pc = elf.pc(self.c, 'boundary_trap') + 0x24
        next(r for r in rows if int(r['pc'], 16) == pc)['rd_wdata'] = '000000008000ffff'
        with self.assertRaises(ValueError): self.architecture(rows)

    def test_wrong_resume(self):
        rows = copy.deepcopy(self.cpu); pc = elf.pc(self.c, 'boundary_trap') + 0x9c
        next(r for r in rows if int(r['pc'], 16) == pc)['rd_wdata'] = '0000000000000000'
        with self.assertRaises(ValueError): self.architecture(rows)

    def test_extra_request(self):
        rows = copy.deepcopy(self.cpu)
        i = next(i for i, r in enumerate(rows) if r['event'] == 'arch_start' and check.qk(int(r['insn'], 16)))
        rows.insert(i, dict(rows[i]))
        with self.assertRaises(ValueError): self.architecture(rows)

    def test_fake_fault_retire(self):
        rows = copy.deepcopy(self.cpu)
        pc = elf.pc(self.c, 'boundary_trap')
        i = next(i for i, r in enumerate(rows) if int(r['pc'], 16) == pc)
        rows.insert(i, dict(rows[i], pc=f'{elf.pc(self.c,"qk_fault_pc"):016x}', insn=f'{cases.QK:08x}'))
        order = 0
        for r in rows:
            if r['event'] == 'retire': r['order'] = str(order); order += 1
        with self.assertRaises(ValueError): self.architecture(rows)

    def test_missing_helper_fcsr(self):
        rows = [r for r in self.cpu if int(r['pc'], 16) != elf.pc(self.c, 'qk_helper_fcsr_pc')]
        with self.assertRaises(ValueError): self.architecture(rows)

    def test_extra_context_reload(self):
        rows = copy.deepcopy(self.cpu)
        rows[0]['insn'] = f'{cases.RELEASE:08x}'
        with self.assertRaises(ValueError): self.architecture(rows)

    def test_nonmonotone(self):
        rows = copy.deepcopy(self.cpu); rows[4]['cycle'] = '0'
        with self.assertRaises(ValueError): self.architecture(rows)

    def test_partial_geometry(self):
        s = self.specs[0]
        self.assertEqual(cases.geometry(s)['active'], 1)
        self.assertEqual(cases.geometry(s)['result_words'], 1)
        self.assertEqual(cases.writes(s), {(0, 0): (s['expected'][0], 15)})
        self.assertEqual(cases.geometry(self.v['cases'][4])['result_words'], 18)

    def test_masked_write(self):
        rows = uop(self.specs[0]); check.audit_uop(rows, 0, 128, 2, cases.writes(self.specs[0]))
        rows[1]['wdata'] = f'{(0xdeadbeef << 32) | self.specs[0]["expected"][0]:016x}'
        check.audit_uop(rows, 0, 128, 2, cases.writes(self.specs[0]))
        rows[1]['be'] = 'ff'
        with self.assertRaises(ValueError): check.audit_uop(rows, 0, 128, 2, cases.writes(self.specs[0]))

    def test_write_wrong_value(self):
        rows = uop(self.specs[0]); rows[1]['wdata'] = '0000000000000000'
        with self.assertRaises(ValueError): check.audit_uop(rows, 0, 128, 2, cases.writes(self.specs[0]))

    def test_duplicate_write(self):
        rows = uop(self.specs[0]); rows.insert(2, dict(rows[1]))
        with self.assertRaises(ValueError): check.audit_uop(rows, 0, 128, 2, cases.writes(self.specs[0]))

    def test_rejected_no_writes(self):
        s = next(s for s in self.specs if s['error'] and s['rejection'] == 'backend')
        rows = uop(s, data={}); check.audit_uop(rows, 0, 128, 2, {})
        rows.insert(1, dict(rows[0], event='write', source='4', be='0f'))
        with self.assertRaises(ValueError): check.audit_uop(rows, 0, 128, 2, {})

    def test_runner_recipe(self):
        out = g.OUT / 'test_qk_not_created'
        recipes = run.recipes(out, dict(simv='/frozen/simv'), dict(elf='/frozen/test.elf'), Path('/frozen/build'))
        self.assertIn('+RESIDENT_PV_PERF', recipes['simulation'])
        self.assertIn('+RESIDENT_PV_WATCHDOG', recipes['simulation'])
        self.assertIn('--require-axi-write', recipes['protocol'])
        self.assertNotIn('-R', recipes['simulation'])

    def test_runner_failures(self):
        self.assertFalse(run.re_failure('UVM_ERROR : 0\nUVM_FATAL : 0\nCore Test *** SUCCESS ***\n'))
        for text in ('UVM_ERROR : 1\n', 'UVM_ERROR @ 42: bad\n', 'Fatal: bad\n', 'Core Test *** FAILED ***\n'):
            self.assertTrue(run.re_failure(text))

    def test_parent_helper_and_trap_identity(self):
        import build
        g.verify(build.EXTERNAL)
        self.assertEqual(elf.pc(self.c, 'qk_helper_fcsr_pc') in self.c['words'], True)

    def full_work(self):
        trace = self.architecture(self.cpu)
        rows, probes = [], []
        index = 0
        for w in trace['qk']:
            s = w['spec']
            if s['error'] and s['rejection'] == 'frontend': continue
            index += 1
            vd = 28 if s['instruction'] == cases.WORDS['qk_rd28_pc'] else 0
            rows += uop(s, seq=w['arch_seq'], begin=w['offer_cycle'], vd=vd,
                         data={} if s['error'] else cases.writes(s), vid=index % 8)
            p = cases.geometry(s)
            if s['error']:
                for k in ('seed_words', 'coefficients', 'value_words', 'result_words', 'final_acks', 'query_reads', 'columns'):
                    p[k] = 0
            p.update(vid=index % 8, dimensions=s['dimension'], tokens=s['tokens'], heads=s['heads'],
                     query_base=s['query_base'], cycles=20, error=s['error'], flags=0 if s['error'] else s['qk_flags'])
            probes.append((w['end'], 'QK', p))
        for w in trace['pv']:
            rows += uop(dict(instruction=cases.PV), seq=w['arch_seq'], begin=w['begin'], vd=0, vl=256, eew=1,
                         data={(l, x): (0x3e003e003e003e00, 255) for l in range(4) for x in range(4)}, vid=6)
            probes.append((w['end'], 'PV', dict(vid=6, control=0, tokens=1, words=4, heads=1, cycles=10,
                          error=0, flags=0, source_words=96, seed_words=16, coefficients=4, value_words=16,
                          result_words=16, final_acks=16, row_reads=4)))
        start = max(int(r['cycle']) for r in rows) + 10
        values = [0x43800000, 0x44000000, 0x44400000] + [0] * 29
        rows += uop(dict(instruction=cases.QBS), seq=1000, begin=start, vd=8, vl=32, eew=2,
            data={(l, 32 + x): (values[8*x+l] | values[8*x+l+4] << 32, 255) for l in range(4) for x in range(4)})
        rows += uop(dict(instruction=cases.VADD), seq=1001, begin=start+20, vd=16, vl=32, eew=2, source=0,
            data={(l, 64 + x): ((0x10203041+3*(8*x+l)) | (0x10203041+3*(8*x+l+4)) << 32, 255)
                  for l in range(4) for x in range(4)})
        rows.sort(key=lambda r: int(r['cycle']))
        rows.insert(0, dict(rows[0], event='config', cycle='0', insn='00000000'))
        text = []
        for i, (_, mode, p) in enumerate(sorted(probes, key=lambda x: x[0])):
            p['seq'] = i
            text.append('[RESIDENT_' + mode + '_PERF] ' + ' '.join(
                k + '=' + (format(v, '04b') if k == 'active' else str(v)) for k, v in p.items()))
        return rows, '\n'.join(text), trace

    def test_full_work_probes_and_tail_data(self):
        rows, text, trace = self.full_work()
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'vector.csv'; write_csv(p, rows)
            self.assertEqual(check.work(p, text, trace)['admitted_qk'], 28)

    def test_pv_undrained_rejected(self):
        rows, text, trace = self.full_work()
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'vector.csv'; write_csv(p, rows)
            with self.assertRaises(ValueError): check.work(p, text.replace('source_words=96', 'source_words=95', 1), trace)

    def test_probe_flags_mutation(self):
        rows, text, trace = self.full_work()
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'vector.csv'; write_csv(p, rows)
            with self.assertRaises(ValueError): check.work(p, text.replace('flags=0', 'flags=16', 1), trace)

    def test_actual_exception_scope(self):
        from types import SimpleNamespace
        expected = []
        for s in self.specs:
            if not (s['error'] and s['kind'] in ('fs_off', 'vs_off')):
                expected.append((s['instruction'], s['error']))
            if s['id'] == 0: expected.append((cases.QK, 0))
        events = []
        for i, (word, error) in enumerate(expected):
            events += [(2*i, 1, 0, word, 0, 0, 0), (2*i+1, 0, 0, 0, 1, 0, error)]
        uvm = SimpleNamespace(_CONTRACT_EVENT=None, _events=lambda *args: (events, []))
        proof = dict(contract_counts=dict(exceptions=10))
        self.assertEqual(run.scoped_exceptions('', self.v, proof, uvm)['qk_requests'], 34)
        events[-1] = (*events[-1][:-1], 1)
        with self.assertRaises(ValueError): run.scoped_exceptions('', self.v, proof, uvm)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--build', type=Path)
    args, rest = parser.parse_known_args()
    BUILD = args.build
    unittest.main(argv=[__file__, *rest])
