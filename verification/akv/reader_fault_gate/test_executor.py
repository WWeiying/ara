"""Independent synthetic identity/recipe mutations. Never invokes GNU or VCS."""
import copy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import executor_common as c


def load(name,file):
    spec=importlib.util.spec_from_file_location(name,HERE/file)
    mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod; spec.loader.exec_module(mod)
    return mod


b=load('held_ar_build_tests','build.py')
r=load('held_ar_run_tests','run.py')
ALLOC=[dict(name='.bss',address=0x80000000,bytes=0x10000,nobits=True)]


class SocInventoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.source=self.root/'snapshot/source'; self.source.mkdir(parents=True)
        self.accepted=self.root/'verification/out/qbacc-soc-20261023-02/build/sim/vcs_source_manifest.json'
        self.original=self.root/'verification/out/qbacc-soc-20261023-02/build/hardware-build/vcs/bender_script_default'
        self.filelist=self.root/'actual.f'
        self.snapshot=self.source.parent/'manifest.json'
        self.hashes={}; mapping={}; original_pins={}; artifact_pins={}
        for i,relative in enumerate(c.SOC_REPEAT_HASHES):
            old,new=self.root/relative,self.source/relative
            for path in (old,new):
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(f'module fixture{i}; endmodule\n')
            self.hashes[relative]=c.digest(old)
            mapping[str(old)]=str(new)
            original_pins[str(old)]=artifact_pins[str(new)]=c.digest(old)
        self.extra=self.source/'unique.sv'; self.extra.write_text('module unique; endmodule\n')
        old=list(mapping); new=list(mapping.values())
        self.lines=['+define+EXAMPLE',new[0],str(self.extra),new[1],new[0],new[1]]
        self.filelist.write_text('\n'.join(self.lines)+'\n')
        self.original.parent.mkdir(parents=True)
        self.original.write_text('\n'.join([old[0],old[1],old[0],old[1]])+'\n')
        original_pins[str(self.original)]=c.digest(self.original)
        self.accepted.parent.mkdir(parents=True)
        c.save(self.accepted,dict(schema_version=1,repo_root=str(self.root),filelist=str(self.original),
                                 files=[dict(path=p,sha256=h) for p,h in original_pins.items()]))
        original_pins[str(self.accepted)]=c.digest(self.accepted)
        c.save(self.snapshot,dict(baseline_manifest=str(self.accepted),input_pins=original_pins,
                                 source_mapping=mapping,artifact_pins=artifact_pins))
        for name,value in (('ROOT',self.root),('SOC_REPEAT_HASHES',self.hashes)):
            context=patch.object(c,name,value); context.start(); self.addCleanup(context.stop)

    def admit(self):
        return c.soc_repeat_admission(self.filelist,self.source)

    def test_exact_repeats(self):
        rows,metadata=self.admit()
        self.assertEqual({r['canonical_relative_path']:r['sha256'] for r in rows},self.hashes)
        self.assertTrue(all(r['count']==2 for r in rows))
        self.assertEqual(metadata,[self.snapshot,self.accepted,self.original])

    def test_count_name_path_and_unlisted_duplicates(self):
        original=self.filelist.read_bytes()
        replacement=self.source/'elsewhere/renamed.sv'; replacement.parent.mkdir()
        replacement.write_bytes(Path(self.lines[1]).read_bytes())
        same_name=self.source/'elsewhere'/Path(self.lines[1]).name
        same_name.write_bytes(replacement.read_bytes())
        cases=[self.lines[:-1],self.lines+[self.lines[1]],self.lines+[str(self.extra)],
               [str(replacement) if x==self.lines[1] else x for x in self.lines],
               [str(same_name) if x==self.lines[1] else x for x in self.lines]]
        for lines in cases:
            with self.subTest(lines=lines),self.assertRaises((ValueError,RuntimeError)):
                self.filelist.write_text('\n'.join(lines)+'\n'); self.admit()
        self.filelist.write_bytes(original)
        self.admit()

    def test_original_and_mapped_source_hash(self):
        relative=next(iter(self.hashes))
        for path in (self.root/relative,self.source/relative):
            original=path.read_bytes(); path.write_bytes(original+b'// changed\n')
            with self.subTest(path=path),self.assertRaises((ValueError,RuntimeError)): self.admit()
            path.write_bytes(original)

    def test_metadata_mapping_hash_and_original_count(self):
        snapshot=json.loads(self.snapshot.read_text()); manifest=json.loads(self.accepted.read_text())
        old=str(self.root/next(iter(self.hashes))); new=str(self.source/next(iter(self.hashes)))
        mutations=[('source_mapping',old,new+'.elsewhere'),('input_pins',old,'0'*64),
                   ('artifact_pins',new,'0'*64)]
        for key,path,value in mutations:
            changed=copy.deepcopy(snapshot); changed[key][path]=value; c.save(self.snapshot,changed)
            with self.subTest(key=key),self.assertRaises((ValueError,RuntimeError)): self.admit()
        c.save(self.snapshot,snapshot)
        for change in (dict(filelist=str(self.filelist)),dict(repo_root=str(self.source)),
                       dict(files=manifest['files']+[manifest['files'][0]])):
            c.save(self.accepted,{**manifest,**change})
            changed=copy.deepcopy(snapshot); changed['input_pins'][str(self.accepted)]=c.digest(self.accepted)
            c.save(self.snapshot,changed)
            with self.subTest(change=change),self.assertRaises((ValueError,RuntimeError)): self.admit()
        c.save(self.accepted,manifest); c.save(self.snapshot,snapshot)
        self.original.write_text(self.original.read_text()+old+'\n')
        manifest['files'][-1]['sha256']=c.digest(self.original)
        c.save(self.accepted,manifest)
        snapshot['input_pins'][str(self.original)]=c.digest(self.original)
        snapshot['input_pins'][str(self.accepted)]=c.digest(self.accepted)
        c.save(self.snapshot,snapshot)
        with self.assertRaisesRegex((ValueError,RuntimeError),'duplicate set/count'): self.admit()

    def test_inventory_adapter_preserves_compiler_bytes_and_order(self):
        before=self.filelist.read_bytes(); seen=[]
        def collect(path,root,extras):
            paths=[path,*extras]+[Path(x) for x in path.read_text().splitlines() if x.startswith('/')]
            return [dict(path=str(p),sha256=c.digest(p)) for p in sorted(set(paths))]
        def graph(path,extras,root):
            seen.extend(path.read_text().splitlines())
            self.assertEqual(len(seen),len(set(seen)))
            return {r['path']:r['sha256'] for r in collect(path,root,extras)}
        with patch.object(c.latency,'graph_pins',side_effect=graph),\
             patch.object(c.latency.tools,'collect',side_effect=collect):
            manifest=c.graph_manifest(dict(filelist=str(self.filelist),extra_sources=[]),self.source)
        self.assertEqual(seen,self.lines[:4])
        self.assertEqual(self.filelist.read_bytes(),before)
        self.assertEqual(manifest['filelist'],str(self.filelist))
        self.assertEqual(len(manifest['admitted_repeats']),2)
        self.assertIn(dict(path=str(self.filelist),sha256=c.digest(self.filelist)),manifest['files'])


