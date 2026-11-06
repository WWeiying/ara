"""Fail-closed scope tests, without simulation or existing evidence mutation."""
import copy
import unittest

import collect_rms_norm_scoped as target


def protocol():
    return dict(status='FAIL', issues=[target.ISSUE],
                contract_counts=dict(protocol_errors=0, requests=1974, responses=1974, outstanding=0),
                backend_counts=dict(allocations=937, completions=937, aborted=0),
                axi_read_counts=dict(ar=313, completed=313, r_beats=7838, pending=0, aborted=0),
                axi_write_counts=dict(aw=0, b=0, w_beats=0, matched=0, pending=0),
                elf_sha256='unchanged', log_sha256='unchanged', sim_image_sha256={'image': 'same'})


def disassembly():
    return '\n'.join(f'{0x1000+i*4:016x} <{name}>:\n'
                     f' {0x1000+i*4:x}: fefb2e27 fsw fa5,-4(s6)'
                     for i, name in enumerate(target.FUNCTIONS))


def trace():
    lines = ['cycle,event,insn,nr_lanes,vlen_bits', '0,config,00000000,4,1024']
    lines.extend(f'{i},alloc,92421257,4,1024' for i in range(649))
    lines.extend(f'{i+649},alloc,020ce207,4,1024' for i in range(288))
    return '\n'.join(lines)+'\n'


class ScopeTests(unittest.TestCase):
    def test_only_exact_original_issue_is_eligible(self):
        target.original_protocol_scope(protocol())
        for issue in ([], [target.ISSUE, 'another failure'], ['another failure']):
            value = protocol()
            value['issues'] = issue
            with self.assertRaises(ValueError):
                target.original_protocol_scope(value)

    def test_protocol_error_missing_work_or_nonzero_writes_rejected(self):
        for group, key, value in (('contract_counts', 'protocol_errors', 1),
                                  ('contract_counts', 'responses', 1973),
                                  ('backend_counts', 'completions', 936),
                                  ('axi_read_counts', 'r_beats', 7837),
                                  ('axi_read_counts', 'pending', 1),
                                  ('axi_write_counts', 'aw', 1)):
            old = protocol()
            old[group][key] = value
            with self.subTest(group=group, key=key), self.assertRaises(ValueError):
                target.original_protocol_scope(old)

    def test_scoped_result_must_preserve_every_other_field(self):
        old = protocol()
        new = copy.deepcopy(old)
        new.update(status='PASS', issues=[])
        target.compare_protocol(old, new)
        for key, value in (('issues', ['other error']), ('status', 'FAIL'),
                           ('elf_sha256', 'changed'), ('log_sha256', 'changed'),
                           ('sim_image_sha256', {'image': 'changed'})):
            wrong = copy.deepcopy(new)
            wrong[key] = value
            with self.assertRaises(ValueError):
                target.compare_protocol(old, wrong)
        wrong = copy.deepcopy(new)
        del wrong['log_sha256']
        with self.assertRaises(ValueError):
            target.compare_protocol(old, wrong)

    def test_command_removes_only_write_coverage_and_retargets_output(self):
        old = ['/python', '-B', '-m', 'ara_verify.uvm_dut', '--require-events',
               '--require-backend', '--require-axi', '--require-axi-write', '--output', '/old']
        expected = old.copy()
        expected.remove('--require-axi-write')
        expected[-1] = '/new'
        self.assertEqual(target.scoped_command(old, '/new'), expected)
        for flag in ('--require-events', '--require-backend', '--require-axi', '--require-axi-write'):
            wrong = old.copy()
            wrong.remove(flag)
            with self.assertRaises(ValueError):
                target.scoped_command(wrong, '/new')
        with self.assertRaises(ValueError):
            target.scoped_command(old+['--require-axi-write'], '/new')


class InstructionTests(unittest.TestCase):
    def test_scalar_fp_stores_are_not_vector_stores(self):
        for word in (0xfefb2e27, 0xfef6ae27, 0x00f73027 | (3 << 12)):
            self.assertFalse(target.vector_store(word))
        for width in (0, 5, 6, 7):
            self.assertTrue(target.vector_store(0x27 | (width << 12)))

    def test_complete_functions_with_scalar_stores(self):
        rows, stores = target.disassembly_work(disassembly())
        self.assertEqual(len(rows), 4)
        self.assertEqual(set(stores), set(target.FUNCTIONS))

    def test_vector_store_encoding_rejected_even_with_misleading_mnemonic(self):
        with self.assertRaises(ValueError):
            target.disassembly_work(disassembly()+'\n 2000: 02006027 .word 0x02006027\n')
        with self.assertRaises(ValueError):
            target.disassembly_work(disassembly().replace(target.FUNCTIONS[0], 'other_function'))
        with self.assertRaises(ValueError):
            target.disassembly_work(disassembly().replace('fefb2e27', '00000013'))

    def test_exact_independent_trace_work(self):
        result = target.trace_work(trace(), {0x92421257, 0x020ce207})
        self.assertEqual((result['allocations'], result['vector_loads'], result['vector_stores']), (937, 288, 0))

    def test_trace_store_unknown_instruction_missing_work_or_config_rejected(self):
        for wrong, words in ((trace()+'1000,alloc,02006027,4,1024\n', {0x92421257, 0x020ce207, 0x02006027}),
                             (trace(), {0x92421257}),
                             ('\n'.join(trace().splitlines()[:-1]), {0x92421257, 0x020ce207}),
                             (trace().replace('0,config,00000000,4,1024', '0,config,00000000,8,1024'),
                              {0x92421257, 0x020ce207})):
            with self.assertRaises(ValueError):
                target.trace_work(wrong, words)


if __name__ == '__main__':
    unittest.main()
