#!/usr/bin/env python3
"""Build one GNU ELF and two isolated VCS images; never execute a simulator."""
import argparse
from pathlib import Path
import re
import shlex
import shutil
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
import executor_common as c


def gnu_commands(report,prepared,gnu):
    cc=list(report['gnu_recipe'][0]['argv']); link=list(report['gnu_recipe'][1]['argv'])
    c.require(cc.count(str(prepared/'main.c'))==1 and cc[cc.index('-o')+1]==str(prepared/'main.o'),
              'Unexpected main compile recipe')
    c.require({'-ffreestanding','-fno-builtin','-fno-tree-loop-distribute-patterns','-Werror'}<=set(cc),
              'Bare-metal compile flags weakened')
    cc[cc.index('-o')+1]=str(gnu/'main.o')
    c.require(link.count(str(prepared/'main.o'))==1 and
              link[link.index('-o')+1]==str(prepared/'reader_fault.elf'),'Unexpected link recipe')
    link[link.index(str(prepared/'main.o'))]=str(gnu/'main.o')
    link[link.index('-o')+1]=str(gnu/'reader_fault.elf')
    old='-Wl,-Map='+str(prepared/'link.map')
    c.require(link.count(old)==1,'Missing map output')
    link[link.index(old)]='-Wl,-Map='+str(gnu/'link.map')
    return cc,link


def tool_paths(cc,vcs):
    compiler=Path(cc[0]).resolve(strict=True)
    prefix=Path(cc[0]).name.removesuffix('gcc')
    c.require(prefix=='riscv64-unknown-elf-','Approved GNU toolchain required')
    paths=[Path(cc[0]),compiler,Path(vcs),Path(vcs).resolve(strict=True)]
    paths += [Path(cc[0]).with_name(prefix+tool) for tool in ('nm','objdump')]
    paths += [Path(vcs).resolve().parents[1]/'linux64/bin/vcs1']
    return sorted(set(paths+[p.resolve(strict=True) for p in paths]))


