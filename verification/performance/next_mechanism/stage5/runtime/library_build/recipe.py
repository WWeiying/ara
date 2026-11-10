#!/usr/bin/env python3
"""Frozen static GGML/llama library build only. No provider grant or inference."""
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tarfile
import time

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=Path('/home/wangwy/openproject/ara_dsa')
OUT=ROOT.parent/'ara_dsa_signoff_integration/verification/out'
HOST=OUT/'stage5_ggml_overlay_host_20261110_09'
HOST_SHA='0a682a093837859d5cc43a2dd04e9859239827a839f4fedc4f9a76a838618f9c'
HOST_PINS='e1303ccc956a7ae3de2cd09f3a2915d3992c8207e0acb64db73ffc1fc449dc17'
SDK_REV='f50092f2d22238c6be4b6c159a1ad71a4ea68678'
SDK_MODEL_REV='c49289ff8f433b8780954e207d6b0149f7bc2c32'
LLAMA_REV='da56aa750559c180d631b466de983ff2bb5d54d9'
TOOLS=Path('/home/wangwy/llama/platforms/cva6-qemu/tools')
CC=TOOLS/'bin/riscv64-linux-gcc'
CXX=CC.with_name('riscv64-linux-g++')
OWN=('recipe.py','test_recipe.py','README.md')
ARCHIVES=('libllama.a','libggml.a','libggml-cpu.a','libggml-base.a')
FLAGS='-march=rv64gcv_zfh_zvfh -mabi=lp64d -fno-fast-math -ffp-contract=off'
LIMIT=1800
PROBE='''// Link-only; never executed or used as a platform provider.
#include "llama.h"
#include "entry.h"
int main() {
    auto *volatile decode = &llama_decode;
    (void) decode;
    auto params = llama_model_default_params();
    (void) params;
    ggml_akv_resident_counters_v1 counters{};
    ggml_akv_resident_snapshot_v1(&counters);
    return akv_resident_platform_current_v1() != nullptr ||
           ggml_akv_legacy_current_v1() != nullptr;
}
'''

def require(ok,message):
    if not ok: raise ValueError(message)

def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''): h.update(data)
    return h.hexdigest()

def canonical(value): return json.dumps(value,sort_keys=True,separators=(',',':')).encode()

def read(path):
    def pairs(items):
        result={}
        for k,v in items:
            require(k not in result,'Duplicate JSON key: '+k);result[k]=v
        return result
    return json.loads(Path(path).read_text(),object_pairs_hook=pairs)

def write(path,value):
    with Path(path).open('x') as f: json.dump(value,f,indent=2,sort_keys=True);f.write('\n')

def verify(pins):
    for p,h in pins.items(): require(sha(p)==h,'Pin drift: '+p)

def identity():
    pins={name:sha(HERE/name) for name in OWN}
    return pins,hashlib.sha256(canonical(pins)).hexdigest()

def fresh(path,prefix):
    p=Path(path).absolute()
    require(p==p.resolve() and p.parent==OUT and re.fullmatch(prefix+r'[A-Za-z0-9_]+',p.name)
            and not p.exists(),'Fresh direct signoff output required')
    p.mkdir();return p

def inventory(root):
    result={}
    for p in sorted(root.rglob('*')):
        name=str(p.relative_to(root))
        if p.is_symlink():
            require(p.resolve().is_relative_to(root.resolve()) and p.resolve().exists(),'Escaping/broken source symlink: '+str(p))
            result[name]=dict(kind='symlink',target=os.readlink(p),sha256=sha(p))
        elif p.is_dir(): result[name]=dict(kind='directory')
        else:
            require(p.is_file(),'Unsupported source member: '+str(p))
            result[name]=dict(kind='file',sha256=sha(p))
    return result

def pin(pins,path):
    p=Path(path).absolute();require(p.is_file(),'Missing dependency: '+str(p))
    for q in (p,p.resolve()):
        value=sha(q)
        require(str(q) not in pins or pins[str(q)]==value,'Dependency changed: '+str(q))
        pins[str(q)]=value

def environment(output):
    return dict(PATH=str(TOOLS/'bin')+':/usr/bin:/bin',HOME=str(output/'home'),TMPDIR=str(output/'tmp'),
        LANG='C',LC_ALL='C',PYTHONNOUSERSITE='1',PYTHONDONTWRITEBYTECODE='1',
        GIT_CEILING_DIRECTORIES=str(output),SOURCE_DATE_EPOCH='1793311200')

