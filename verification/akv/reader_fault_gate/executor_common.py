"""Identity and bounded foreground execution shared by new build/run workers."""
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import signal
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]


def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec)
    sys.modules[name]=mod; spec.loader.exec_module(mod)
    return mod


prep=load('held_ar_preparation',HERE/'prepare.py')
latency=load('held_ar_inventory',HERE.parent/'legacy_latency/run.py')
sys.path.insert(0,str(HERE.parent/'reader_handoff'))
hand=load('held_ar_handoff_interfaces',HERE.parent/'reader_handoff/run.py')
check=load('held_ar_semantic_checker',HERE/'check.py')
sections=load('held_ar_elf_sections',HERE.parent/'refill_overlap_probe/build.py')
s=hand.s
require=s.require
digest=s.digest
save=s.atomic_json
MODES=('baseline','candidate')
BUILD_STATE='READER_HELD_AR_BUILT_NOT_EXECUTED'


class StopRequested(RuntimeError):
    pass


def install_signals():
    def stop(sig,_frame):
        raise StopRequested(f'Stop requested: {sig}')
    for sig in (signal.SIGINT,signal.SIGTERM): signal.signal(sig,stop)


class Execution(hand.Execution):
    def __init__(self,out):
        super().__init__(out)
        for key in ('GCC_EXEC_PREFIX','COMPILER_PATH','LIBRARY_PATH','CPATH',
                    'C_INCLUDE_PATH','CPLUS_INCLUDE_PATH'):
            self.env.pop(key,None)

    def execute(self,argv,log,timeout,phase):
        require(type(timeout) is int and 1<=timeout<=1800,'Bounded phase required')
        key=phase.lower()+'_exit_code'
        self.state.pop(key,None)
        error=None
        try:
            super().execute(argv,log,timeout,phase)
        except BaseException as exc:
            error=repr(exc)
            raise
        finally:
            save(log.with_suffix('.exit.json'),dict(exit_code=self.state.get(key),error=error))


def own_pins():
    files=[p for p in HERE.iterdir() if p.suffix in ('.py','.sv','.md')]
    files += [Path(sys.executable).resolve(),*s.script_files(),
              SOC_COMPILE_PRIOR,
              ROOT/'hardware/scripts/fsdb_trace/extract_cycles.py',
              ROOT/'hardware/scripts/llama_q4km_extract/check-sim-l2.sh']
    for mod in tuple(sys.modules.values()):
        name=getattr(mod,'__file__',None)
        if name and Path(name).resolve().is_relative_to(ROOT): files.append(Path(name).resolve())
    return s.hashes(files)


def checked_prepare(path,expected):
    require(re.fullmatch('[0-9a-f]{64}',expected) is not None and digest(path/'prepare.json')==expected,
            'Reviewed preparation identity mismatch')
    report=s.read_json(path/'prepare.json')
    require(report['state']=='PREPARED_NOT_COMPILED_NOT_EXECUTED' and
            report['schema']=='reader_held_ar_fault_v1' and report['expected_commands']==71 and
            report['expected_reader_fault']==3 and report['expected_trap_cause']==5 and
            report['capture_bound_ns']==250000 and set(report['recipes'])==set(MODES),
            'Wrong preparation contract')
    require(digest(path/'source-pins.json')==report['source_pins_sha256'],'Preparation pins receipt drift')
    pins=s.read_json(path/'source-pins.json')
    for source in HERE.iterdir():
        if source.suffix in ('.py','.sv'):
            require(pins.get(str(source))==digest(source),'New/changed executor requires fresh preparation: '+str(source))
    s.merge_pins(pins,report['artifact_pins'])
    s.merge_pins(pins,s.hashes([path/'prepare.json',path/'source-pins.json']))
    s.verify_pins(pins)
    require((path/'main.c').read_text()==prep.render.render_main(prep.render.MAIN.read_text()),
            'Successor program transform drift')
    require(prep.render.restore_main((path/'main.c').read_text())==prep.render.MAIN.read_text(),
            'Program inverse mismatch')
    for mode in MODES:
        recipe=report['recipes'][mode]
        require(recipe['filelist']==str(path/(mode+'.f')) and recipe['vlsu']==str(path/(mode+'_vlsu.sv')),
                'Source graph outside prepared output')
        require(s.read_json(Path(recipe['capture']))==prep.wave.profile(mode=='candidate') and
                Path(recipe['script']).read_text()==prep.wave.script(mode=='candidate',250000),
                'Capture identity drift')
    return report,pins