def build(args):
    prepared=args.prepared.resolve(strict=True); out=args.output.resolve()
    c.require(not out.exists() and not out.is_relative_to(prepared) and
              not prepared.is_relative_to(out),'Fresh independent build required')
    report,pins=c.checked_prepare(prepared,args.expected_prepare_sha256)
    c.s.merge_pins(pins,c.own_pins())
    vcs=shutil.which('vcs'); c.require(vcs is not None,'VCS executable unavailable')
    cc,link=gnu_commands(report,prepared,out/'gnu')
    c.s.merge_pins(pins,c.s.hashes(tool_paths(cc,vcs)))
    snapshot=Path(report['snapshot'])
    snapshot_report=c.s.read_json(snapshot/'manifest.json')
    accepted_config=Path(snapshot_report['baseline_manifest']).parent/'simulator.conf'
    config=accepted_config.read_text()
    for line in ('sim_l2_bytes=16777216','nr_lanes=4','vlen=1024','qbs_enabled=1',
                 'akv_v2_enabled=1','verify_axi_delay=0'):
        c.require(config.splitlines().count(line)==1,'Wrong original SoC configuration: '+line)
    graphs={mode:c.graph_manifest(report['recipes'][mode],snapshot/'source') for mode in c.MODES}
    for graph in graphs.values(): c.s.merge_pins(pins,{r['path']:r['sha256'] for r in graph['files']})
    c.s.verify_pins(pins)
    out.mkdir(parents=True); (out/'gnu').mkdir()
    owner=c.Execution(out); owner.state.update(prepared=str(prepared),execution='NOT_RUN'); owner.save()
    try:
        c.save(out/'source-pins.json',pins)
        if args.preflight_only:
            c.save(out/'preflight.json',dict(state='BUILD_PREFLIGHT_ONLY',execution='NOT_RUN',
                prepared=str(prepared),prepare_sha256=args.expected_prepare_sha256,
                source_pins_sha256=c.digest(out/'source-pins.json')))
            owner.state['state']='BUILD_PREFLIGHT_ONLY'
            return

        def identity():
            c.checked_prepare(prepared,args.expected_prepare_sha256)
            c.s.verify_pins(pins)
            for mode in c.MODES:
                c.require(graphs[mode]==c.graph_manifest(report['recipes'][mode],snapshot/'source'),
                          'VCS graph drift')

        gnu=out/'gnu'; compiler=cc[0]
        # Bind the actual multilib and compiler subprocesses before compiling.
        arch=[a for a in cc if a.startswith(('-march=','-mabi='))]
        for kind,name in (('prog','cc1'),('prog','as'),('prog','ld'),('prog','collect2'),
                          ('file','libgcc.a'),('file','libm.a')):
            log=gnu/('tool-'+name+'.log')
            owner.execute([compiler,*arch,f'-print-{kind}-name={name}'],log,30,'TOOL_IDENTITY')
            raw=log.read_text().strip()
            path=Path(raw) if Path(raw).is_absolute() else Path(shutil.which(raw) or gnu/raw)
            c.require(path.is_file(),'Unresolved actual GNU component: '+raw)
            c.s.merge_pins(pins,c.s.hashes([path,path.resolve(strict=True)]))
        excluded={cc.index('-c'),cc.index('-o'),cc.index('-o')+1}
        deps=[x for i,x in enumerate(cc) if i not in excluded]+['-M','-MT','main.o']
        owner.execute(deps,gnu/'dependencies.log',180,'GNU_DEPENDENCIES')
        deptext=(gnu/'dependencies.log').read_text()
        c.require(deptext.startswith('main.o:'),'Malformed GNU dependency output')
        headers=[Path(p).resolve(strict=True) for p in shlex.split(deptext.replace('\\\n',' ').split(':',1)[1])]
        c.s.merge_pins(pins,c.s.hashes(headers))
        c.save(out/'source-pins.json',pins)
        identity()
        owner.execute(cc,gnu/'compile.log',180,'GNU_COMPILE')
        owner.execute(link,gnu/'link.log',180,'GNU_LINK')
        elf=gnu/'reader_fault.elf'
        nm=Path(compiler).with_name('riscv64-unknown-elf-nm')
        objdump=Path(compiler).with_name('riscv64-unknown-elf-objdump')
        owner.execute([nm,'-S','--defined-only','--format=posix',elf],gnu/'nm.log',30,'GNU_NM')
        owner.execute([objdump,'-d',elf],gnu/'disassembly.log',30,'GNU_OBJDUMP')
        allocated=c.sections.alloc_sections(elf); c.check_sections(allocated)
        weights=c.parse_weights((gnu/'nm.log').read_text(),allocated)
        disassembly=(gnu/'disassembly.log').read_text()
        for name in ('main','rh_trap_handler','rh_qbs_site','rh_qbs_then_akv','rh_akv_load','rh_rvv_copy_add'):
            c.require('<'+name+'>:' in disassembly,'Missing actual probe function '+name)
        c.require('qbs_ref_execute' not in disassembly and 'archived_main' not in disassembly and
                  all(code in disassembly for code in ('00b5045b','0005385b','00b5605b','0000505b')),
                  'Unexpected fallback/reference or missing native instructions')
        identity()
        images={}
        closed=[p for p in gnu.iterdir() if p.is_file()]
        for mode in c.MODES:
            work=out/mode; work.mkdir(); (work/'incremental_db').mkdir()
            argv=list(report['recipes'][mode]['argv']); argv[0]=vcs
            c.require(argv.count('-f')==1 and argv[argv.index('-f')+1]==str(prepared/(mode+'.f')),
                      'Wrong VCS graph')
            c.save(work/'vcs_source_manifest.json',graphs[mode])
            (work/'simulator.conf').write_text(config)
            identity()
            owner.execute(argv,work/'compile.console.log',1800,'VCS_'+mode.upper())
            text=(work/'comp.vcs.log').read_text()
            admission=c.check_soc_compile(text,0,argv,snapshot/'source')
            c.save(work/'compile-admission.json',admission)
            c.verify_manifest(work/'vcs_source_manifest.json')
            simv=work/'simv'; image=c.s.hashes(c.s.image_files(simv))
            owner.execute(['bash',c.ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh',
                           work,elf],work/'image-contract.log',180,'L2_'+mode.upper())
            c.require(c.s.hashes(c.s.image_files(simv))==image,'Image changed after compile')
            images[mode]=dict(simv=str(simv),pins=image)
            closed += [p for p in work.iterdir() if p.is_file() and p.name in
                       ('comp.vcs.log','compile.console.log','compile.console.command.json',
                        'compile.console.exit.json','compile-admission.json','image-contract.log',
                        'image-contract.command.json','image-contract.exit.json')]
            identity()
        c.s.verify_pins(pins)
        artifacts=c.closed_evidence([out/'source-pins.json',*closed])
        for image in images.values(): c.s.merge_pins(artifacts,image['pins'])
        c.save(out/'build.json',dict(state=c.BUILD_STATE,execution='NOT_RUN',post_pins_match=True,
            prepared=str(prepared),prepare_sha256=args.expected_prepare_sha256,
            source_pins_sha256=c.digest(out/'source-pins.json'),artifact_pins=artifacts,
            elf=str(elf),elf_sha256=c.digest(elf),weights=weights,sections=allocated,images=images,
            one_elf_for_both=True,production_modified=False,mmu_covered=False))
        owner.state['state']=c.BUILD_STATE
    except BaseException as exc:
        c.finish_failure(owner,out,exc)
        raise
    finally:
        owner.state['child_pid']=None; owner.save()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--prepared',type=Path,required=True)
    p.add_argument('--expected-prepare-sha256',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--preflight-only',action='store_true')
    c.install_signals(); build(p.parse_args())
