import json
from pathlib import Path
import tempfile
import unittest

from audit import digest
from collect_output_tile import check, EXPECTED


class OutputEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        state,_,markers=EXPECTED['online']
        for name in ('test','commands.json','disassembly.log','source.h'):
            (self.root/name).write_text('fixture\n')
        pins={str(self.root/'source.h'):digest(self.root/'source.h')}
        (self.root/'source-pins.json').write_text(json.dumps(pins))
        self.result=dict(state=state,suite='online',rtl_performance=False,
                         production_enabled=False,elf_sha256=digest(self.root/'test'),
                         source_pins_sha256=digest(self.root/'source-pins.json'),trials=[])
        for vlen,marker in markers.items():
            log=self.root/f'qemu-{vlen}.log'
            log.write_text(marker+'\nGUEST_TEST_EXIT=0\n')
            self.result['trials'].append(dict(vlen=vlen,marker=marker,log_sha256=digest(log)))
        self.save()

    def save(self):
        (self.root/'result.json').write_text(json.dumps(self.result))

    def test_accepts_both_raw_verdicts(self):
        self.assertEqual(check(self.root,'online')['source_pins_checked'],1)

    def test_green_result_cannot_override_guest_failure(self):
        log=self.root/'qemu-1024.log'
        log.write_text('OUTPUT_ONLINE_FAIL\nGUEST_TEST_EXIT=1\n')
        self.result['trials'][0]['log_sha256']=digest(log)
        self.save()
        with self.assertRaises(ValueError): check(self.root,'online')

    def test_changed_inputs_rejected(self):
        (self.root/'source.h').write_text('changed\n')
        with self.assertRaises(ValueError): check(self.root,'online')

    def test_duplicate_vlen_rejected(self):
        self.result['trials'][1]=self.result['trials'][0]
        self.save()
        with self.assertRaises(ValueError): check(self.root,'online')

    def test_wrong_suite_rejected(self):
        with self.assertRaises(ValueError): check(self.root,'runtime')


if __name__=='__main__': unittest.main()
