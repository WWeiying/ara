"""Synthetic host checks only. No compiler, simulator, real run, or polling."""
import copy
import importlib.util
from pathlib import Path
import re
import sys
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location('legacy_latency_run_tests', HERE/'run.py')
runner = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = runner
spec.loader.exec_module(runner)
check = runner.checker


def rows():
    result = []
    cases = [(0,128,0),(2,128,0),(1,128,0),(3,0,0),(0,64,0),(2,64,0),
             (2,128,-1),(0,128,2),(0,128,3),(0,128,5),(4,128,0)]
    for index, (command, dim, fault) in enumerate(cases):
        row = dict.fromkeys(check.META+check.COUNTERS, 0)
        row.update(seq=index+1, command=command, dim=dim, id=index % 16, busy=1,
                   accept=index*100+10, first=index*100+20, fire=index*100+22,
                   first_latency=10, fire_latency=12, wait_cycles=2, command_cycles=11,
                   success=int(fault == 0), fault=int(fault != 0), context_ready=int(fault == 0),
                   validation=int(fault == -1), validation_error=int(fault == -1),
                   read_fault_kind=max(fault,0), mmu_valid=int(fault == 2))
        result.append(row)
    return result


def transcript(records=None):
    records = rows() if records is None else records
    lines = ['AKV_LATENCY_BEGIN version=1']
    for row in records:
        lines.append('AKV_LATENCY_COMMAND '+' '.join(
            f'{key}={row[key]:016x}' if key in check.HEX else f'{key}={row[key]}'
            for key in check.META+check.COUNTERS))
    lines += [check.SUITE, f'AKV_LATENCY_SUMMARY version=1 accepted={len(records)} '
              f'completed={len(records)} pending=0 errors=0']
    return '\n'.join(lines)+'\n'


