"""Host-only context geometry/provenance and strict evidence mutations."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from context_spec import CAPTURE_ROOT, NAMES, ORDER, expected, old_build, shared as s
from build_context import validate_capture
from check_context import check_log, subset, SUITE


def fixture(kv=256, paired_cycles=80000):
    lines,rows = [subset(kv)],[]
    for trial,variant in enumerate(ORDER):
        paired = variant == 'paired'
        lines.append(f'CONTEXT_THREEWAY_BEGIN trial={trial} variant={variant}')
        commands = []
        if variant != 'rvv':
            for head in range(2):
                for start in range(0,kv,64):
                    commands.append(4 if start == 0 else 5)
                    commands += [6]*(32 if paired else 256)
                    commands += [2]*(64 if paired else 128)
                commands.append(3)
        for cmd in commands:
            row = dict.fromkeys(s.PERF_FIELDS,0)
            row.update(seq=len(rows)+1,id=1,command=cmd,success=1,context_ready=int(cmd != 3),busy_cycles=10)
            if cmd in (4,5):
                row.update(v2_full=int(cmd == 4),v2_refill=int(cmd == 5),
                    q_external_bytes=512 if cmd == 4 else 0,kv_external_bytes=32768,
                    read_ranges=131 if cmd == 4 else 128,read_payload_bytes=33344 if cmd == 4 else 32768,
                    ar=140,r_beats=2100,read_outstanding_max=2)
            elif cmd == 6:
                row.update(v2_column_load=1,v2_column_panel=int(paired),v2_logical_column=4 if paired else 1,
                    replay_bytes=512 if paired else 128,v2_k_view_bank_cycles=8)
            elif cmd == 2:
                row.update(load=1,v2_row_load=1,replay_bytes=256)
            else:
                row['release'] = 1
            rows.append(row)
            lines.append('[AKV_PERF] '+' '.join(f'{k}={v}' for k,v in row.items()))
        cycles = paired_cycles if paired else 100000 if variant == 'generic' else 200000
        flags = 1 if variant == 'rvv' else 3
        checksum = '0123456789abcdef' if variant == 'rvv' else '9876543210abcdef'
        lines.append(f'CONTEXT_THREEWAY_END trial={trial} variant={variant} executed=1 native={int(variant != "rvv")} '
            f'admitted_groups={2*int(paired)} outputs=512 cycles={cycles} fcsr={flags} vcsr=5 '
            f'checksum={checksum} guardbytes=384 errors=0')
    # Independent sum/max calculation instead of the checker's totals helper.
    from run_refill_overlap_probe import COUNTERS
    summary = {k:sum(r[k] for r in rows) for k in COUNTERS}
    summary['read_outstanding_max'] = 2
    summary.update(records=len(rows),success_records=len(rows),fault_records=0,validation_fault_records=0)
    lines += [SUITE,s.TERMINAL,'UVM_ERROR : 0','UVM_FATAL : 0',
              '[AKV_PERF_SUMMARY] '+' '.join(f'{k}={v}' for k,v in summary.items())]
    return '\n'.join(lines)+'\n'


class ContextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.text = fixture()

    def test_exact_kv256_geometry(self):
        e = expected(256)
        self.assertEqual(e['commands'],7720)
        self.assertEqual(e['generic'],dict(commands=3082,column_load=2048,column_panel=0,row_load=1024,logical_columns=2048,replay_bytes=524288))
        self.assertEqual(e['paired'],dict(commands=778,column_load=256,column_panel=256,row_load=512,logical_columns=1024,replay_bytes=262144))
        self.assertEqual(e['per_native_trial'],dict(v2_full=2,v2_refill=6,release=2,q_external_bytes=1024,
            kv_external_bytes=262144,read_payload_bytes=263296,read_ranges=1030))
        for bad in (0,64,129,512,True):
            with self.assertRaises(ValueError):
                expected(bad)

    def test_six_trials_own_numerical_contract(self):
        result = check_log(self.text,256)
        self.assertEqual([t['derived_hardware_totals']['records'] for t in result['trials']], [0,3082,778,778,3082,0])
        self.assertNotEqual(result['trials'][0]['checksum'],result['trials'][1]['checksum'])
        self.assertNotEqual(result['trials'][0]['fcsr'],result['trials'][1]['fcsr'])
        self.assertEqual(result['raw_hardware_summary']['records'],7720)
        self.assertFalse(result['deployment_approved'])

    def test_kv128_parameterized_not_accepted_as_kv256(self):
        old = fixture(128)
        self.assertEqual(check_log(old,128)['raw_hardware_summary']['records'],3864)
        with self.assertRaises(ValueError):
            check_log(old,256)

    def test_negative_and_neutral_performance_preserve_functional_pass(self):
        for cycles,label in ((200000,'neutral'),(300000,'regressed')):
            result = check_log(fixture(paired_cycles=cycles),256)
            self.assertEqual(result['state'],'PASS')
            self.assertEqual(result['performance_vs_ordinary_rvv'],label)

    def test_same_context_checksums_not_fixed_to_prior_capture(self):
        result = check_log(self.text.replace('9876543210abcdef','aaaaaaaaaaaaaaaa'),256)
        self.assertEqual(result['state'],'PASS')

    def test_wrong_work_unknown_and_faults(self):
        for old,new in (('seq=1 ','seq=2 '),('command=4','command=5'),('v2_refill=1','v2_refill=0'),
            ('v2_column_panel=1','v2_column_panel=0'),('v2_logical_column=4','v2_logical_column=1'),
            ('replay_bytes=512','replay_bytes=128'),('read_payload_bytes=33344','read_payload_bytes=33343'),
            ('success=1','success=0'),('fault=0','fault=1'),('context_ready=1','context_ready=0'),
            ('busy_cycles=10','busy_cycles=x'),('guardbytes=384','guardbytes=0'),('errors=0','errors=1'),
            ('admitted_groups=2','admitted_groups=0'),('fcsr=3','fcsr=32'),('vcsr=5','vcsr=0'),
            ('checksum=9876543210abcdef','checksum=0000000000000000')):
            with self.subTest(old=old),self.assertRaises(ValueError):
                check_log(self.text.replace(old,new,1),256)

    def test_missing_duplicate_fake_and_malformed_records(self):
        lines = self.text.splitlines()
        refill = next(i for i,l in enumerate(lines) if l.startswith('[AKV_PERF] ') and ' command=5 ' in l)
        malformed = ['\n'.join(lines[:refill]+lines[refill+1:]), self.text+lines[refill],
            self.text.replace('[AKV_PERF_SUMMARY]','[AKV_PERF_SUMMARY_BOGUS]'),
            '\n'.join(l for l in lines if not l.startswith('[AKV_PERF_SUMMARY]')),
            self.text.replace('CONTEXT_THREEWAY_BEGIN trial=2 variant=paired','CONTEXT_THREEWAY_BEGIN trial=2 variant=generic'),
            self.text.replace(subset(256),subset(128)), self.text+'\n'+SUITE,
            SUITE+'\n'+s.TERMINAL, self.text+'\n[QBS_PERF] seq=1',
            self.text.replace('UVM_ERROR : 0','UVM_ERROR : 1'),self.text.replace(s.TERMINAL,''),
            self.text.replace('[AKV_PERF]','embedded [AKV_PERF]',1)]
        for i,text in enumerate(malformed):
            with self.subTest(i=i),self.assertRaises(ValueError):
                check_log(text,256)

    def test_rvv_cannot_issue_akv(self):
        record = next(l for l in self.text.splitlines() if l.startswith('[AKV_PERF] '))
        text = self.text.replace('CONTEXT_THREEWAY_BEGIN trial=0 variant=rvv',
             'CONTEXT_THREEWAY_BEGIN trial=0 variant=rvv\n'+record)
        with self.assertRaises(ValueError):
            check_log(text,256)

    def test_real_capture_and_crop(self):
        root = CAPTURE_ROOT/'kv256'
        info = validate_capture(root,256)
        self.assertEqual(info['provenance']['source_dirty'],'true')
        for name in ('input_a','golden'):
            original = (root/'decode/block'/(NAMES[name]+'.bin')).read_bytes()
            cropped = old_build.crop_heads(original)
            self.assertEqual(len(cropped),2048)
        self.assertEqual(old_build.self_test()['rejected_mutations'],3)

    def test_capture_mutations_rejected_without_touching_originals(self):
        root = CAPTURE_ROOT/'kv256'
        info = validate_capture(root,256)
        with tempfile.TemporaryDirectory(prefix='akv-context-host-') as temp:
            copy = Path(temp)
            for source in info['files']:
                target = copy/source.relative_to(root)
                target.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(source,target)
            manifest = copy/'tensor.sha256'
            saved = manifest.read_text()
            for bad in ('\n'.join(saved.splitlines()[1:]),saved+saved.splitlines()[0]+'\n'):
                manifest.write_text(bad)
                with self.assertRaises(ValueError): validate_capture(copy,256)
            manifest.write_text(saved)
            q = copy/'decode/block/attn_q_input-0.bin'
            contents = q.read_bytes()
            q.write_bytes(bytes([contents[0]^1])+contents[1:])
            with self.assertRaises(ValueError): validate_capture(copy,256)
            q.write_bytes(contents)
            meta = q.with_suffix('.json')
            original_meta = meta.read_text()
            changed = json.loads(original_meta)
            changed['strides'][2] = 256
            meta.write_text(json.dumps(changed))
            with self.assertRaises(ValueError): validate_capture(copy,256)
            meta.write_text(original_meta)
            conf = copy/'run.conf'
            conf.write_text(conf.read_text().replace('effective_kv=256','effective_kv=128'))
            with self.assertRaises(ValueError): validate_capture(copy,256)


if __name__ == '__main__':
    unittest.main()
