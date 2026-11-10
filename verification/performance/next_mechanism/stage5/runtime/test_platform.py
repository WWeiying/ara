#!/usr/bin/env python3
"""Host policy tests and scalar GNU object audit. No native model execution."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=Path('/home/wangwy/openproject/ara_dsa')
OUT=ROOT.parent/'ara_dsa_signoff_integration/verification/out'
REV='f50092f2d22238c6be4b6c159a1ad71a4ea68678'
GNU=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
OWN=('platform.h','platform.c','read_state.S','test_platform.c','test_platform.py','README.md')
OUTPUT=None


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class PlatformTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory() if OUTPUT is None else None
        cls.out=Path(cls.temp.name) if cls.temp else OUTPUT
        if OUTPUT is not None:cls.out.mkdir()
        cls.inputs=cls.out/'inputs';cls.inputs.mkdir();cls.commands=[];cls.pins={}
        for name in OWN:
            source=HERE/name;dest=cls.inputs/name;shutil.copyfile(source,dest)
            cls.pins[str(source)]=sha(source);cls.pins[str(dest)]=sha(dest)
        raw=subprocess.check_output(['git','-C',str(ROOT),'archive',REV,'software/akv'])
        (cls.out/'sdk.tar').write_bytes(raw)
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
            for member in archive.getmembers():
                if not (member.isfile() or member.isdir()) or '..' in Path(member.name).parts:
                    raise ValueError('Unsafe SDK archive')
            archive.extractall(cls.inputs/'sdk')
        cls.sdk=cls.inputs/'sdk/software/akv'
        for p in cls.inputs.rglob('*'):
            if p.is_file():cls.pins[str(p)]=sha(p)
        cls.pins[str(cls.out/'sdk.tar')]=sha(cls.out/'sdk.tar')

    @classmethod
    def tearDownClass(cls):
        if cls.temp:cls.temp.cleanup()

    def run_command(self,label,argv):
        argv=list(map(str,argv))
        p=subprocess.run(argv,cwd=self.out,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,
                         timeout=60,env=dict(PATH='/usr/bin:/bin',LC_ALL='C',HOME='/home/wangwy'))
        (self.out/(label+'.log')).write_bytes(p.stdout)
        self.commands.append(dict(label=label,argv=argv,returncode=p.returncode,cwd=str(self.out),timeout_seconds=60))
        tool=Path(shutil.which(argv[0]) or argv[0]).resolve();self.pins[str(tool)]=sha(tool)
        self.assertEqual(p.returncode,0,p.stdout.decode(errors='replace'))
        return p.stdout.decode()

    def host(self,name,extra=(),compiler='/usr/bin/gcc'):
        exe=self.out/name
        flags=['-std=gnu11','-O2','-UNDEBUG','-Wall','-Wextra','-Werror','-fno-fast-math',
            '-ffp-contract=off',
            '-ffunction-sections','-fdata-sections','-I'+str(self.inputs),
            '-I'+str(self.sdk/'include'),'-I'+str(self.sdk/'experimental')]
        flags+=['-fno-vectorize','-fno-slp-vectorize'] if compiler.endswith('clang') else [
            '-fno-tree-vectorize','-fno-tree-slp-vectorize']
        self.run_command(name+'-compile',[compiler,*flags,*extra,self.inputs/'platform.c',
            self.inputs/'test_platform.c',self.sdk/'src/akv_runtime.c',self.sdk/'src/akv_features.c',
            '-Wl,--gc-sections','-lm','-o',exe])
        text=self.run_command(name+'-run',[exe])
        self.assertEqual(text,'PLATFORM_HOST_PASS checks=88 native_execution=0 board_acceptance=0\n')

    def test_host_policy_lease_and_precopy_guards(self):self.host('host')

    def test_ubsan_policy_same_contract(self):
        self.host('ubsan',['-fsanitize=undefined','-fno-sanitize-recover=all'],'/usr/bin/clang')

    def test_scalar_gnu_objects_and_first_vstart_branch(self):
        for name in ('platform.c','read_state.S'):
            obj=self.out/(Path(name).stem+'.o')
            self.run_command('gnu-'+Path(name).stem,[GNU,'-march=rv64gcv_zfh_zvfh','-mabi=lp64d',
                '-O2','-fno-tree-vectorize','-fno-tree-slp-vectorize','-ffreestanding','-fno-builtin',
                '-I'+str(self.inputs),'-I'+str(self.sdk/'include'),'-I'+str(self.sdk/'experimental'),
                '-c',self.inputs/name,'-o',obj])
            text=self.run_command('disasm-'+Path(name).stem,[GNU.with_name(GNU.name[:-3]+'objdump'),
                '-d','-M','no-aliases,numeric',obj])
            words=[int(x,16) for x in re.findall(r'(?m)^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s',text)]
            self.assertTrue(words)
            self.assertFalse(any(w&127 in (0x07,0x27,0x43,0x47,0x4b,0x4f,0x53,0x57,0x5b) for w in words))
            if name=='read_state.S':
                self.assertEqual(words[0]>>20,0x008)  # vstart, not privileged mstatus/sstatus
                self.assertEqual(words[1]&127,0x63)
                self.assertFalse(any(w&127==0x73 and (w>>12)&7 in (1,5) for w in words))
                self.assertTrue(all((w>>20) not in (0x300,0x100) for w in words if w&127==0x73))

    def test_no_environment_authority_or_native_query(self):
        text=(self.inputs/'platform.c').read_text()
        for name in ('getenv','akv_native_info','akv_encode_resident','mstatus','sstatus'):
            self.assertNotIn(name,text)
        self.assertIn('const volatile uint8_t *identity',text)
        self.assertIn('return NULL;',text)

    def test_fixed_supported_bits_remain_zero(self):
        abi=(self.sdk/'include/akv/akv_abi.h').read_text()
        self.assertIn('#define AKV_RESIDENT_QK_SUPPORTED 0u',abi)
        self.assertIn('#define AKV_RESIDENT_PV_SUPPORTED 0u',abi)

    def test_precopy_reader_contains_no_calls_or_writes(self):
        text=(self.inputs/'read_state.S').read_text()
        self.assertLess(text.index('csrr t0, vstart'),text.index('bnez t0'))
        self.assertLess(text.index('bnez t0'),text.index('sd t1'))
        self.assertNotRegex(text,r'(?m)^\s*(?:call|csrw\w*)\s')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    parser.add_argument('--output',type=Path)
    args,rest=parser.parse_known_args()
    if args.output:
        OUTPUT=args.output.absolute()
        if OUTPUT!=OUTPUT.resolve() or OUTPUT.parent!=OUT or OUTPUT.exists() or not re.fullmatch(
                r'stage5_resident_platform_host_[A-Za-z0-9_-]+',OUTPUT.name):
            raise ValueError('Fresh direct signoff stage5_resident_platform_host_* output required')
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(PlatformTests)
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    if OUTPUT is not None and OUTPUT.exists():
        pins=PlatformTests.pins
        for p,digest in pins.items():
            if sha(p)!=digest:raise ValueError('Identity drift: '+p)
        (OUTPUT/'commands.json').write_text(json.dumps(PlatformTests.commands,indent=2)+'\n')
        (OUTPUT/'source-pins.json').write_text(json.dumps(pins,indent=2,sort_keys=True)+'\n')
        report=dict(state='HOST_GNU_POLICY_PASS_NO_NATIVE' if result.wasSuccessful() else 'FAIL',
            host_tests=result.testsRun,host_c_checks=88,sdk_revision=REV,native_execution=False,
            qemu_provider_accepted=False,board_acceptance=False,discovery_changed=False,
            source_pins_sha256=sha(OUTPUT/'source-pins.json'),
            artifacts={str(p):sha(p) for p in OUTPUT.rglob('*') if p.is_file()})
        (OUTPUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