SOC_REPEAT_HASHES = {
    'hardware/deps/cva6/corev_apu/tb/common/mock_uart.sv':
        '1bd632e6e7ec0f8395b30378e2c2a0a7b138a4bf4c89e95f6e4f092919c5c470',
    'hardware/tb/ara_testharness.sv':
        '2170512673680e73b91cce44a0a600bb32000427404b9026238b2914af20482c',
}


SOC_COMPILE_PRIOR = ROOT/'verification/out/qbacc-soc-20261023-02/build/sim/comp.vcs.log'
SOC_COMPILE_PRIOR_SHA256 = '3dea2df66c7bffe0fdc5fba59f785bb171a57fd765c493a412cb16fcca256873'
SOC_MONITOR_HASHES = {
    'hardware/tb/ara_tb.sv': 'c6416eabbc9a77c49ffbaec4643dcafdc1a31e758a35f1418cf084d63049f3e8',
    'hardware/tb/llm_perf_monitor.sv': '06429b17aadd8fcb7c7c9881879d4f84a0c1ba61b50a0aad79b18b3993d3af67',
}


def check_soc_compile(text,code,expectedargv,source_root):
    require(text.startswith('Command: ') and len(re.findall(r'^Command:',text,re.M))==1,
            'Need one complete leading VCS command record')
    lines=text.splitlines(keepends=True); header=[]
    for line in lines:
        require(line.endswith('\n'),'Unterminated VCS command record')
        header.append(line)
        if not line.endswith('\\\n'): break
    header=''.join(header)
    argv=shlex.split(header[len('Command: '):].replace('\\\n',''))
    require(expectedargv and Path(expectedargv[0]).name=='vcs' and
            argv==['vcs',*map(str,expectedargv[1:])] and argv.count('+lint=PCWM')==1,
            'VCS command record differs from approved argv')
    remaining=text[len(header):]
    require(digest(SOC_COMPILE_PRIOR)==SOC_COMPILE_PRIOR_SHA256,'Accepted SoC compile log drift')
    manifest=s.read_json(SOC_COMPILE_PRIOR.parent/'vcs_source_manifest.json')
    records={row['path']:row['sha256'] for row in manifest['files']}
    for relative,expected in SOC_MONITOR_HASHES.items():
        require(records.get(str(ROOT/relative))==expected and
                digest(source_root/relative)==expected,'Admitted SoC monitor source drift')
    pattern=r'^Lint-\[PCWM-L\][\s\S]*?(?=\n\n|\Z)'
    prior=re.findall(pattern,SOC_COMPILE_PRIOR.read_text(),re.M)
    ports=('retired_inst_count_i','retired_vector_inst_count_i')
    require(len(prior)==2,'Wrong accepted SoC lint inventory')
    for block,port in zip(prior,ports):
        require(block.startswith('Lint-[PCWM-L] Port connection width mismatch\n'+
                    str(ROOT/'hardware/tb/ara_tb.sv')+', 2129\n') and
                f'  "{port}" of module "llm_perf_monitor", instance ' in block and
                '  The following 32-bit expression is connected to 2-bit port ' in block,
                'Wrong accepted monitor lint contract')
    admitted=[block.replace(str(ROOT)+'/',str(source_root)+'/') for block in prior]
    require(re.findall(pattern,remaining,re.M)==admitted and
            all(remaining.count(block)==1 for block in admitted),'Changed/extra/missing SoC lint blocks')
    for block in admitted: remaining=remaining.replace(block,'',1)
    legacy=latency.check_compile(remaining,code,source_root/'hardware/deps/cva6/core/cva6_mmu/cva6_shared_tlb.sv')
    return dict(legacy=legacy,command_argv=list(map(str,expectedargv)),
                prior_log=str(SOC_COMPILE_PRIOR),prior_sha256=SOC_COMPILE_PRIOR_SHA256,
                source_hashes=SOC_MONITOR_HASHES,lint_code='PCWM-L',line=2129,
                ports=list(ports),count_per_port=1)


