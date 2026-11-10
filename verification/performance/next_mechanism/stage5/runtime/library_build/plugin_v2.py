#!/usr/bin/env python3
"""Compiler-plugin classification fix; reuse authenticated FAIL01 sources."""
import argparse
import difflib
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
OUT=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
PARTIAL=OUT/'stage5_libraries_prepare_20261110_01'
FAIL_SHA='aad6a3ff700d4e22c74446442d091f220997b299a739056c9f670c26ce0494eb'
PARENT_FILES={'recipe.py':'268281440cd9f1a526cfbbbdb891e8fbed2269e7855d01c9357cc865794e64ce',
    'test_recipe.py':'685d6770223854c8071c1c2ad3e2582dc31fa41d55781b5e0fed0cac6a69bc9e',
    'README.md':'ef637decbf34ae1e8d172522fad62744e108bd65144e8337d24e1f185d01035a'}
OWN=('plugin_v2.py','test_plugin_v2.py','PLUGIN_V2.md')

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''): h.update(data)
    return h.hexdigest()

def identity():
    values={name:sha(HERE/name) for name in OWN}
    return values,hashlib.sha256(json.dumps(values,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def require(ok,message):
    if not ok: raise ValueError(message)

def load(path,name):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module

def parent():
    require(sha(PARTIAL/'prepare.json')==FAIL_SHA,'Historical FAIL01 receipt changed')
    require({n:sha(PARTIAL/'inputs'/n) for n in PARENT_FILES}==PARENT_FILES,'Historical helper changed')
    base=load(PARTIAL/'inputs/recipe.py','stage5_library_frozen_v1')
    report=base.read(PARTIAL/'prepare.json')
    require(report['state']=='FAIL' and report['error']=="ValueError('Missing target runtime liblto_plugin.so')",
            'Wrong historical failure')
    return base

def once(text,old,new):
    require(text.count(old)==1,'Missing/nonunique successor anchor: '+old[:80]);return text.replace(old,new)

def worker_source(text):
    # Functional tool fix only: plugin is a host compiler program, never target
    # runtime. Existing program pin+ldd handling then covers it without omission.
    text=once(text,"('cc1','cc1plus','collect2','as','ld'):",
                   "('cc1','cc1plus','collect2','as','ld','liblto_plugin.so'):")
    text=once(text,"'crtbeginT.o','crtend.o','liblto_plugin.so'):","'crtbeginT.o','crtend.o'):")
    text=once(text,"    for name in ('libgcc.a'","    pinned_library_dirs=set()\n    for name in ('libgcc.a'")
    text=once(text,'        for sibling in p.parent.iterdir():\n',
        '        directory=p.parent.resolve()\n'
        '        if directory in pinned_library_dirs: continue\n'
        '        pinned_library_dirs.add(directory)\n'
        '        for sibling in directory.iterdir():\n')
    # Reuse an explicitly authenticated historical data root. Do not copy or
    # symlink the large source trees, alter FAIL01, or pretend its receipt passed.
    before,body=text.split('def build(args):',1)
    body,after=body.split('\ndef main():',1)
    body=once(body,"receipt=read(prepared/'prepare.json');require(receipt['state']=='PREPARED_NOT_BUILT','Preparation not accepted')",
        "receipt=read(prepared/'prepare.json');require(receipt['state']=='PREPARED_NOT_BUILT' and receipt['schema']=='stage5-libraries-prepare-v2','Preparation not accepted')\n"
        "    input_prepared=Path(receipt['input_prepared']).resolve()\n"
        "    require(input_prepared==Path("+repr(str(PARTIAL))+"),'Unexpected historical source owner')\n"
        "    require(inventory(prepared/'runner')==read(prepared/'runner-inventory.json'),'Runner membership changed')")
    body=once(body,"pins[str(prepared/'inputs/recipe.py')]","pins[str(prepared/'runner/recipe.py')]")
    body=body.replace("prepared/'inputs", "input_prepared/'inputs")
    body=once(body,'validate_commands(commands,prepared,builddir)','validate_commands(commands,input_prepared,builddir)')
    body=once(body,'link_argv(prepared,output,archives)','link_argv(input_prepared,output,archives)')
    body=once(body,"        verify(pins);require(inventory(input_prepared/'inputs')",
        "        require(inventory(prepared/'runner')==read(prepared/'runner-inventory.json'),'Runner membership changed')\n"
        "        verify(pins);require(inventory(input_prepared/'inputs')")
    return before+'def build(args):'+body+'\ndef main():'+after

def checked_partial(base):
    base.checked_host()
    inputs=PARTIAL/'inputs';root=inputs/'llama';original=base.HOST/'inputs/llama'
    artifacts=base.read(base.HOST/'result.json')['artifacts']
    remapped={str(root/Path(p).relative_to(original)):h for p,h in artifacts.items() if Path(p).is_relative_to(original)}
    base.checked_source_membership(root,remapped)
    # Compare the existing SDK archive against immutable Git objects, then check
    # every extracted SDK member. No archive extraction or source copying.
    raw=subprocess.check_output(['/usr/bin/git','-C',str(base.ROOT),'archive',base.SDK_REV,
        'software/akv','software/qbs'],timeout=30)
    require(sha(inputs/'sdk.tar')==hashlib.sha256(raw).hexdigest(),'Historical SDK archive differs from f500')
    sdk_files={}
    with tarfile.open(fileobj=io.BytesIO(raw)) as archive:
        for member in archive.getmembers():
            if member.isdir(): continue
            require(member.isfile() and '..' not in Path(member.name).parts and not Path(member.name).is_absolute(),
                    'Unexpected frozen SDK archive member')
            sdk_files['sdk/'+member.name]=hashlib.sha256(archive.extractfile(member).read()).hexdigest()
    expected={'llama/'+str(Path(p).relative_to(root)):h for p,h in remapped.items()}
    expected.update(sdk_files)
    expected.update({n:h for n,h in PARENT_FILES.items()})
    expected['sdk.tar']=sha(inputs/'sdk.tar')
    expected['link_probe.cpp']=hashlib.sha256(base.PROBE.encode()).hexdigest()
    actual={n:v['sha256'] for n,v in base.inventory(inputs).items() if v['kind']!='directory'}
    require(actual==expected,'Historical partial input membership/bytes changed')
    return base.inventory(inputs)

def classify(file_query,program_query,configured,dry_run,tool_root):
    require(file_query.strip()=='liblto_plugin.so','Unexpected failed-query evidence')
    plugin=Path(program_query.strip()).resolve()
    require(plugin.is_file() and plugin.is_relative_to(tool_root.resolve()),'Compiler plugin absent/escaping')
    require('--enable-plugins' in configured and '--enable-lto' in configured,'GCC configuration lacks plugin support')
    commands=[]
    for line in dry_run.splitlines():
        if line.lstrip().startswith('/'):
            argv=shlex.split(line)
            if argv and Path(argv[0]).name=='collect2': commands.append(argv)
    require(len(commands)==1 and '-plugin' in commands[0],'No explicit collect2 plugin usage proof')
    require(Path(commands[0][commands[0].index('-plugin')+1]).resolve()==plugin,'Driver uses a different plugin')
    require(not any(a.startswith('-flto') for argv in commands for a in argv),'Unexpected requested LTO transformation')
    return plugin

def audit(args):
    base=parent();own,own_sha=identity();checked_partial(base)
    output=base.fresh(args.output,'stage5_libraries_tool_audit_');rows=[];pins={}
    def expired(_signal,_frame): raise TimeoutError('Tool audit 360-second deadline')
    previous=signal.signal(signal.SIGALRM,expired);signal.alarm(360)
    report=dict(state='FAIL',schema='stage5-libraries-tool-audit-v2',source_review_sha256=own_sha,
        historical_failure_sha256=FAIL_SHA,library_build_started=False,provider_registered=False)
    try:
        (output/'home').mkdir();(output/'tmp').mkdir();(output/'runner').mkdir()
        corrected=worker_source((PARTIAL/'inputs/recipe.py').read_text())
        worker=output/'runner/recipe.py';worker.write_text(corrected)
        fixed=load(worker,'stage5_library_corrected_tool_audit')
        env=fixed.environment(output)
        def query(label,argv): return fixed.command(argv,output,env,output/(label+'.log'),rows,60).strip()
        file_query=query('plugin-file-query',[fixed.CXX,'-print-file-name=liblto_plugin.so'])
        program_query=query('plugin-program-query',[fixed.CXX,'-print-prog-name=liblto_plugin.so'])
        configured=query('compiler-config',[fixed.CXX,'-v'])
        dry=query('link-driver-dry-run',[fixed.CXX,*fixed.FLAGS.split(),'-static','-no-pie','-###',
            PARTIAL/'inputs/link_probe.cpp','-o',output/'never-linked.elf'])
        plugin=classify(file_query,program_query,configured,dry,fixed.TOOLS)
        header=query('host-plugin-elf',[fixed.TOOLS/'bin/riscv64-linux-readelf','-h',plugin])
        require('X86-64' in header and 'RISC-V' not in header,'Plugin is not a host ELF')
        # Run the complete corrected metadata audit once before prepare retry;
        # includes/tool libs/ldd are reused by the new preparation, not recopied.
        toolchain=fixed.pin_toolchain(output,pins,rows)
        require(Path(toolchain['programs']['liblto_plugin.so']).resolve()==plugin,'Plugin not pinned as program')
        require(not (output/'never-linked.elf').exists(),'Dry run created target output')
        fixed.write(output/'toolchain.json',toolchain);fixed.write(output/'tool-pins.json',pins)
        source_pins=dict(pins)
        for p in [worker,PARTIAL/'prepare.json',PARTIAL/'inputs/recipe.py',*[HERE/n for n in OWN]]:
            fixed.pin(source_pins,p)
        fixed.verify(source_pins);require(identity()==(own,own_sha),'Audit source changed')
        fixed.write(output/'source-pins.json',source_pins)
        report.update(state='TOOL_AUDIT_PASS_NO_BUILD',host_plugin=str(plugin),host_plugin_sha256=sha(plugin),
            classification='compiler-host-program, mandatory collect2 plugin even with GGML_LTO=OFF',
            plugin_program_query=True,target_runtime_query=False,lto_transforms_requested=False,
            corrected_worker_sha256=sha(worker),tool_pins_sha256=sha(output/'tool-pins.json'),
            source_pins_sha256=sha(output/'source-pins.json'))
    except BaseException as exc:
        report['error']=repr(exc);raise
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous)
        base.write(output/'commands.json',rows)
        report['artifacts']={str(p):sha(p) for p in output.rglob('*') if p.is_file()}
        base.write(output/'audit.json',report)
    return report

def prepare(args):
    base=parent();own,own_sha=identity()
    require(own_sha==args.reviewed_source_sha256,'Successor review mismatch')
    source_inventory=checked_partial(base);audit_dir=Path(args.audit).resolve()
    require(audit_dir.parent==OUT and sha(audit_dir/'audit.json')==args.reviewed_audit_sha256,'Unreviewed audit')
    a=base.read(audit_dir/'audit.json')
    require(a['state']=='TOOL_AUDIT_PASS_NO_BUILD' and a['source_review_sha256']==own_sha,'Audit not accepted for this successor')
    base.verify(base.read(audit_dir/'source-pins.json'));base.verify(a['artifacts'])
    output=base.fresh(args.output,'stage5_libraries_prepare_')
    report=dict(schema='stage5-libraries-prepare-v2',state='FAIL',source_review_sha256=own_sha,
        historical_failure_sha256=FAIL_SHA,input_prepared=str(PARTIAL),tool_audit_sha256=args.reviewed_audit_sha256,
        reused_inputs=True,source_copied=False,provider_registered=False,native_execution=False)
    try:
        runner=output/'runner';runner.mkdir()
        worker=runner/'recipe.py';shutil.copyfile(audit_dir/'runner/recipe.py',worker)
        require(sha(worker)==a['corrected_worker_sha256'],'Corrected worker changed')
        for name in OWN: shutil.copyfile(HERE/name,runner/name)
        require({n:sha(runner/n) for n in OWN}==own,'Successor copies changed')
        pins=base.read(audit_dir/'tool-pins.json')
        for root in (PARTIAL/'inputs',runner):
            for p in root.rglob('*'):
                if p.is_file(): base.pin(pins,p)
        for p in [PARTIAL/'prepare.json',audit_dir/'audit.json',audit_dir/'source-pins.json',
                  audit_dir/'tool-pins.json',*[HERE/n for n in OWN]]: base.pin(pins,p)
        base.write(output/'tree-inventory.json',source_inventory)
        base.write(output/'runner-inventory.json',base.inventory(runner))
        shutil.copyfile(audit_dir/'toolchain.json',output/'toolchain.json')
        for n in ('tree-inventory.json','runner-inventory.json','toolchain.json'): base.pin(pins,output/n)
        base.verify(pins);require(base.inventory(PARTIAL/'inputs')==source_inventory,'Historical source changed during reuse')
        require(identity()==(own,own_sha) and {n:sha(runner/n) for n in OWN}==own,'Successor changed during prepare')
        base.write(output/'source-pins.json',pins)
        base_source=(PARTIAL/'inputs/recipe.py').read_text();corrected=worker.read_text()
        (output/'worker.patch').write_text(''.join(difflib.unified_diff(base_source.splitlines(True),corrected.splitlines(True),
            'a/frozen-library-recipe.py','b/plugin-v2-library-recipe.py')))
        report.update(state='PREPARED_NOT_BUILT',source_pins_sha256=sha(output/'source-pins.json'),
            source=str(PARTIAL/'inputs/llama'),sdk=str(PARTIAL/'inputs/sdk'),
            jobs=4,total_worker_timeout_seconds=1800,required_archives=list(base.ARCHIVES),
            configure_options=base.options(PARTIAL/'inputs/llama',PARTIAL/'inputs/sdk'),
            frontend_include_dirs=list(map(str,base.includes(PARTIAL))),frontend_flags=['-std=c++17',*base.FLAGS.split(),'-static','-no-pie'],
            link_order=['frontend.o','future-accepted-provider.o','--start-group',*base.ARCHIVES,
                '--end-group','-lm','-pthread','-ldl','-latomic'],worker_sha256=sha(worker),patch_sha256=sha(output/'worker.patch'))
    except BaseException as exc:
        report['error']=repr(exc);raise
    finally: base.write(output/'prepare.json',report)
    return report

def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('identity')
    a=sub.add_parser('audit');a.add_argument('--output',type=Path,required=True)
    a=sub.add_parser('prepare');a.add_argument('--output',type=Path,required=True)
    a.add_argument('--audit',type=Path,required=True);a.add_argument('--reviewed-source-sha256',required=True)
    a.add_argument('--reviewed-audit-sha256',required=True)
    args=p.parse_args()
    result=dict(files=identity()[0],source_sha256=identity()[1]) if args.command=='identity' else (
        audit(args) if args.command=='audit' else prepare(args))
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__': main()