class ExecutorTests(unittest.TestCase):
    def test_exact_weights_and_allocation(self):
        good='other T 80000000 4\nweights b 80004000 1b0\n'
        self.assertEqual(c.parse_weights(good,ALLOC)['address'],0x80004000)
        for bad in ('',good+good,good.replace('1b0','1b1'),good.replace('80004000','80004002'),
                    good.replace('80004000','80004fc0'),good.replace('80004000','80ff0000'),
                    good.replace('weights b','weights U'),good.replace('1b0','1b0 extra')):
            with self.subTest(bad=bad),self.assertRaises((ValueError,RuntimeError)):
                c.parse_weights(bad,ALLOC)
        with self.assertRaises((ValueError,RuntimeError)): c.parse_weights(good,[])
        for bad in ([],[dict(address=0x7fffffff,bytes=8)],[dict(address=0x80ff0000,bytes=1)]):
            with self.assertRaises((ValueError,RuntimeError)): c.check_sections(bad)

    def test_gnu_recipe_preserves_flags_objects_source(self):
        p=Path('/prepared'); o=Path('/fresh/gnu')
        flags=['-ffreestanding','-fno-builtin','-fno-tree-loop-distribute-patterns','-Werror']
        cc=['/tool/riscv64-unknown-elf-gcc',*flags,'-c',str(p/'main.c'),'-o',str(p/'main.o')]
        link=[cc[0],str(p/'main.o'),'/sealed/probe.o','-Wl,-Map='+str(p/'link.map'),'-o',str(p/'reader_fault.elf')]
        report=dict(gnu_recipe=[dict(argv=cc),dict(argv=link)])
        newcc,newlink=b.gnu_commands(report,p,o)
        self.assertEqual(newcc[:-1],cc[:-1])
        self.assertIn('/sealed/probe.o',newlink)
        self.assertIn(str(p/'main.c'),newcc)
        self.assertEqual(newlink[-1],str(o/'reader_fault.elf'))
        bad=copy.deepcopy(report); bad['gnu_recipe'][0]['argv'].remove('-ffreestanding')
        with self.assertRaises((ValueError,RuntimeError)): b.gnu_commands(bad,p,o)

    def test_image_inventory_contains_manifest_config_and_libraries(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); (p/'simv').write_bytes(b'image'); (p/'simv').chmod(0o700)
            (p/'simulator.conf').write_text('config')
            (p/'vcs_source_manifest.json').write_text('{}')
            (p/'simv.daidir').mkdir(); (p/'simv.daidir/a.so').write_bytes(b'library')
            files=c.s.image_files(p/'simv')
            self.assertEqual({x.name for x in files},{'simv','simulator.conf','vcs_source_manifest.json','a.so'})
            pins=c.s.hashes(files)
            for file in files:
                original=file.read_bytes(); file.write_bytes(original+b'drift')
                with self.subTest(file=file.name),self.assertRaises((ValueError,RuntimeError)):
                    c.s.verify_pins(pins)
                file.write_bytes(original)
            (p/'simulator.conf').unlink()
            with self.assertRaises(RuntimeError): c.s.image_files(p/'simv')

    def test_active_stdout_never_sealed(self):
        for name in ('worker.log','status.json','result.json','build.json'):
            with self.assertRaises((ValueError,RuntimeError)): c.closed_evidence([Path('/tmp')/name])

    def test_new_executor_requires_fresh_preparation(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); own=p/'own'; own.mkdir(); (own/'build.py').write_text('new executor')
            (p/'source-pins.json').write_text('{}')
            report=dict(state='PREPARED_NOT_COMPILED_NOT_EXECUTED',schema='reader_held_ar_fault_v1',
                        expected_commands=71,expected_reader_fault=3,expected_trap_cause=5,
                        capture_bound_ns=250000,recipes=dict(baseline={},candidate={}),
                        source_pins_sha256=c.digest(p/'source-pins.json'))
            c.save(p/'prepare.json',report)
            with patch.object(c,'HERE',own),self.assertRaisesRegex((ValueError,RuntimeError),'fresh preparation'):
                c.checked_prepare(p,c.digest(p/'prepare.json'))

    def test_phase_exit_receipt_does_not_reuse_prior_zero(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); owner=c.Execution(p); owner.state['running_exit_code']=0
            with patch.object(c.hand.Execution,'execute',side_effect=c.StopRequested('test')),\
                    self.assertRaises(c.StopRequested):
                owner.execute(['not-launched'],p/'simulation.log',1,'RUNNING')
            receipt=json.loads((p/'simulation.exit.json').read_text())
            self.assertIsNone(receipt['exit_code'])
            self.assertIn('StopRequested',receipt['error'])

    def test_manifest_changes_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'vcs_source_manifest.json'
            c.save(p,dict(schema_version=1,filelist='/f',repo_root='/root',extra_sources=[],
                          files=[dict(path='/rtl',sha256='a'*64)]))
            with patch.object(c.latency.tools,'collect',return_value=[dict(path='/rtl',sha256='b'*64)]),\
                    self.assertRaises((ValueError,RuntimeError)):
                c.verify_manifest(p)

    def test_full_pair_cannot_hide_one_command_difference(self):
        log=dict(commands=71,trap_tval=0x80004000,records=[dict(seq=i,ar=2,busy_cycles=100) for i in range(71)])
        pair={m:dict(log=copy.deepcopy(log)) for m in c.MODES}
        self.assertEqual(r.compare_pair(pair)['state'],'PASS')
        pair['candidate']['log']['records'][0]['busy_cycles']+=1
        pair['candidate']['log']['records'][1]['busy_cycles']-=1
        checked=r.compare_pair(pair)
        self.assertEqual(checked['state'],'REGRESSION'); self.assertEqual(len(checked['differences']),2)
        pair['candidate']['log']['records'][0]['new_field']=0
        with self.assertRaises((ValueError,RuntimeError)): r.compare_pair(pair)

    def test_capture_and_unfiltered_commands(self):
        profile=dict(signals=[dict(alias='x'),dict(alias='y')])
        meta=dict(edge='negedge',cycle_count=100,present_signals=['x','y'],missing_signals=[])
        r.check_metadata(meta,profile)
        for changed in (dict(edge='posedge'),dict(present_signals=['x','x','y']),dict(cycle_count=0),
                        dict(missing_signals=['y']),dict(present_signals=['x'])):
            with self.assertRaises((ValueError,RuntimeError)): r.check_metadata({**meta,**changed},profile)
        command=r.simulation_command('/simv','/elf',0x80004000,'/probe','/raw.log','/raw.csv')
        self.assertIn('+READER_FAULT_TARGET=80004000',command)
        self.assertIn('+VECTOR_TRACE=/raw.csv',command)
        self.assertIn('+QBS_PERF',command); self.assertIn('+AKV_PERF',command)


if __name__=='__main__': unittest.main()