def soc_repeat_admission(filelist,source_root):
    from collections import Counter
    snapshot_path=source_root.parent/'manifest.json'
    snapshot=s.read_json(snapshot_path)
    accepted=ROOT/'verification/out/qbacc-soc-20261023-02/build/sim/vcs_source_manifest.json'
    original_list=ROOT/'verification/out/qbacc-soc-20261023-02/build/hardware-build/vcs/bender_script_default'
    require(snapshot['baseline_manifest']==str(accepted),'Wrong accepted full-SoC manifest')
    for path in (accepted,original_list):
        require(snapshot['input_pins'].get(str(path))==digest(path),'Accepted metadata identity drift')
    manifest=s.read_json(accepted)
    require(manifest['schema_version']==1 and manifest['repo_root']==str(ROOT) and
            manifest['filelist']==str(original_list),'Accepted metadata path/root mismatch')
    records={r['path']:r['sha256'] for r in manifest['files']}
    require(len(records)==len(manifest['files']) and records.get(str(original_list))==digest(original_list),
            'Ambiguous accepted inventory or filelist drift')

    def sources(path):
        return [Path(line.strip()) for line in path.read_text().splitlines()
                if Path(line.strip()).is_absolute() and Path(line.strip()).suffix in ('.sv','.v')]

    originals=sources(original_list); current=sources(filelist)
    require(all(p==p.resolve(strict=True) for p in current),'Aliased source path in full-SoC filelist')
    prior_repeats={p:n for p,n in Counter(originals).items() if n>1}
    current_repeats={p:n for p,n in Counter(current).items() if n>1}
    require(prior_repeats=={ROOT/r:2 for r in SOC_REPEAT_HASHES},'Changed accepted duplicate set/count')
    require(current_repeats=={source_root/r:2 for r in SOC_REPEAT_HASHES},
            'Unlisted/renamed/missing duplicate or wrong count in full-SoC filelist')
    admissions=[]
    for relative,expected in SOC_REPEAT_HASHES.items():
        old,new=ROOT/relative,source_root/relative
        require(snapshot['source_mapping'].get(str(old))==str(new),'Duplicate source mapping changed')
        require(records.get(str(old))==snapshot['input_pins'].get(str(old))==expected and
                snapshot['artifact_pins'].get(str(new))==expected and
                digest(old)==digest(new)==expected,'Duplicate source hash changed')
        admissions.append(dict(canonical_relative_path=relative,original=str(old),mapped=str(new),
                               count=2,sha256=expected))
    return admissions,[snapshot_path,accepted,original_list]


def graph_manifest(recipe,source_root):
    import tempfile
    filelist=Path(recipe['filelist'])
    extras=list(map(Path,recipe['extra_sources']))
    admissions,provenance=soc_repeat_admission(filelist,source_root)
    extras+=provenance
    repeated={row['mapped'] for row in admissions}
    # Deduplicate ONLY the inventory adapter, after exact full-SoC admission.
    # The actual compiler filelist is neither rewritten nor reordered, and its
    # complete bytes (including both occurrences) remain pinned in the manifest.
    seen=set(); inventory=[]
    for line in filelist.read_text().splitlines(keepends=True):
        token=line.strip()
        if token in repeated:
            if token in seen: continue
            seen.add(token)
        inventory.append(line)
    with tempfile.TemporaryDirectory(prefix='held-ar-soc-inventory-') as directory:
        normalized=Path(directory)/'inventory.f'
        normalized.write_text(''.join(inventory))
        graph=latency.graph_pins(normalized,extras,source_root)
        graph.pop(str(normalized))
    graph[str(filelist)]=digest(filelist)
    # Include source-local headers as explicit inventory extras. This changes
    # only manifest coverage, not compiler input order or the source filelist.
    extras=sorted(set(extras+[Path(p) for p in graph if Path(p).suffix in ('.h','.hpp','.vh','.svh')]))
    records=latency.tools.collect(filelist,source_root,extras)
    require({r['path']:r['sha256'] for r in records}==graph,'Incomplete source/header graph inventory')
    return dict(schema_version=1,repo_root=str(source_root),filelist=str(filelist),
                extra_sources=list(map(str,extras)),files=records,admitted_repeats=admissions)


