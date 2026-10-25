#!/usr/bin/env python3
"""Prepare two private SoC source lists and one GNU ELF recipe. Executes no tools."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
sys.path.insert(0,str(HERE))


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec); sys.modules[name]=mod; spec.loader.exec_module(mod)
    return mod


render=load('reader_fault_prepare_render',HERE/'render.py')
wave=load('reader_fault_prepare_profile',HERE/'profile.py')


def prepare(snapshot, fixture, out):
    integ=HERE.parent/'shared_reader_integration'
    latency=load('reader_fault_latency_inventory',HERE.parent/'legacy_latency/run.py')
    soc=load('reader_fault_soc_recipe',integ/'build_soc.py')
    sys.path.insert(0,str(HERE.parent/'reader_handoff'))
    hand=load('reader_fault_original_build_check',HERE.parent/'reader_handoff/run.py')
    tools=latency.tools
    require=latency.checker.require
    report=latency.storage.validate_snapshot(snapshot)
    original,fixture_pins=hand.checked_build(fixture)
    require(not out.exists() and not out.is_relative_to(snapshot) and
            not out.is_relative_to(fixture),'Fresh independent preparation required')
    manifest_path=Path(report['baseline_manifest'])
    accepted=manifest_path.parent
    accepted_manifest=json.loads(manifest_path.read_text())
    command,extras=soc.mapped_command(soc.accepted_command((accepted/'comp.vcs.log').read_text()),report)
    require('-debug_access+all' in command and '+define+ARA_VERIFY_UVM_CVXIF' in command,
            'Keep debug and actual UVM monitors')
    mapping={report['source_mapping'][str(ROOT/p)]:str(ROOT/p) for p in latency.MODULES}
    for p in mapping.values():
        require(report['input_pins'].get(p)==tools.digest(Path(p)),'Canonical original drift')
    lists=latency.paired_lists(Path(report['filelist']).read_text(),mapping)
    pins=latency.storage.merge_pins(report['input_pins'],report['artifact_pins'],fixture_pins)
    own=list(HERE.glob('*.py'))+list(HERE.glob('*.sv'))+[HERE/'README.md',render.MAIN,render.ASM,
        fixture/'commands.json',manifest_path,accepted/'comp.vcs.log',accepted/'simulator.conf',
        Path(sys.executable).resolve()]
    for module in tuple(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if name and Path(name).resolve().is_relative_to(ROOT): own.append(Path(name).resolve())
    pins=latency.storage.merge_pins(pins,{str(p):tools.digest(p) for p in own})
    tools.verify(pins)
    out.mkdir(parents=True)
    tools.save(out/'source-pins.json',pins)
    transformed=render.render_main(render.MAIN.read_text())
    require(render.restore_main(transformed)==render.MAIN.read_text(),'Program inverse failed')
    (out/'main.c').write_text(transformed)
    commands=json.loads((fixture/'commands.json').read_text())
    templates=[x['argv'] for x in commands if '-c' in x['argv'] and str(render.MAIN) in x['argv']]
    links=[x['argv'] for x in commands if '-nostdlib' in x['argv']]
    require(len(templates)==len(links)==1,'Ambiguous GNU recipe')
    cc=list(templates[0]); cc[cc.index(str(render.MAIN))]=str(out/'main.c')
    cc[cc.index('-o')+1]=str(out/'main.o')
    link=list(links[0]); require(link.count(str(fixture/'fixture-0.o'))==1,'Missing original main object')
    link[link.index(str(fixture/'fixture-0.o'))]=str(out/'main.o')
    link[link.index('-o')+1]=str(out/'reader_fault.elf')
    link=['-Wl,-Map='+str(out/'link.map') if a.startswith('-Wl,-Map=') else a for a in link]
    for token in link:
        if token.endswith(('.o','.a')) and token!=str(out/'main.o'):
            require(pins.get(token)==tools.digest(Path(token)),'Reused object not hash-pinned')
    recipes={}
    for mode,text in zip(('baseline','candidate'),lists):
        shared=mode=='candidate'; path=out/(mode+'_vlsu.sv')
        old=Path(report['source_mapping'][str(ROOT/latency.MODULES[2])]) if shared else ROOT/latency.MODULES[2]
        path.write_text(render.render_vlsu(old.read_text(),shared))
        text=render.replace_once(text,str(old)+'\n',str(path)+'\n')
        text+='\n'+str(HERE/'reader_fault_cut.sv')+'\n'+str(HERE/'probe.sv')+'\n'
        filelist=out/(mode+'.f'); filelist.write_text(text)
        current=list(command)
        current[current.index(report['filelist'])]=str(filelist)
        # Existing recipe uses relative build outputs; each profile gets its own cwd.
        work=out/mode; work.mkdir(); (work/'incremental_db').mkdir()
        require(not any(a.startswith('-Mdir=/') for a in current),'Absolute inherited build directory')
        require('-o' not in current or not Path(current[current.index('-o')+1]).is_absolute(),
                'Absolute inherited image output')
        tools.save(out/(mode+'-profile.json'),wave.profile(shared))
        (out/(mode+'-probe.tcl')).write_text(wave.script(shared))
        recipes[mode]=dict(argv=current,cwd=str(work),extra_sources=extras,
                           filelist=str(filelist),vlsu=str(path),
                           capture=str(out/(mode+'-profile.json')),
                           script=str(out/(mode+'-probe.tcl')))
    # The full copied source/header closure is pinned by the snapshot. New sources
    # and filelists are additional artifacts, not silently substituted old receipts.
    tools.verify(pins)
    tools.save(out/'source-pins.json',pins)
    result=dict(state='PREPARED_NOT_COMPILED_NOT_EXECUTED',schema='reader_held_ar_fault_v1',
        snapshot=str(snapshot),fixture_predecessor=str(fixture),source_pins_sha256=tools.digest(out/'source-pins.json'),
        recipes=recipes,gnu_recipe=[dict(argv=cc,cwd=str(out)),dict(argv=link,cwd=str(out))],
        reused_objects='All original startup/libc/probe assembly objects; only successor main recompiled',
        target_resolution='After GNU link, require exactly one weights symbol of size 432, aligned64, first288B within one4KiB page; pass its address as +READER_FAULT_TARGET and bind it to UART target',
        expected_commands=71,expected_reader_fault=3,expected_trap_cause=5,
        wall_timeout_seconds=900,scenario_cycle_bound=4096,capture_bound_ns=250000,
        required_checks=['fresh image/source inventory pre/post','exact original UVM sources and flags',
                         'raw successor transcript','independent wave AXI ledgers and reader-held condition',
                         'unfiltered ara_verify.uvm_dut --require-events --require-backend --require-axi --require-axi-write',
                         'FSDB exporter identities and complete signal metadata','ELF/image/result hash binding'],
        artifact_pins={str(p):tools.digest(p) for p in out.iterdir() if p.is_file()},
        production_modified=False,simulation_launched=False,mmu_covered=False)
    tools.save(out/'prepare.json',result)
    return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--fixture-build',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    output=a.output.resolve()
    fresh=not output.exists()
    try:
        print(prepare(a.snapshot.resolve(strict=True),a.fixture_build.resolve(strict=True),output)['state'])
    except BaseException as exc:
        if fresh and output.exists():
            (output/'prepare-failure.json').write_text(json.dumps(
                dict(state='PREPARATION_FAIL',simulation_launched=False,error=repr(exc)),indent=2)+'\n')
        raise