class LatencyTests(unittest.TestCase):
    def test_exact_inherited_warning_only(self):
        source = Path('/snapshot')/runner.TLB_RELATIVE
        warning = runner.admitted_warning(source)
        log = '\n'+warning+'\ncompile complete\n'
        with patch.object(runner.tools, 'digest', return_value=runner.TLB_SHA256):
            self.assertEqual(runner.check_compile(log, 0, source)['count'], 1)
            mutations = [log+warning, log.replace(warning,''),
                         log.replace("'i'", "'x'"), log.replace('458','459'),
                         log.replace('168','169'), log.replace('genvar','wire'),
                         log.replace(str(source), '/other/tlb.sv'),
                         log+'Warning-[IPDW] another net\n', log+'Warning-[PCWM] width\n',
                         log+'Warning-[PINMISSING] pin\n', log+'Error: failed\n',
                         log.replace('Warning-[IPDW]', 'prefixWarning-[IPDW]')]
            for bad in mutations:
                with self.subTest(log=bad), self.assertRaises(ValueError):
                    runner.check_compile(bad, 0, source)
            with self.assertRaises(ValueError):
                runner.check_compile(log, 1, source)
        with patch.object(runner.tools, 'digest', return_value='0'*64), self.assertRaises(ValueError):
            runner.check_compile(log, 0, source)

    def test_complete_synthetic_pair(self):
        old = check.check_log(transcript(),0)
        result = check.compare(old, copy.deepcopy(old))
        self.assertEqual(result['state'],'PASS')
        self.assertFalse(result['soc_verified'])
        self.assertFalse(result['ppa_measured'])

    def test_all_latency_and_counter_differences_are_reported(self):
        old = check.check_log(transcript(),0)
        new = copy.deepcopy(old)
        new['rows'][0]['first_latency'] += 1
        new['rows'][0]['fire_latency'] += 1
        new['rows'][1]['command_cycles'] -= 1
        result = check.compare(old,new)
        self.assertEqual(result['state'],'REGRESSION')
        self.assertEqual(len(result['differences']),2)
        self.assertIn('first_latency',result['differences'][0]['fields'])

    def test_absolute_tick_shift_does_not_fake_latency_difference(self):
        old = check.check_log(transcript(),0)
        shifted = rows()
        for row in shifted:
            for key in ('accept','first','fire'):
                row[key] += 50
        new = check.check_log(transcript(shifted),0)
        self.assertEqual(check.compare(old,new)['state'],'PASS')

    def test_malformed_unknown_missing_duplicate_records(self):
        text = transcript()
        command = next(line for line in text.splitlines() if line.startswith('AKV_LATENCY_COMMAND'))
        mutations = [text.replace(command+'\n','',1), text.replace(command,command+'\n'+command,1),
                     text.replace(command,command+' extra=1',1),
                     text.replace('AKV_LATENCY_COMMAND','AKV_LATENCY_COMMAND_BOGUS',1),
                     text+'AKV_LATENCY_UNKNOWN x=0\n', text.replace('pending=0','pending=1'),
                     text.replace('errors=0','errors=1'), text.replace('version=1','version=2',1),
                     text.replace('seq=1 ','seq=x ',1), text.replace(check.SUITE,''),
                     text+check.SUITE+'\n', text+'Error: failed\n']
        for bad in mutations:
            with self.assertRaises(ValueError):
                check.check_log(bad,0)
        with self.assertRaises(ValueError):
            check.check_log(text,1)

    def test_timing_and_fault_validity(self):
        changes = [(0,'first_latency',11), (0,'fire',0), (0,'wait_cycles',0),
                   (0,'fault_vaddr',1), (0,'mmu_valid',1), (0,'success',0),
                   (6,'read_fault_kind',2), (8,'mmu_tval',1), (0,'read_outstanding_max',3)]
        for index, field, value in changes:
            data = rows()
            data[index][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                check.check_log(transcript(data),0)

    def test_only_three_filelist_units_change_order_and_defines_preserved(self):
        mapping = {f'/snapshot/source/{name}':f'/canonical/{name}' for name in runner.MODULES}
        text = '\n'.join(['+define+VLEN=1024','+incdir+/snapshot/source/hardware/include',
                          '// fixed graph',*mapping,'/snapshot/support/repacker.sv',
                          '/snapshot/source/mock_uart.sv','/snapshot/source/mock_uart.sv'])+'\n'
        old,new = runner.paired_lists(text,mapping)
        self.assertEqual(new,text)
        self.assertEqual(sum(x != y for x,y in zip(old.splitlines(),new.splitlines())),3)
        self.assertEqual(old.splitlines()[-3:],new.splitlines()[-3:])
        for bad in (text+next(iter(mapping))+'\n',text.replace(next(iter(mapping)),'missing',1)):
            with self.assertRaises(ValueError):
                runner.paired_lists(bad,mapping)

    def test_source_monitor_contract_is_top_wire_only(self):
        source = (HERE/'monitor.sv').read_text()
        self.assertIn('bind akv_engine_tb akv_legacy_latency_monitor', source)
        self.assertIn('default input #1step;',source)
        self.assertNotIn('dut.',source)
        self.assertNotIn('$fatal',source)
        names = source.split('localparam string Names [31] =',1)[1].split('};',1)[0]
        self.assertEqual(re.findall(r'"([a-z_0-9]+)"',names),check.COUNTERS)
        bound = source.split('.stats({',1)[1].split('}),',1)[0]
        bound_names = re.findall(r'\b[a-z_][a-z_0-9]*\b',bound)
        self.assertEqual(bound_names,check.COUNTERS)
        bench = runner.BENCH.read_text()
        for name in check.COUNTERS:
            self.assertRegex(bench,rf'\b{re.escape(name)}\b')
        package = (runner.ROOT/'hardware/include/qbs_pkg.sv').read_text()
        for name,value in (('MMU',2),('AXI_RESPONSE',3),('PMA',5)):
            self.assertRegex(package,rf'QBS_READ_FAULT_{name}\s*=\s*3\x27d{value}')

    def test_original_assertions_and_stimulus_inverse(self):
        original = runner.BENCH.read_text()
        changed = runner.composer.adapt_tb(original,'akv')
        restored = changed.replace('dut.i_engine.','dut.').replace(
            '  akv_engine_composed #(\n','  akv_engine #(\n',1)
        self.assertEqual(restored,original)
        entry,_ = runner.composer.contract('akv')
        self.assertEqual(runner.tools.digest(runner.BENCH),entry['tb_sha256'])


if __name__ == '__main__':
    unittest.main()