def command(argv,cwd,env,log,rows,timeout):
    argv=list(map(str,argv));row=dict(argv=argv,cwd=str(cwd),timeout_seconds=timeout)
    rows.append(row);started=time.monotonic()
    with Path(log).open('x') as f:
        try:
            p=subprocess.run(argv,cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
            row['returncode']=p.returncode
        finally: row['elapsed_seconds']=time.monotonic()-started
    require(row['returncode']==0,'Command failed: '+str(log))
    return Path(log).read_text()

def checked_host():
    require(sha(HOST/'result.json')==HOST_SHA and sha(HOST/'source-pins.json')==HOST_PINS,'Wrong overlay09 identity')
    r=read(HOST/'result.json')
    require(r['state']=='HOST_GNU_CONTROL_PASS_NO_NATIVE' and r['tests']==7 and
        r['native_execution'] is False and r['provider_registered'] is False,'Wrong overlay09 scope')
    verify(read(HOST/'source-pins.json'));verify(r['artifacts'])
    checked_source_membership(HOST/'inputs/llama',r['artifacts'])
    return read(HOST/'inputs/manifest.json')

def checked_source_membership(root,artifacts):
    expected={str(Path(p).relative_to(root)):h for p,h in artifacts.items() if Path(p).is_relative_to(root)}
    require(expected,'Missing authoritative source membership')
    actual={name:item['sha256'] for name,item in inventory(root).items() if item['kind']!='directory'}
    require(actual==expected,'Overlay source membership/bytes differ from authoritative host09')

def checked_owned(own,own_sha,copies):
    require(identity()==(own,own_sha),'Reviewed successor changed during preparation')
    require({name:sha(copies/name) for name in OWN}==own,'Frozen successor copies differ from review')

def options(source,sdk):
    return dict(CMAKE_SYSTEM_NAME='Linux',CMAKE_SYSTEM_PROCESSOR='riscv64',CMAKE_C_COMPILER=str(CC),
        CMAKE_CXX_COMPILER=str(CXX),CMAKE_ASM_COMPILER=str(CC),CMAKE_C_FLAGS=FLAGS,CMAKE_CXX_FLAGS=FLAGS,
        CMAKE_ASM_FLAGS=FLAGS,CMAKE_TRY_COMPILE_TARGET_TYPE='STATIC_LIBRARY',CMAKE_BUILD_TYPE='Release',
        CMAKE_EXPORT_COMPILE_COMMANDS='ON',CMAKE_SKIP_RPATH='ON',BUILD_SHARED_LIBS='OFF',
        GGML_NATIVE='OFF',GGML_CCACHE='OFF',GGML_LTO='OFF',GGML_OPENMP='OFF',GGML_BACKEND_DL='OFF',
        GGML_CPU='ON',GGML_CPU_REPACK='ON',GGML_RVV='ON',GGML_RV_ZFH='ON',GGML_RV_ZVFH='ON',
        GGML_RV_ZICBOP='OFF',GGML_RV_ZIHINTPAUSE='OFF',GGML_RV_ZVFBFWMA='OFF',GGML_BLAS='OFF',
        GGML_RISCV_QBS='ON',GGML_RISCV_AKV='ON',GGML_RISCV_AKV_RESIDENT='ON',
        GGML_RISCV_AKV_QUANT_KV='ON',GGML_RISCV_AKV_QUANT_PREFILL='ON',GGML_RISCV_AKV_REGISTER_PV='ON',
        GGML_RISCV_QBS_RUNTIME_DIR=str(sdk/'software/qbs'),GGML_RISCV_AKV_RUNTIME_DIR=str(sdk/'software/akv'),
        LLAMA_BUILD_COMMON='OFF',LLAMA_BUILD_TESTS='OFF',LLAMA_BUILD_EXAMPLES='OFF',LLAMA_BUILD_TOOLS='OFF',
        LLAMA_BUILD_SERVER='OFF',LLAMA_BUILD_APP='OFF',LLAMA_BUILD_MTMD='OFF',LLAMA_CURL='OFF',
        LLAMA_OPENSSL='OFF',LLAMA_HTTPLIB='OFF',LLAMA_BUILD_NUMBER='0',LLAMA_BUILD_COMMIT='da56+overlay09')

def configure_argv(source,sdk,build):
    return ['/usr/bin/cmake','-S',str(source),'-B',str(build),'-G','Unix Makefiles']+[
        '-D'+k+'='+v for k,v in sorted(options(source,sdk).items())]

def includes(prepared):
    inputs=prepared/'inputs';source=inputs/'llama';sdk=inputs/'sdk/software/akv'
    return [source/'include',source/'ggml/include',source/'ggml/src/ggml-cpu/arch/riscv',sdk/'include',sdk/'experimental']

def link_argv(prepared,output,archives,provider_objects=()):
    # Provider objects, when eventually accepted, MUST precede static archives.
    # This worker always passes the empty tuple and does not accept a CLI override.
    return [str(CXX),'-std=c++17',*FLAGS.split(),'-static','-no-pie',
        *['-I'+str(p) for p in includes(prepared)],str(prepared/'inputs/link_probe.cpp'),
        *map(str,provider_objects),'-Wl,--start-group',*[str(archives[n]) for n in ARCHIVES],
        '-Wl,--end-group','-lm','-pthread','-ldl','-latomic','-Wl,-Map='+str(output/'link-probe.map'),
        '-o',str(output/'link-probe.elf')]

def unique_archives(build):
    result={}
    for name in ARCHIVES:
        found=list(build.rglob(name));require(len(found)==1,'Missing/ambiguous archive '+name)
        result[name]=found[0]
    return result

def dependency_names(text):
    text=text.replace('\\\n',' ')
    require(':' in text,'Invalid compiler dependency file')
    rest=text.split(':',1)[1]
    require(':' not in rest,'Unsupported dependency directives')
    return shlex.split(rest)

def pin_toolchain(output,pins,rows):
    env=environment(output);tools={}
    def query(label,args): return command(args,output,env,output/(label+'.log'),rows,60).strip()
    names=('gcc','g++','ar','ranlib','nm','objdump','readelf','as','ld')
    for name in names:
        p=TOOLS/('bin/riscv64-linux-'+name);pin(pins,p);tools[name]=str(p)
    for pattern in ('riscv64*gcc*','riscv64*g++*'):
        for p in (TOOLS/'bin').glob(pattern):
            if p.is_file(): pin(pins,p)
    for name in ('cc1','cc1plus','collect2','as','ld'):
        value=query('tool-'+name,[CXX if name=='cc1plus' else CC,'-print-prog-name='+name])
        p=Path(value)
        if not p.is_absolute(): p=Path(shutil.which(value,path=env['PATH']) or value)
        require(p.resolve().is_relative_to(TOOLS.resolve()),'Unexpected compiler program: '+value)
        pin(pins,p);tools[name]=str(p)
    for name in ('libgcc.a','libgcc_eh.a','libstdc++.a','libatomic.a','libc.a','libm.a','libpthread.a',
                 'libdl.a','crt1.o','crti.o','crtn.o','crtbeginT.o','crtend.o','liblto_plugin.so'):
        value=query('library-'+name,[CXX,'-print-file-name='+name]);p=Path(value)
        require(p.is_absolute() and p.resolve().is_relative_to(TOOLS.resolve()),'Missing target runtime '+name)
        pin(pins,p)
        # Some .a names are linker scripts selecting adjacent archives/objects.
        for sibling in p.parent.iterdir():
            if sibling.is_file() and (sibling.suffix in ('.a','.o','.so') or '.so.' in sibling.name):
                pin(pins,sibling)
    verbose=query('compiler-includes',[CXX,*FLAGS.split(),'-E','-x','c++','-v','/dev/null'])
    require('#include <...> search starts here:' in verbose and 'End of search list.' in verbose,'Missing compiler include roots')
    roots=verbose.split('#include <...> search starts here:',1)[1].split('End of search list.',1)[0]
    include_roots=[]
    for line in roots.splitlines():
        if not line.strip(): continue
        p=Path(line.strip()).resolve();require(p.is_dir() and p.is_relative_to(TOOLS.resolve()),'Unexpected include root')
        include_roots.append(str(p))
        for f in p.rglob('*'):
            if f.is_file(): pin(pins,f)
    for name in ('cmake','make','git','sh','ldd','python3','systemctl','systemd-run'):
        p=Path(shutil.which(name,path='/usr/bin:/bin') or '/nonexistent');pin(pins,p);tools['host-'+name]=str(p)
    for modules in Path('/usr/share').glob('cmake*/Modules'):
        for f in modules.rglob('*'):
            if f.is_file(): pin(pins,f)
    for p in list(dict.fromkeys(tools.values())):
        # ldd is metadata-only; shell/static tools legitimately report non-dynamic.
        process=subprocess.run(['/usr/bin/ldd',p],env=env,capture_output=True,text=True,timeout=20)
        text=process.stdout+process.stderr
        require('not found' not in text,'Missing host tool library: '+p)
        require(process.returncode==0 or 'not a dynamic executable' in text or 'statically linked' in text,
                'Unrecognized ldd result: '+p)
        for token in text.split():
            if token.startswith('/') and Path(token).is_file(): pin(pins,token)
    return dict(programs=tools,include_roots=include_roots)

def prepare(args):
    own,own_sha=identity();require(own_sha==args.reviewed_source_sha256,'Source review mismatch')
    manifest=checked_host();output=fresh(args.output,'stage5_libraries_prepare_')
    rows=[];report=dict(schema='stage5-libraries-prepare-v1',state='FAIL',overlay_receipt_sha256=HOST_SHA,
        sdk_revision=SDK_REV,sdk_model_revision=SDK_MODEL_REV,llama_revision=LLAMA_REV,
        native_execution=False,provider_registered=False,source_review_sha256=own_sha)
    try:
        (output/'home').mkdir();(output/'tmp').mkdir();inputs=output/'inputs';inputs.mkdir()
        source=inputs/'llama';inventory(HOST/'inputs/llama')
        shutil.copytree(HOST/'inputs/llama',source,symlinks=True)
        require(inventory(source)==inventory(HOST/'inputs/llama'),'Overlay source copy differs')
        raw=subprocess.check_output(['/usr/bin/git','-C',str(ROOT),'archive',SDK_REV,'software/akv','software/qbs'])
        (inputs/'sdk.tar').write_bytes(raw)
        with tarfile.open(fileobj=io.BytesIO(raw)) as archive: archive.extractall(inputs/'sdk',filter='data')
        sdk=inputs/'sdk'
        require(inventory(sdk/'software/akv')==inventory(HOST/'sdk/software/akv'),'SDK differs from overlay09')
        subprocess.run(['/usr/bin/git','-C',str(ROOT),'diff','--exit-code',SDK_MODEL_REV,SDK_REV,'--',
            'software/akv','software/qbs'],check=True,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        for name in OWN: shutil.copyfile(HERE/name,inputs/name)
        checked_owned(own,own_sha,inputs)
        (inputs/'link_probe.cpp').write_text(PROBE)
        pins={}
        for p in inputs.rglob('*'):
            if p.is_file(): pin(pins,p)
        for name in OWN: pin(pins,HERE/name)
        pin(pins,HOST/'result.json');pin(pins,HOST/'source-pins.json')
        toolchain=pin_toolchain(output,pins,rows)
        write(output/'toolchain.json',toolchain);pin(pins,output/'toolchain.json')
        write(output/'tree-inventory.json',inventory(inputs));pin(pins,output/'tree-inventory.json')
        write(output/'source-pins.json',pins);verify(pins)
        checked_owned(own,own_sha,inputs)
        report.update(state='PREPARED_NOT_BUILT',source_pins_sha256=sha(output/'source-pins.json'),
            source=str(source),sdk=str(sdk),akv_sha256=manifest['akv_sha256'],cmake_sha256=manifest['cmake_sha256'],
            jobs=4,total_worker_timeout_seconds=LIMIT,required_archives=list(ARCHIVES),
            configure_options=options(source,sdk),frontend_include_dirs=list(map(str,includes(output))),
            frontend_flags=['-std=c++17',*FLAGS.split(),'-static','-no-pie'],
            link_order=['frontend.o','future-accepted-provider.o','--start-group',*ARCHIVES,
                        '--end-group','-lm','-pthread','-ldl','-latomic'],
            provider_object_required_for_positive_execution=True)
    except BaseException as exc:
        report['error']=repr(exc);raise
    finally:
        write(output/'commands.json',rows);write(output/'prepare.json',report)
    return report

def service_owner(unit):
    require(re.fullmatch(r'stage5-libraries-[A-Za-z0-9_-]+\.service',unit),'Owned service name required')
    invocation=os.environ.get('INVOCATION_ID','');require(re.fullmatch('[0-9a-f]{32}',invocation),'No systemd invocation')
    cgroup=Path('/proc/self/cgroup').read_text();require('/'+unit in cgroup,'Wrong service CGroup')
    pid=subprocess.check_output(['/usr/bin/systemctl','--user','show',unit,'--property=MainPID','--value'],text=True,timeout=10).strip()
    require(pid==str(os.getpid()),'Service must own worker directly')
    return dict(unit=unit,main_pid=os.getpid(),invocation_id=invocation,cgroup=cgroup)

def validate_commands(rows,prepared,builddir):
    inputs=prepared/'inputs';files=[]
    arch=inputs/'llama/ggml/src/ggml-cpu/arch/riscv'
    for row in rows:
        source=Path(row['file']).resolve();require(source.is_relative_to(inputs),'Source outside frozen inputs')
        argv=shlex.split(row['command']);files.append(source.name)
        require({a for a in argv if a.startswith('-march=')}=={'-march=rv64gcv_zfh_zvfh'} and
                {a for a in argv if a.startswith('-mabi=')}=={'-mabi=lp64d'},'Wrong ISA/ABI')
        require(not any(a in argv for a in ('-ffast-math','-Ofast')),'Unapproved fast math')
        for argument in argv:
            if argument.startswith('-I') and len(argument)>2:
                include=Path(argument[2:]).resolve()
                require(any(include.is_relative_to(root.resolve()) for root in (inputs,builddir,TOOLS)),
                        'Include outside frozen source/tool closure: '+str(include))
        guarded=source in [arch/name for name in ('akv.cpp','platform.c','entry.c')]
        if guarded or source.name=='akv_v2_native_riscv.c':
            require('-DGGML_AKV_RESIDENT=1' in argv,'Resident integration disabled')
            if guarded:
                require('-fno-tree-vectorize' in argv and '-fno-tree-slp-vectorize' in argv,'Guard not scalar')
    for name in ('qbs.cpp','akv.cpp','quant-kv.cpp','platform.c','read_state.S','qk.S','pv.S',
                 'qbs_runtime.c','qbs_native_riscv.c','akv_v2_native_riscv.c'):
        require(files.count(name)==1,'Required translation unit missing/duplicated: '+name)
    require(sum(Path(r['file']).resolve()==arch/'entry.c' for r in rows)==1,'Resident entry companion missing/duplicated')
    require('pv_prepare.S' not in files,'PV prepare must not be compiled twice')
    require(any('quantized_kv/prefill/ggml_entry.c' in r['file'] for r in rows),'Quantized Prefill missing')
    require(any('quantized_kv/register_pv/entry.c' in r['file'] for r in rows),'Register PV missing')

def build(args):
    prepared=Path(args.prepared).resolve();owner=service_owner(args.service)
    require(prepared.parent==OUT and sha(prepared/'prepare.json')==args.reviewed_prepare_sha256,'Unreviewed prepare')
    receipt=read(prepared/'prepare.json');require(receipt['state']=='PREPARED_NOT_BUILT','Preparation not accepted')
    require(sha(prepared/'source-pins.json')==receipt['source_pins_sha256'],'Pin inventory changed')
    pins=read(prepared/'source-pins.json');verify(pins)
    require(inventory(prepared/'inputs')==read(prepared/'tree-inventory.json'),'Input membership changed')
    require(sha(__file__)==pins[str(prepared/'inputs/recipe.py')],'Worker is not the frozen recipe')
    output=fresh(args.output,'stage5_libraries_build_');rows=[];started=time.monotonic()
    def expired(_signal,_frame): raise TimeoutError('Total 1800-second worker deadline')
    previous=signal.signal(signal.SIGALRM,expired);signal.alarm(LIMIT)
    report=dict(schema='stage5-libraries-build-v1',state='FAIL',service_owner=owner,
        prepare_sha256=args.reviewed_prepare_sha256,native_execution=False,numerical_checked=False,
        provider_registered=False,performance_measured=False)
    try:
        (output/'home').mkdir();(output/'tmp').mkdir();env=environment(output);report['environment']=env
        def run(label,argv):
            remaining=LIMIT-(time.monotonic()-started);require(remaining>0,'Worker deadline exceeded')
            return command(argv,output,env,output/(label+'.log'),rows,remaining)
        source=prepared/'inputs/llama';sdk=prepared/'inputs/sdk';builddir=output/'build'
        run('configure',configure_argv(source,sdk,builddir))
        commands=read(builddir/'compile_commands.json');validate_commands(commands,prepared,builddir)
        run('build',['/usr/bin/cmake','--build',builddir,'--target','llama','-j4'])
        archives=unique_archives(builddir)
        symbols=run('cpu-symbols',[TOOLS/'bin/riscv64-linux-nm','-g','--defined-only',archives['libggml-cpu.a']])
        for symbol in ('ggml_akv_resident_snapshot_v1','akv_experimental_attention_execute_v2_native',
                       'akv_experimental_resident_qk','akv_experimental_resident_pv','qbs_native_execute_command'):
            require(re.search(r'\b[TW]\s+'+symbol+r'$',symbols,re.M),'Missing CPU definition '+symbol)
        for symbol in ('akv_resident_platform_current_v1','ggml_akv_legacy_current_v1'):
            require(re.search(r'\bW\s+'+symbol+r'$',symbols,re.M),'Provider default is not weak: '+symbol)
            require(not re.search(r'\bT\s+'+symbol+r'$',symbols,re.M),'Unexpected strong provider')
        run('link-probe',link_argv(prepared,output,archives))
        headers=run('probe-elf',[TOOLS/'bin/riscv64-linux-readelf','-h','-l','-d',output/'link-probe.elf'])
        require('RISC-V' in headers and 'INTERP' not in headers and 'NEEDED' not in headers,'Probe not static RISC-V')
        linked=run('probe-symbols',[TOOLS/'bin/riscv64-linux-nm','-g',output/'link-probe.elf'])
        for symbol in ('akv_resident_platform_current_v1','ggml_akv_legacy_current_v1'):
            require(re.search(r'\bW\s+'+symbol+r'$',linked,re.M),'Linked provider not weak NULL implementation')
        for raw in re.findall(r'(?m)^LOAD (\S+)',(output/'link-probe.map').read_text()):
            p=Path(raw).resolve()
            if not p.is_relative_to(output):
                require(str(p) in pins and sha(p)==pins[str(p)],'Unpinned linker input: '+str(p))
        dependencies={}
        for dep in builddir.rglob('*.o.d'):
            for raw in dependency_names(dep.read_text()):
                p=Path(raw);p=p if p.is_absolute() else builddir/p;p=p.resolve()
                if p.is_relative_to(output): require(p.is_file(),'Missing generated dependency')
                else: require(str(p) in pins and sha(p)==pins[str(p)],'Unpinned compiler input: '+str(p))
                dependencies[str(p)]=sha(p)
        require(dependencies,'No compiler dependency evidence')
        verify(pins);require(inventory(prepared/'inputs')==read(prepared/'tree-inventory.json'),'Source membership drift')
        require(service_owner(args.service)==owner,'Service owner changed')
        write(output/'compiler-dependencies.json',dependencies)
        artifacts={str(p):sha(p) for p in output.rglob('*') if p.is_file()}
        report.update(state='BUILT_NOT_EXECUTED',post_pins_match=True,source_pins_sha256=receipt['source_pins_sha256'],
            static_libraries={n:dict(path=str(p),sha256=sha(p)) for n,p in archives.items()},
            link_probe=dict(path=str(output/'link-probe.elf'),sha256=sha(output/'link-probe.elf'),executed=False),
            translation_units=len(commands),compiler_dependencies=len(dependencies),artifacts=artifacts,
            frontend_include_dirs=receipt['frontend_include_dirs'],frontend_flags=receipt['frontend_flags'],
            link_order=receipt['link_order'],scope='Full static native GGML/llama compile/link closure; default NULL providers; no inference or ISA acceptance')
    except BaseException as exc:
        report['error']=repr(exc);raise
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,previous)
        report['elapsed_seconds']=time.monotonic()-started
        write(output/'commands.json',rows)
        report['commands_sha256']=sha(output/'commands.json')
        if 'artifacts' in report: report['artifacts'][str(output/'commands.json')]=report['commands_sha256']
        write(output/'build.json',report)
    return report

def main():
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    sub=parser.add_subparsers(dest='command',required=True);sub.add_parser('identity')
    prep=sub.add_parser('prepare');prep.add_argument('--output',type=Path,required=True)
    prep.add_argument('--reviewed-source-sha256',required=True)
    worker=sub.add_parser('build');worker.add_argument('--prepared',type=Path,required=True)
    worker.add_argument('--output',type=Path,required=True);worker.add_argument('--service',required=True)
    worker.add_argument('--reviewed-prepare-sha256',required=True)
    args=parser.parse_args()
    result=dict(files=identity()[0],source_sha256=identity()[1]) if args.command=='identity' else (
        prepare(args) if args.command=='prepare' else build(args))
    print(json.dumps(result,sort_keys=True))

if __name__=='__main__': main()
