#!/usr/bin/env python3
"""Frozen-source, host-control and GNU build checks. No native model execution."""
import argparse
import io
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import unittest

sys.dont_write_bytecode=True
import prepare as overlay

HERE=Path(__file__).resolve().parent
ROOT=overlay.ROOT
OUT=overlay.OUT
SDK_REV='f50092f2d22238c6be4b6c159a1ad71a4ea68678'
CXX=Path('/home/wangwy/llama/platforms/cva6-qemu/tools/bin/riscv64-linux-g++')
CC=CXX.with_name('riscv64-linux-gcc')
OUTPUT=None

class OverlayTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory() if OUTPUT is None else None
        cls.out=Path(cls.temp.name) if cls.temp else OUTPUT
        if OUTPUT: cls.out.mkdir()
        cls.tree,cls.manifest=overlay.materialize(cls.out/'inputs')
        raw=subprocess.check_output(['git','-C',str(ROOT),'archive',SDK_REV,'software/akv'])
        (cls.out/'sdk.tar').write_bytes(raw)
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive: archive.extractall(cls.out/'sdk',filter='data')
        cls.sdk=cls.out/'sdk/software/akv'
        cls.arch=cls.tree/'ggml/src/ggml-cpu/arch/riscv'
        cls.commands=[];cls.pins=json.loads((cls.out/'inputs/source-pins.json').read_text())
        for p in (cls.out/'sdk').rglob('*'):
            if p.is_file(): cls.pins[str(p)]=overlay.sha(p)
        cls.pins[str(cls.out/'sdk.tar')]=overlay.sha(cls.out/'sdk.tar')

    @classmethod
    def tearDownClass(cls):
        if cls.temp: cls.temp.cleanup()

    def run_cmd(self,label,args,timeout=120,cwd=None):
        args=list(map(str,args));cwd=cwd or self.out
        p=subprocess.run(args,cwd=cwd,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=timeout,
            env=dict(PATH='/usr/bin:/bin',HOME='/home/wangwy',LC_ALL='C'))
        (self.out/(label+'.log')).write_bytes(p.stdout)
        self.commands.append(dict(label=label,argv=args,cwd=str(cwd),returncode=p.returncode,timeout=timeout))
        tool=Path(shutil.which(args[0]) or args[0]).resolve();self.pins[str(tool)]=overlay.sha(tool)
        self.assertEqual(p.returncode,0,p.stdout.decode(errors='replace'))
        return p.stdout.decode()

    def includes(self):
        return ['-I'+str(p) for p in (self.arch,self.sdk/'include',self.sdk/'experimental',
            self.tree/'ggml/include',self.tree/'ggml/src',self.tree/'ggml/src/ggml-cpu')]

    def test_adapted06_exact_reviewed_intermediate(self):
        self.assertEqual(overlay.sha(self.out/'inputs/auto_reference/akv.cpp'),overlay.AUTO_AKV)
        self.assertEqual(self.manifest['llama_revision'],overlay.REV)
        text=(self.tree/overlay.CMAKE).read_text()
        original=subprocess.check_output(['git','-C',str(overlay.LLAMA),'show',overlay.REV+':'+overlay.CMAKE]).decode()
        # Strip only the registered additions: the original 54-line quantKV and
        # all unrelated feature/build controls remain byte-identical.
        text=text.split('\n',1)[1].replace((HERE/'resident.cmake').read_text(),'')
        self.assertEqual(text,original)

    def test_default_off_and_source_counter_contract(self):
        text=(self.tree/overlay.CMAKE).read_text()
        self.assertTrue(text.startswith('option(GGML_RISCV_AKV_RESIDENT '))
        self.assertIn('default deny)" OFF)',text.split('\n',1)[0])
        self.assertNotIn('features_v2',text)
        src=(self.arch/'akv.cpp').read_text()
        entry=src[src.index('bool ggml_riscv_akv_flash_attn('):]
        self.assertLess(entry.index('ggml_akv_platform_entry_v1'),entry.index('emulation_enabled'))
        self.assertLess(entry.index('gate!=AKV_PLATFORM_READY'),entry.index('stage5_native('))
        inc=(self.arch/'resident.inc').read_text()
        self.assertLess(inc.index('akv_resident_platform_group_v1'),inc.index('convert(source'))
        self.assertLess(inc.index('akv_resident_platform_start_v1'),inc.index('convert(source'))
        self.assertNotIn('akv_experimental_attention_execute_v2_features',inc)

    def test_host_real_entry_counted_routes_no_numeric_claim(self):
        objs=[]
        for source in (self.arch/'platform.c',self.arch/'entry.c',self.sdk/'src/akv_runtime.c',self.sdk/'src/akv_features.c'):
            obj=self.out/(source.stem+'.host.o');objs.append(obj)
            self.run_cmd('host-'+source.stem,['/usr/bin/gcc','-O2','-ffunction-sections','-fdata-sections',
                '-fno-tree-vectorize','-fno-tree-slp-vectorize',*self.includes(),'-c',source,'-o',obj])
        exe=self.out/'host-control'
        self.run_cmd('host-control-compile',['/usr/bin/g++','-std=c++17','-O2','-UNDEBUG','-fno-fast-math',
            '-ffp-contract=off','-ffunction-sections','-fdata-sections','-DGGML_AKV_RESIDENT=1',
            '-DAKV_NATIVE_AUTO_PAIR_POLICY=1','-DGGML_USE_RISCV_QUANT_KV=1',*self.includes(),HERE/'host_control.cpp',*objs,
            '-Wl,--gc-sections','-lm','-pthread','-o',exe])
        self.assertEqual(self.run_cmd('host-control-run',[exe]),
            'GGML_CONTROL_PASS resident_groups=2 native_groups=4 actual_numeric=0 native_execution=0\n')

    def test_gnu_off_object_identical_to_adapted_baseline(self):
        common=[CXX,'-std=c++17','-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-O2','-fno-fast-math',
            '-ffp-contract=off','-DAKV_NATIVE_AUTO_PAIR_POLICY=1',
            '-ffile-prefix-map='+str(self.arch)+'=SOURCE',
            '-ffile-prefix-map='+str(self.out/'inputs/auto_reference')+'=SOURCE',*self.includes(),'-c']
        # Same basename/relative source path avoids source-name noise in .file.
        ref=self.out/'inputs/auto_reference/akv.cpp'
        for quant in (0,1):
            off=self.out/('off'+str(quant)+'.o');base=self.out/('base'+str(quant)+'.o')
            flags=['-DGGML_USE_RISCV_QUANT_KV=1'] if quant else []
            self.run_cmd('gnu-off'+str(quant),[*common,*flags,self.arch/'akv.cpp','-o',off])
            self.run_cmd('gnu-base'+str(quant),[*common,*flags,ref,'-o',base])
            self.assertEqual(off.read_bytes(),base.read_bytes())

    def test_gnu_on_object_and_scalar_entry(self):
        obj=self.out/'on.o'
        self.run_cmd('gnu-on',[CXX,'-std=c++17','-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-O2',
            '-fno-fast-math','-ffp-contract=off','-fno-tree-vectorize','-fno-tree-slp-vectorize',
            '-DGGML_AKV_RESIDENT=1','-DAKV_NATIVE_AUTO_PAIR_POLICY=1',*self.includes(),'-c',self.arch/'akv.cpp','-o',obj])
        gate=self.out/'entry.gnu.o'
        self.run_cmd('gnu-entry',[CC,'-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-O2','-ffreestanding','-fno-builtin',
            '-fno-tree-vectorize','-fno-tree-slp-vectorize',*self.includes(),'-c',self.arch/'entry.c','-o',gate])
        dis=self.run_cmd('gnu-entry-disasm',[CC.with_name('riscv64-linux-objdump'),'-d','-M','no-aliases,numeric',gate])
        words=[int(x,16) for x in re.findall(r'(?m)^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s',dis)]
        self.assertTrue(words)
        self.assertFalse(any(w&127 in (0x07,0x27,0x43,0x47,0x4b,0x4f,0x53,0x57,0x5b) for w in words))
        symbols=self.run_cmd('gnu-on-nm',[CC.with_name('riscv64-linux-nm'),'-C',obj])
        self.assertIn(' U akv_experimental_attention_execute_v2_native',symbols)
        self.assertIn(' T ggml_akv_resident_snapshot_v1',symbols)
        actual=self.run_cmd('gnu-on-disasm',[CC.with_name('riscv64-linux-objdump'),'-dr','-M','no-aliases,numeric',obj])
        entry=actual.split('<_Z25ggml_riscv_akv_flash_attnPK19ggml_compute_paramsP11ggml_tensor>:',1)[1]
        before_gate=entry.split('R_RISCV_CALL_PLT\tggml_akv_platform_entry_v1',1)
        self.assertEqual(len(before_gate),2)
        words=[int(x,16) for x in re.findall(r'(?m)^\s*[0-9a-f]+:\s+([0-9a-f]{8})\s',before_gate[0])]
        self.assertFalse(any(w&127 in (0x07,0x27,0x43,0x47,0x4b,0x4f,0x53,0x57,0x5b) for w in words))
        off=self.out/'off-nm.o'
        self.run_cmd('gnu-off-nm-compile',[CXX,'-std=c++17','-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-O2',
            *self.includes(),'-c',self.arch/'akv.cpp','-o',off])
        self.assertNotIn('akv_experimental_attention_execute',self.run_cmd('gnu-off-nm',[CC.with_name('riscv64-linux-nm'),off]))

    def test_gnu_cmake_on_plumbing_and_off_default(self):
        parent=self.out/'cmake-parent';parent.mkdir()
        (parent/'CMakeLists.txt').write_text('cmake_minimum_required(VERSION 3.16)\nproject(stage5 LANGUAGES C CXX)\n'
            'add_subdirectory("'+str(self.tree/'ggml')+'" ggml-build)\n')
        build=self.out/'cmake-build'
        self.run_cmd('cmake-on',['/usr/bin/cmake','-S',parent,'-B',build,
            '-DCMAKE_SYSTEM_NAME=Linux','-DCMAKE_SYSTEM_PROCESSOR=riscv64','-DCMAKE_C_COMPILER='+str(CC),
            '-DCMAKE_CXX_COMPILER='+str(CXX),'-DCMAKE_EXPORT_COMPILE_COMMANDS=ON','-DBUILD_SHARED_LIBS=OFF',
            '-DGGML_NATIVE=OFF','-DGGML_OPENMP=OFF','-DGGML_RVV=ON','-DGGML_RV_ZFH=ON','-DGGML_RV_ZVFH=ON',
            '-DGGML_RISCV_AKV=ON','-DGGML_RISCV_AKV_RESIDENT=ON','-DGGML_RISCV_AKV_RUNTIME_DIR='+str(self.sdk)])
        commands=json.loads((build/'compile_commands.json').read_text())
        files=[Path(c['file']).name for c in commands]
        for name in ('entry.c','platform.c','read_state.S','qk.S','pv.S'): self.assertEqual(files.count(name),1)
        self.assertNotIn('pv_prepare.S',files)
        for c in commands:
            if Path(c['file']).name in ('akv.cpp','platform.c','entry.c'):
                self.assertIn('-fno-tree-vectorize',c['command'])
                self.assertIn('-DGGML_AKV_RESIDENT=1',c['command'])
        self.assertTrue(all('FEATURES_V2=1' not in c['command'] for c in commands))
        # Compile only the integration closure with its actual generated flags,
        # not a whole model/library build and not hand-written approximations.
        selected={'akv.cpp','akv_v2_native_riscv.c','entry.c','platform.c','read_state.S','qk.S','pv.S'}
        compiled=[]
        for c in commands:
            name=Path(c['file']).name
            if name not in selected: continue
            argv=shlex.split(c['command']);obj=self.out/(name+'.cmake.o')
            argv[argv.index('-o')+1]=str(obj)
            self.run_cmd('cmake-object-'+name,argv,cwd=Path(c['directory']))
            compiled.append(name)
        self.assertEqual(set(compiled),selected)
        core=self.run_cmd('cmake-core-nm',[CC.with_name('riscv64-linux-nm'),self.out/'akv_v2_native_riscv.c.cmake.o'])
        self.assertIn(' T akv_experimental_attention_execute_v2_native',core)

    def test_production_supported_bits_still_zero_and_no_provider(self):
        abi=(self.sdk/'include/akv/akv_abi.h').read_text()
        self.assertIn('#define AKV_RESIDENT_QK_SUPPORTED 0u',abi)
        self.assertIn('#define AKV_RESIDENT_PV_SUPPORTED 0u',abi)
        self.assertIn('return NULL;',(self.arch/'platform.c').read_text())
        self.assertNotIn('getenv',(self.arch/'entry.c').read_text())

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);p.add_argument('--output',type=Path)
    args=p.parse_args()
    if args.output:
        OUTPUT=args.output.absolute()
        if OUTPUT!=OUTPUT.resolve() or OUTPUT.parent!=OUT or OUTPUT.exists() or not OUTPUT.name.startswith('stage5_ggml_overlay_host_'):
            raise ValueError('Fresh direct signoff host output required')
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(OverlayTests))
    if OUTPUT and OUTPUT.exists():
        pins=getattr(OverlayTests,'pins',{})
        for p,digest in pins.items():
            if overlay.sha(p)!=digest: raise ValueError('Source drift: '+p)
        (OUTPUT/'source-pins.json').write_text(json.dumps(pins,indent=2,sort_keys=True)+'\n')
        (OUTPUT/'commands.json').write_text(json.dumps(getattr(OverlayTests,'commands',[]),indent=2)+'\n')
        report=dict(state='HOST_GNU_CONTROL_PASS_NO_NATIVE' if result.wasSuccessful() else 'FAIL',
            tests=result.testsRun,native_execution=False,numerical_checked=False,provider_registered=False,
            source_pins_sha256=overlay.sha(OUTPUT/'source-pins.json'),
            artifacts={str(p):overlay.sha(p) for p in OUTPUT.rglob('*') if p.is_file()})
        (OUTPUT/'result.json').write_text(json.dumps(report,indent=2)+'\n')
    raise SystemExit(not result.wasSuccessful())
