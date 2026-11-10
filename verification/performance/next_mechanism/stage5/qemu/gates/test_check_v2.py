"""Host-only INFO trace mutations, not execution evidence."""
import argparse
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
import sys
import unittest

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('directed_info_successor',HERE/'check_v2.py')
v=importlib.util.module_from_spec(spec);spec.loader.exec_module(v)
WORDS=[0x000f010808400101,0x006b1a5b,0x0000017f06084002,0x01803e5b,0]


def fixture():
    manifest=dict(cases=[dict(op='info',a=i,cause=0) for i in range(5)])
    trace=''.join('100@0:akv_arch_info index=%d result=0x%x\n'%(i,word) for i,word in enumerate(WORDS))
    return manifest,trace


class InfoSuccessorTests(unittest.TestCase):
    def test_actual_words(self):
        m,t=fixture()
        self.assertEqual(v.info_results(t,m),dict(records=5,trace_results_checked=True))

    def test_wrong_result_index_count(self):
        m,t=fixture()
        for changed in (t.replace('result=0x0','result=0x1',1),t.replace('index=0','index=1',1),
                        '\n'.join(t.splitlines()[:-1])+'\n',t+t.splitlines()[-1]+'\n'):
            with self.subTest(trace=changed),self.assertRaises(ValueError):v.info_results(changed,m)

    def test_disabled_no_info_event(self):
        m=dict(cases=[dict(op='info',a=0,cause=2)])
        self.assertEqual(v.info_results('',m),dict(records=0,trace_results_checked=True))
        with self.assertRaises(ValueError):v.info_results('akv_arch_info index=0 result=0x0\n',m)

    def test_original_checker_unchanged(self):
        self.assertEqual(hashlib.sha256(v.BASE.read_bytes()).hexdigest(),v.BASE_SHA)


if __name__=='__main__':
    p=argparse.ArgumentParser(add_help=False);p.add_argument('--output',type=Path)
    args,other=p.parse_known_args()
    if args.output is None:
        unittest.main(argv=[sys.argv[0],*other])
    else:
        root=HERE.parents[5];out=args.output.absolute()
        if out.parent!=root.parent/'ara_dsa_signoff_integration/verification/out' or out!=out.resolve() or out.exists():
            raise ValueError('Fresh direct signoff output required')
        out.mkdir();inputs=out/'inputs';inputs.mkdir();pins={}
        def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
        for name in ('check.py','check_v2.py','test_check_v2.py'):
            source=HERE/name;shutil.copyfile(source,inputs/name)
            pins[str(source)]=sha(source);pins[str(inputs/name)]=sha(inputs/name)
        log=io.StringIO();r=unittest.TextTestRunner(stream=log,verbosity=2).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(InfoSuccessorTests))
        (out/'host.log').write_text(log.getvalue())
        (out/'source-pins.json').write_text(json.dumps(pins,indent=2,sort_keys=True)+'\n')
        matched=all(sha(Path(path))==h for path,h in pins.items())
        report=dict(state='HOST_INFO_SUCCESSOR_PASS_NOT_EXECUTED' if r.wasSuccessful() and matched else 'FAIL',
                    host_tests=r.testsRun,post_pins_match=matched,original_checker_sha256=v.BASE_SHA,
                    firmware_rebuilt=False,qemu_executed=False,source_pins_sha256=sha(out/'source-pins.json'))
        (out/'result.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n')
        print(log.getvalue(),end='');print(json.dumps(report,sort_keys=True))
        raise SystemExit(int(report['state']=='FAIL'))
