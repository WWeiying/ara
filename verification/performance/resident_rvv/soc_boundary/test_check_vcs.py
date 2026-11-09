"""Actual-RVFI-shaped synthetic fixtures, never invented fault retirements."""
import copy
import csv
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

import check_vcs as c


def monotone_orders(rows):
    order = 0
    for row in rows:
        if row['event'] == 'retire':
            row['order'] = str(order)
            order += 1


def fixture(vectors, contract, previous):
    with patch.object(previous, 'PC', contract['fault_pc']):
        numerical = previous.numerical(vectors)
    vector, _, probes = previous.work_fixture(vectors)
    ranks = {}
    for row in vector:
        if row['event'] == 'config':
            continue
        seq = int(row['arch_seq'])
        base = seq*2000 if seq <= 33 else (34 if seq == 100 else 35)*2000
        ranks[seq] = ranks.get(seq, 0)+1
        row['cycle'] = str(base+300+ranks[seq])
    commit, order = [], 0
    records = c.case_records(numerical)
    specs = c.cases.attempts(vectors['cases'])
    issue, trap = contract['issue'], contract['trap']

    def cpu(cycle, pc, insn, rd=0, value=0, event='retire', seq=0):
        nonlocal order
        row = dict.fromkeys(previous.CFIELDS, '0')
        row.update(cycle=str(cycle), event=event, order=str(order if event == 'retire' else seq),
            pc=f'{pc:016x}', insn=f'{insn:08x}', rd=str(rd), rd_wdata=f'{value:016x}')
        commit.append(row)
        if event == 'retire':
            order += 1

    def instruction(cycle, pc, rd=0, value=0):
        cpu(cycle, pc, contract['words'][pc], rd, value)

    for seq, (spec, record) in enumerate(zip(specs, records), 1):
        base = seq*2000
        if not spec['phase'] or not spec['rejection'] or spec['recovery_reloads_context']:
            cpu(base+1, 0x80000104, c.cases.FILL_INSN)
        if not spec['phase'] and spec['recovery_reloads_context']:
            cpu(base+2, 0x80000110, c.cases.RELEASE_INSN)
        instruction(base+5, issue)
        for n, (field, offset, _) in enumerate(c.ISSUE_READS[:5]):
            instruction(base+10+n, issue+offset, 6, record[field])
        off = spec['error'] and spec['kind'] in ('fs_off', 'vs_off')
        if not off:
            cpu(base+100, 0, spec['instruction'], event='arch_start', seq=seq)
        if spec['error']:
            path = list(range(trap, trap+0xbc, 4))
            if off:
                first = 0x40 if spec['kind'] == 'fs_off' else 0x4c
                path = [pc for pc in path if not trap+first <= pc < trap+0x6c]
            values = {trap+offset: (rd, record[field]) for field, offset, _, rd in c.TRAP_READS}
            values.update({trap+offset: (rd, value) for offset, rd, value in
                ((0x6c, 6, 2), (0x78, 28, contract['fault_pc'][str(spec['instruction'])]),
                 (0x80, 28, 1), (0x8c, 28, 0), (0x9c, 6, contract['resume']))})
            for i, pc in enumerate(path):
                instruction(base+900+i, pc, *values.get(pc, (0, 0)))
        else:
            instruction(base+900, contract['fault_pc'][str(c.cases.PV_INSN)])
        for n, (field, offset, _) in enumerate(c.ISSUE_READS[5:]):
            instruction(base+1200+n, issue+offset, 6, record[field])
        instruction(base+1210, issue+0x1a0, 10, spec['error'])
        instruction(base+1211, contract['issue_return'])
        if spec['phase']:
            cpu(base+1500, 0x80000110, c.cases.RELEASE_INSN)
    cpu(34*2000+1000, 0x80000900, c.cases.QBS_INSN)
    cpu(35*2000+1000, 0x80000904, c.cases.VADD_INSN)
    return vector, commit, numerical+'\n'+probes


class VcsBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Read the immutable fixture/ELF only; never regenerate or compile inputs.
        c.require(c.sha(c.BUILD/'build.json') == c.BUILD_SHA, 'Build02 receipt drift')
        receipt = json.loads((c.BUILD/'build.json').read_text())
        c.require(c.sha(receipt['elf']) == c.ELF_SHA, 'Build02 ELF drift')
        path = c.BUILD/'vectors/vectors.json'
        c.require(receipt['artifacts'][str(path)] == c.sha(path), 'Build02 vectors drift')
        cls.vectors = json.loads(path.read_text())
        cls.contract = c.elf_contract(Path(receipt['elf']).read_bytes())
        c.require(c.sha(c.HERE/'test_boundary.py') ==
            '98d2d5a1a96da0cb9e15ddf44c523fccc1bf7ed2bd7aaf93821da5bee2421a61', 'Sealed fixture helper drift')
        cls.previous = c.g.load(c.HERE/'test_boundary.py', 'boundary_previous_fixture_parts')

    def data(self):
        return fixture(self.vectors, self.contract, self.previous)

    def work(self, vector, commit, text):
        with tempfile.TemporaryDirectory() as temp:
            paths = []
            for name, fields, rows in (('vector.csv', self.previous.VFIELDS, vector),
                                       ('commit.csv', self.previous.CFIELDS, commit)):
                path = Path(temp)/name
                with path.open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
                paths.append(path)
            return c.check_work(*paths, text, self.vectors, self.contract)

    def test_real_elf_csr_pc_words_and_extents(self):
        d = self.contract
        self.assertEqual((d['trap']+0x1c, d['words'][d['trap']+0x1c]), (0x80000370, 0x34202373))
        self.assertEqual((d['trap']+0x24, d['words'][d['trap']+0x24]), (0x80000378, 0x341023f3))
        self.assertEqual((d['mret'], d['words'][d['mret']]), (0x8000040c, 0x30200073))
        self.assertEqual(d['fault_pc'], json.loads((c.BUILD/'build.json').read_text())['fault_pc'])

    def test_actual_21_success_retire_and_12_real_csr_traps(self):
        vector, commit, text = self.data()
        self.assertEqual(sum(r['event'] == 'retire' and c.pv(int(r['insn'], 16)) for r in commit), 21)
        self.assertFalse(any(r['event'] == 'retire' and r['trap'] == '1' for r in commit))
        c.old.check_log(text, self.vectors, self.contract['fault_pc'])
        work, architecture = self.work(vector, commit, text)
        self.assertEqual((work['admitted_pv'], work['maintenance_uops']), (24, 6))
        self.assertEqual((architecture['successful_pv_retirements'], architecture['real_csr_trap_groups'],
                          architecture['pv_arch_start'], architecture['faulting_pv_retirements']), (21, 12, 31, 0))
        self.assertEqual(sum(not x['csr_accessible'] for x in architecture['groups']), 2)
        self.assertEqual((architecture['actual_fill_retirements'], architecture['actual_release_retirements']), (22, 22))

    def test_missing_extra_mispc_wrong_csr_instruction_or_rd(self):
        for kind in ('missing', 'extra', 'pc', 'instruction', 'rd'):
            vector, commit, text = self.data()
            i = next(i for i, row in enumerate(commit) if int(row['pc'], 16) == self.contract['trap']+0x1c)
            if kind == 'missing':
                commit.pop(i)
            elif kind == 'extra':
                commit.insert(i, dict(commit[i]))
            else:
                field, value = {'pc': ('pc', '0000000080000374'),
                    'instruction': ('insn', '34102373'), 'rd': ('rd', '7')}[kind]
                commit[i][field] = value
            monotone_orders(commit)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.work(vector, commit, text)

    def test_cause_mepc_status_fcsr_vstart_and_counter_mutations(self):
        for offset in (0x1c, 0x24, 0x2c, 0x54, 0x5c, 0x78, 0x80, 0x8c, 0x9c):
            vector, commit, text = self.data()
            row = next(r for r in commit if int(r['pc'], 16) == self.contract['trap']+offset)
            row['rd_wdata'] = f'{int(row["rd_wdata"], 16)^1:016x}'
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.work(vector, commit, text)
        vector, commit, text = self.data()
        next(r for r in commit if int(r['pc'], 16) == self.contract['issue']+0x1a0)['rd_wdata'] = '0000000000000001'
        with self.assertRaises(ValueError):
            self.work(vector, commit, text)

    def test_unsafe_off_state_csr_capture_is_not_accepted(self):
        vector, commit, text = self.data()
        _, architecture = self.work(vector, commit, text)
        group = next(r for r in architecture['groups'] if not r['csr_accessible'])
        i = next(i for i, r in enumerate(commit) if int(r['cycle']) == group['last_cycle'])
        row = dict(commit[i], pc=f'{self.contract["trap"]+0x54:016x}', insn='00302e73', rd='28')
        commit.insert(i, row)
        monotone_orders(commit)
        with self.assertRaises(ValueError):
            self.work(vector, commit, text)

    def test_no_fake_fault_retire_and_no_missing_trap_group(self):
        for kind in ('fake_retire', 'remove_handler'):
            vector, commit, text = self.data()
            i = next(i for i, r in enumerate(commit) if int(r['pc'], 16) == self.contract['trap'])
            if kind == 'fake_retire':
                commit.insert(i, dict(commit[i], pc=f'{self.contract["fault_pc"][str(c.cases.PV_INSN)]:016x}',
                                      insn=f'{c.cases.PV_INSN:08x}', trap='1'))
            else:
                j = next(j for j in range(i, len(commit)) if int(commit[j]['pc'], 16) == self.contract['mret'])
                del commit[i:j+1]
            monotone_orders(commit)
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                self.work(vector, commit, text)

    def test_all_ten_nonoff_rejects_require_offer_and_off_rejects_forbid_offer(self):
        vector, commit, text = self.data()
        _, architecture = self.work(vector, commit, text)
        for group in architecture['groups']:
            v, rows = copy.deepcopy(vector), copy.deepcopy(commit)
            if group['arch_seq'] is None:
                i = next(i for i, row in enumerate(rows) if int(row['cycle']) == group['first_cycle'])
                rows.insert(i, dict(rows[i], event='arch_start', order='999', insn=f'{c.cases.PV_INSN:08x}'))
            else:
                rows = [row for row in rows if not (row['event'] == 'arch_start' and int(row['order']) == group['arch_seq'])]
            with self.subTest(id=group['id']), self.assertRaises(ValueError):
                self.work(v, rows, text)

    def test_context_reload_or_release_between_bad_and_good_rejected(self):
        for insn in (c.cases.FILL_INSN, c.cases.RELEASE_INSN, 0x02a0605b):
            vector, commit, text = self.data()
            index = next(i for i, row in enumerate(commit) if int(row['pc'], 16) == self.contract['mret'])
            end = next(i for i in range(index, len(commit)) if int(commit[i]['pc'], 16) == self.contract['issue_return'])
            added = dict(commit[end], cycle=str(int(commit[end]['cycle'])+1), pc='0000000080000104', insn=f'{insn:08x}')
            commit.insert(end+1, added)
            monotone_orders(commit)
            with self.subTest(insn=insn), self.assertRaises(ValueError):
                self.work(vector, commit, text)

    def test_raw_view_six_maintenance_and_final_geometry_unchanged(self):
        for field, value in (('vd', '14'), ('vl', '256'), ('source', '4'), ('wdata', '0000000000000000')):
            vector, commit, text = self.data()
            row = next(r for r in vector if r['event'] == 'write' and r['source'] == '3')
            row[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.work(vector, commit, text)
        vector, commit, text = self.data()
        next(r for r in vector if r['event'] == 'alloc' and c.pv(int(r['insn'], 16)))['insn'] = '0495705b'
        with self.assertRaises(ValueError):
            self.work(vector, commit, text)

    def test_backend_reject_source_drain_and_no_write_are_required(self):
        vector, commit, text = self.data()
        for bad in (text.replace('source_words=96', 'source_words=95'),
                    text.replace('row_reads=0', 'row_reads=1')):
            with self.assertRaises(ValueError):
                self.work(vector, commit, bad)
        _, architecture = self.work(vector, commit, text)
        bad = next(x['arch_seq'] for x in architecture['groups'] if x['id'] == 12)
        i = next(i for i, r in enumerate(vector) if int(r['arch_seq']) == bad and r['event'] == 'alloc')
        vector.insert(i+1, dict(vector[i], event='write', source='4', be='ff'))
        with self.assertRaises(ValueError):
            self.work(vector, commit, text)

    def test_elf_csr_word_mutation_and_build_selection_fail_closed(self):
        receipt = json.loads((c.BUILD/'build.json').read_text())
        raw = bytearray(Path(receipt['elf']).read_bytes())
        pattern = bytes.fromhex('73232034')  # 34202373, little endian.
        position = raw.find(pattern)
        self.assertGreaterEqual(position, 0)
        raw[position] ^= 1
        with self.assertRaises(ValueError):
            c.elf_contract(raw)
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(ValueError):
                c.verified_build(Path(temp))

    def test_cli_single_json_with_real_build_pins_and_input_hashes(self):
        vector, commit, text = self.data()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            log = root/'log.txt'
            log.write_text(text)
            for name, fields, rows in (('vector.csv', self.previous.VFIELDS, vector),
                                       ('commit.csv', self.previous.CFIELDS, commit)):
                with (root/name).open('w', newline='') as stream:
                    writer = csv.DictWriter(stream, fieldnames=fields)
                    writer.writeheader()
                    writer.writerows(rows)
            proc = subprocess.run([c.sys.executable, '-B', str(c.HERE/'check_vcs.py'),
                '--build', str(c.BUILD), '--log', str(log), '--vector', str(root/'vector.csv'),
                '--commit', str(root/'commit.csv')], text=True, capture_output=True, timeout=120)
            self.assertEqual(proc.returncode, 0, proc.stderr[-3000:])
            answer = json.loads(proc.stdout)
            self.assertFalse(answer['protocol_checked'])
            self.assertEqual(answer['trap_architecture']['real_csr_trap_groups'], 12)
            self.assertEqual(answer['work']['maintenance_uops'], 6)
            for path in (log, root/'vector.csv', root/'commit.csv'):
                self.assertEqual(answer['evidence_sha256'][str(path)], c.sha(path))


if __name__ == '__main__':
    unittest.main()
