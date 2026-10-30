import unittest
import json
import os
import tempfile
from pathlib import Path
import build
import render


class PrepareTests(unittest.TestCase):
    def setUp(self):
        self.source=render.SOURCE.read_bytes()
        self.generated=render.render(self.source)

    def test_exact_inverse_and_timing(self):
        self.assertEqual(render.inverse(self.generated),self.source)
        self.assertEqual(render.timed(self.generated),render.timed(self.source))
        self.assertEqual(render.digest(render.timed(self.generated)),render.TIMED_SHA)

    def test_diagnostic_extent_no_repeat_claim(self):
        proof=render.provenance(self.generated)
        self.assertEqual(proof['trial_order'],[0,1,2])
        self.assertEqual(proof['total_outputs'],2304)
        self.assertEqual(proof['expected_qbs_commands'],8)
        self.assertEqual(self.generated.count(b'QUANT_DIAG_HSB_'),4)
        self.assertNotIn(b'repeats_exact=1',self.generated)
        self.assertNotIn(b'QUANT_THREEWAY_',self.generated)
        self.assertIn(b'repeat_checks=0',self.generated)

    def test_unreviewed_source_rejected(self):
        for before,after in [(b'0.004f',b'0.04f'),(b'vc!=5',b'vc!=0'),(b'0xa5',b'0x00')]:
            with self.subTest(before=before),self.assertRaises(ValueError):
                render.render(self.source.replace(before,after,1))

    def test_inverse_rejects_semantic_or_protocol_mutations(self):
        for before,after in [(b'THREEWAY_TRIALS = 3',b'THREEWAY_TRIALS = 2'),
            (b'0.004f',b'0.04f'),(b'repeat_checks=0',b'repeat_checks=1'),
            (b'QUANT_DIAG_HSB_BEGIN',b'QUANT_THREEWAY_BEGIN'),
            (b'HEADS*DIM*4',b'HEADS*DIM*8')]:
            with self.subTest(before=before),self.assertRaises(ValueError):
                render.inverse(self.generated.replace(before,after,1))

    def test_checks_remaining(self):
        for token in (b'!isfinite(y)',b'delta>0.004f+0.002f*fabsf(gold)',b'fc!=baseline_fcsr',
                      b'vc!=5',b'output.before[i]!=0xa5',b'output.after[i]!=0xa5',
                      b'padding_word!=UINT32_C(0xa5a5a5a5)',b'if (errors) return 1;'):
            self.assertEqual(self.source.count(token),1)
            self.assertEqual(self.generated.count(token),1)

    def test_approved_compile_policy(self):
        cc,link=build.templates()
        build.policy(cc,link)
        for mutate in ('-ffast-math','-Ofast','-ffp-contract=off'):
            with self.subTest(mutate=mutate),self.assertRaises(ValueError):
                build.policy(cc+[mutate],link)
        with self.assertRaises(ValueError):
            build.policy(['zcc',*cc[1:]],link)

    def test_link_slot_finite_and_no_silent_growth(self):
        data=build.linker(Path('/tmp/diagnostic-fixture'))
        self.assertIn('. = 0x1c4c;',data)
        self.assertIn('__review_main_body_end <= 0x80001c4c',data)
        self.assertIn('SIZEOF(.text) == 0x4b88',data)
        self.assertIn('ADDR(.bss) == 0x8003c500',data)

    def test_repeated_or_missing_timer_rejected(self):
        with self.assertRaises(ValueError): render.timed(self.source+render.START)
        with self.assertRaises(ValueError): render.timed(self.source.replace(render.END,b'',1))

    def test_linked_protocol_does_not_confuse_unused_predecessor_string(self):
        data=(b'QUANT_STRIDED_SUITE_PASS repeats_exact=1\n\0'
              b'QUANT_DIAG_HSB_CAP\0QUANT_DIAG_HSB_BEGIN\0QUANT_DIAG_HSB_RESULT\0'
              b'QUANT_DIAG_HSB_SUITE_PASS trials=3 outputs=768 rvv_exact=1 repeat_checks=0\n\0')
        build.protocol_bytes(data)
        for changed in (data.replace(b'repeat_checks=0',b'repeat_checks=1'),
                        data.replace(b'trials=3',b'trials=6'),data+b'QUANT_DIAG_HSB_BOGUS',
                        data+b'QUANT_THREEWAY_SUITE_PASS'):
            with self.assertRaises(ValueError): build.protocol_bytes(changed)


@unittest.skipUnless(os.environ.get('Q4_PHASE_DIAG_ELF'), 'Explicit GNU artifact required')
class ObjectChecks(unittest.TestCase):
    def setUp(self):
        self.path=Path(os.environ['Q4_PHASE_DIAG_ELF']).resolve(strict=True)
        self.assembly=(self.path.parent/'disassembly.log').read_text()
        self.prior=json.loads((build.BASE/'layout-review.json').read_text())

    def test_actual_object_map(self):
        report=build.mapped(self.path,self.assembly,self.prior)
        self.assertEqual(len(report['rdcycle_sites']),2)
        self.assertEqual(len(report['objects']),32)
        self.assertEqual(len(report['nonmain_functions']),36)

    def test_payload_and_primitive_byte_mutations_rejected(self):
        elf=build.Elf(self.path)
        for name in ('attention_query','attention_golden','attention_strided_key','qbs_native_execute_command'):
            with self.subTest(name=name),tempfile.TemporaryDirectory() as temp:
                row=elf.symbols[name];section=elf.sections[row['section']]
                offset=section[4]+row['address']-section[3]
                data=bytearray(elf.data);data[offset]^=1
                path=Path(temp)/'mutant.elf';path.write_bytes(data)
                with self.assertRaises(ValueError): build.mapped(path,self.assembly,self.prior)

    def test_missing_timer_rejected(self):
        with self.assertRaises(ValueError):
            build.mapped(self.path,self.assembly.replace('rdcycle','rdinstret'),self.prior)


if __name__=='__main__': unittest.main()
