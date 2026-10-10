"""Synthetic checker fixtures only; never launch a simulator."""
import csv
from io import BytesIO
from pathlib import Path
import shutil
import tempfile
import unittest

import run_masklogical_restart8 as r
from ara_verify.vector_commit import _deshuffle_byte


class RunnerAuditTests(unittest.TestCase):
    def fixture(self, out, defect=''):
        shutil.copyfile(r.PRE / 'input.elf', out / 'input.elf')
        elf = r.reference.ELFFile(BytesIO((out / 'input.elf').read_bytes()))
        symbols = elf.get_section_by_name('.symtab')
        base = symbols.get_symbol_by_name('restart8_got')[0]['st_value']
        eoc = symbols.get_symbol_by_name('_eoc')[0]['st_value']
        log = r.reference.PASS_LINE + '\nCore Test *** SUCCESS\n' + (
            '[ARA_CONTRACT] requests=8 responses=8 exceptions=0 mmu_request_cycles=0 '
            'protocol_errors=0 outstanding=0 req_stalled=0 resp_stalled=0\n'
            '$finish called from file\nV C S   S i m u l a t i o n   R e p o r t\n')
        for name in ('console.log', 'run.vcs.log'):
            (out / name).write_text(log)
        rows, vector = [], ['cycle,event,arch_seq,vid,lane,source,insn,use_vd,vd,eew,vl,vstart,addr,be,wdata,nr_lanes,vlen_bits',
                           '0,config,0,0,0,0,00000000,0,0,0,0,0,0,00,0,4,1024']
        order = 0
        def row(event, pc, word, **extra):
            return dict(event=event, order=order, pc=f'{pc:x}', insn=f'{word:08x}', trap='0',
                        **dict(dict(mem_rmask='0', mem_wmask='0', mem_addr='0', mem_wdata='0',
                                    rd_wdata='0'), **extra))
        for op, site in enumerate(r.reference.elf_sites(out / 'input.elf')):
            # Real arch_start uses its own sequence, not the retire order, and
            # has a zero PC placeholder (ara_commit_monitor.sv).
            seq = 99 + 3 * op
            if not (defect == 'missing_start' and op == 7):
                start = row('arch_start', 0, site['word'])
                start['order'] = seq
                if defect == 'wrong_start_word' and op == 7:
                    start['insn'] = f'{site["word"] ^ (1 << 15):08x}'
                if defect == 'wrong_start_seq' and op == 7:
                    start['order'] = seq + 1
                if defect == 'duplicate_seq' and op == 7:
                    start['order'] = 99
                rows.append(start)
            pc = 0 if defect == 'wrong_retire_pc' and op == 7 else site['pc']
            rows.append(row('retire', pc, site['word'])); order += 1
            want = r.reference.expected(op)
            vector.append(f'0,alloc,{seq},0,0,0,{site["word"]:08x},1,{site["vd"]},0,1024,256,0,00,0,4,1024')
            for word in range(4):
                for lane in range(4):
                    if defect == 'missing_word' and op == 7 and word == 3:
                        continue
                    data = [want[8 + word * 32 + _deshuffle_byte(lane * 8 + b, 4, 0)] for b in range(8)]
                    if defect == 'bad_vrf' and op == 0 and word == lane == 0:
                        data[0] ^= 1
                    value = int.from_bytes(bytes(data), 'little')
                    vector.append(f'1,write,{seq},0,{lane},2,{site["word"]:08x},1,{site["vd"]},0,1024,256,{site["vd"]*4+word},ff,{value:016x},4,1024')
            if not (defect == 'missing_done' and op == 7):
                vector.append(f'2,done,{seq},0,0,0,{site["word"]:08x},1,{site["vd"]},0,1024,256,0,00,0,4,1024')
            for byte, value in enumerate(want):
                rows.append(row('retire', 0x80010000, 0x00004503, mem_rmask='1',
                                mem_addr=f'{base+op*144+byte:x}', rd_wdata=f'{value:x}'))
                order += 1
        for i in range(3):
            extras = dict(mem_wmask='ff', mem_addr='d0000000',
                          mem_wdata='1' if defect == 'bad_exit' else '0') if i == 2 else {}
            rows.append(row('retire', eoc + 4*i, 0x13, **extras)); order += 1
        with (out / 'commit_trace.csv').open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader(); writer.writerows(rows)
        (out / 'vector_trace.csv').write_text('\n'.join(vector) + '\n')

    def test_complete_fixture(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp); self.fixture(out)
            self.assertEqual(r.audit(out)['vrf_bytes'], 1024)

    def test_incomplete_or_wrong_evidence_rejected(self):
        for defect in ('missing_start', 'missing_done', 'missing_word', 'bad_vrf', 'bad_exit',
                       'wrong_start_word', 'wrong_start_seq', 'duplicate_seq', 'wrong_retire_pc'):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as tmp:
                out = Path(tmp); self.fixture(out, defect)
                with self.assertRaises(ValueError):
                    r.audit(out)


if __name__ == '__main__':
    unittest.main()