def verify_manifest(path):
    manifest=s.read_json(path)
    require(manifest['schema_version']==1,'Wrong VCS manifest schema')
    records=latency.tools.collect(Path(manifest['filelist']),Path(manifest['repo_root']),
                                 list(map(Path,manifest['extra_sources'])))
    require(records==manifest['files'],'VCS source/header inventory drift')


def parse_weights(text,allocated):
    matches=[]
    for line in text.splitlines():
        parts=line.split()
        if parts and parts[0]=='weights':
            require(len(parts)==4 and parts[1] in ('b','B','d','D') and
                    re.fullmatch('[0-9a-fA-F]+',parts[2]) and re.fullmatch('[0-9a-fA-F]+',parts[3]),
                    'Malformed or non-data weights symbol')
            matches.append((int(parts[2],16),int(parts[3],16)))
    require(len(matches)==1,'Need one exact weights symbol')
    address,size=matches[0]
    require(size==432 and address%64==0 and address%4096<=4096-288 and
            0x80000000<=address and address+size<=0x81000000-65536,'Weights geometry/page/L2 bound')
    require(sum(int(r['address']<=address and address+size<=r['address']+r['bytes'])
                for r in allocated)==1,'Weights not wholly in one allocated section')
    return dict(name='weights',address=address,bytes=size,alignment=64,first_two_rows_same_page=True)


def check_sections(allocated):
    require(allocated and all(type(r['address']) is int and type(r['bytes']) is int and r['bytes']>0
            and 0x80000000<=r['address'] and r['address']+r['bytes']<=0x81000000-65536
            for r in allocated),'ELF allocation exceeds 16MiB/reserved stack')


def closed_evidence(paths):
    paths=list(paths)
    require(all(p.name not in ('worker.log','status.json','result.json','build.json') for p in paths),
            'Never seal active stdout/status/self receipt')
    return s.hashes(paths)


def checked_build(path,expected):
    require(digest(path/'build.json')==expected,'Reviewed build identity mismatch')
    report=s.read_json(path/'build.json'); status=s.read_json(path/'status.json')
    require(report['state']==status['state']==BUILD_STATE and status['child_pid'] is None and
            report['post_pins_match'] is True and report['execution']=='NOT_RUN','Nonterminal/wrong build')
    require(digest(path/'source-pins.json')==report['source_pins_sha256'],'Build source receipt drift')
    prepared,_=checked_prepare(Path(report['prepared']),report['prepare_sha256'])
    pins=s.read_json(path/'source-pins.json')
    s.merge_pins(pins,report['artifact_pins'])
    s.merge_pins(pins,s.hashes([path/'build.json',path/'status.json',path/'source-pins.json']))
    require(report['elf']==str(path/'gnu/reader_fault.elf') and
            report['elf_sha256']==digest(Path(report['elf'])),'ELF identity drift')
    allocated=sections.alloc_sections(Path(report['elf'])); check_sections(allocated)
    require(allocated==report['sections'] and
            parse_weights((path/'gnu/nm.log').read_text(),allocated)==report['weights'],'ELF/nm receipt mismatch')
    require(set(report['images'])==set(MODES),'Missing paired image')
    for mode in MODES:
        image=report['images'][mode]; simv=Path(image['simv'])
        require(simv==path/mode/'simv','Image variant/output mismatch')
        require(s.hashes(s.image_files(simv))==image['pins'],'Image inventory drift')
        s.merge_pins(pins,image['pins'])
        require(s.read_json(simv.parent/'vcs_source_manifest.json')==
                graph_manifest(prepared['recipes'][mode],Path(prepared['snapshot'])/'source'),
                'Compiled manifest not the prepared source graph')
    s.verify_pins(pins)
    return report,prepared,pins


def finish_failure(owner,out,exc):
    import subprocess
    state='INTERRUPTED' if isinstance(exc,(StopRequested,KeyboardInterrupt)) else \
          'TIMEOUT' if isinstance(exc,subprocess.TimeoutExpired) else 'FAIL'
    owner.state.update(state=state,error=repr(exc),child_pid=None)
    save(out/'result.json',dict(owner.state))
    owner.save()
