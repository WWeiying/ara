import copy
import json
from pathlib import Path
import tempfile
import unittest

import scalar_entropy64_reviewed as r


class Reviewed(unittest.TestCase):
    def test_actual_frozen_typed_fixture_has_only_regfile_MDA(self):
        runtime = json.loads((r.runner.OUT/'scalar-entropy64-old-image786-agent-20261008-01.prepared.json').read_bytes())
        files = list((Path(runtime['input_ledger'][-1])/'snps/coverage/db/testdata').glob('*/tgl.verilog.data.xml'))
        self.assertEqual(len(files),1)
        binary,groups = r.typed_sample(files[0],runtime['compiled_definitions'])
        self.assertEqual(len(groups[r.runner.SCOPES[0]]),6)
        self.assertEqual(groups[r.runner.SCOPES[1]],[])
        self.assertEqual(binary[r.runner.SCOPES[1]]['width'],5076)
        bad = copy.deepcopy(runtime['compiled_definitions'])
        bad[r.runner.SCOPES[0]]['checksum'] = '1'
        with self.assertRaises(ValueError):
            r.typed_sample(files[0],bad)

    def test_real_cache_exact_prefix_binding(self):
        manifest = json.loads((r.runner.BASE/'admission-manifest.json').read_bytes())
        runtime = dict(input_ledger=(r.runner.BASE/'combined-inputs.txt').read_text().splitlines(),
                       pins=manifest['input_pins'])
        cache = r.life.read_bound(r.CACHE,r.CACHE_SHA)
        self.assertEqual(set(r.cache_prefix(runtime,cache)),set(r.runner.SCOPES))
        bad = copy.deepcopy(runtime)
        bad['input_ledger'][1],bad['input_ledger'][742] = bad['input_ledger'][742],bad['input_ledger'][1]
        with self.assertRaises(ValueError):
            r.cache_prefix(bad,cache)
        bad = copy.deepcopy(cache)
        name = next(iter(bad['input_pins']))
        bad['input_pins'][name] = '0'*64
        with self.assertRaises(ValueError):
            r.cache_prefix(runtime,bad)

    def test_terminal_receipt_and_false_integer_negative(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td)
            launch = dict(pid=123,command=['simv'],cwd=str(out),executable=str(r.life.IMAGE),
                          exe_sha256='a'*64,starttime_ticks=99,cgroup='0::/app.slice/'+r.SERVICE+'\n',
                          expected_systemd_service=r.SERVICE)
            r.life.save(out/'launch-identity.json',launch)
            receipt = dict(schema='ENTROPY64_PROCESS_TERMINAL_V1',complete=True,timed_out=False,
                returncode=0,reason=None,timeout_seconds=600,pid=123,
                launch_identity_sha256=r.runner.toggle.digest(out/'launch-identity.json'))
            runtime = dict(command=['simv'],timeout_s=600,pins={str(r.life.IMAGE):'a'*64},expected_systemd_service=r.SERVICE)
            (out/'execution-receipt.json').write_text(json.dumps(receipt))
            r.verify_receipt(out,runtime)
            for changes in (dict(returncode=False),dict(timed_out=True),dict(pid=124),dict(reason='failed')):
                (out/'execution-receipt.json').write_text(json.dumps(dict(receipt,**changes)))
                with self.subTest(changes=changes),self.assertRaises(ValueError):
                    r.verify_receipt(out,runtime)

    def test_real_identity_foreign_command_rejected(self):
        import os
        with self.assertRaises(ValueError):
            r.identity(os.getpid(),[str(r.life.IMAGE)],Path.cwd(),r.SERVICE)

    def test_exact_service_cgroup_not_merely_nonempty(self):
        r.service_cgroup('0::/user.slice/app.slice/'+r.SERVICE+'\n',r.SERVICE)
        for text in ('0::/foreign.service\n','0::/app.slice/'+r.SERVICE+'/foreign\n',
                     '0::/app.slice/'+r.SERVICE+'\n1:cpu:/foreign.service\n',''):
            with self.subTest(text=text),self.assertRaises(ValueError):
                r.service_cgroup(text,r.SERVICE)

    def test_native_siminfo_command_compile_and_all_five_metrics(self):
        import shlex
        import xml.etree.ElementTree as ET
        runtime = dict(command=['/simv','+PRELOAD=/file with space.elf'],input_ledger=['/compiled/simv.vdb'])
        out = Path('/run')
        sim = ET.Element('test')
        ET.SubElement(sim,'srctest',cmdline=shlex.join(runtime['command']),workdir=str(out),seed='1',
                      teststatus='unknown',starttime='1000000',finishtime='2000000')
        args = ET.Element('vcm_args',compvdbpath=runtime['input_ledger'][0])
        for metric in ('branch','cond','fsm','line','tgl'):
            ET.SubElement(args,'vcm_arg_data',vcm_opt='-cm '+metric)
        self.assertTrue(r.native_identity(sim,args,runtime,out)['XML_status_not_claimed_as_PASS'])
        for key,value in (('workdir','/foreign'),('seed','0'),('cmdline','/foreign'),('finishtime','0')):
            bad = copy.deepcopy(sim)
            bad[0].set(key,value)
            with self.subTest(key=key),self.assertRaises(ValueError):
                r.native_identity(bad,args,runtime,out)
        for mode in ('missing','duplicate','compile'):
            bad = copy.deepcopy(args)
            if mode == 'missing':
                bad.remove(bad[-1])
            elif mode == 'duplicate':
                ET.SubElement(bad,'vcm_arg_data',vcm_opt='-cm tgl')
            else:
                bad.set('compvdbpath','/foreign')
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                r.native_identity(sim,bad,runtime,out)

    def test_private_measure_does_not_change_frozen_collector(self):
        from types import FunctionType
        original = r.collector.collect.__globals__['measure']
        private = FunctionType(r.collector.collect.__code__,dict(r.collector.collect.__globals__,measure=r.measure))
        self.assertIs(private.__globals__['measure'],r.measure)
        self.assertIs(r.collector.collect.__globals__['measure'],original)


if __name__ == '__main__':
    unittest.main()
