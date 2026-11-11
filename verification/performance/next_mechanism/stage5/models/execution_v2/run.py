#!/usr/bin/env python3
"""Actual static model link, then S3-gated Linux preparation and one-shot worker."""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
BINDING = OUT/'stage5_models_binding_prepare_20261110_02'
BINDING_SHA = '21c07bab9f59a4fd1d849d13c636e5f42dc7642581929d801e9d8162d43c711a'
MODELS = OUT/'stage5_models_prepare_20261110_04'
MODELS_SHA = 'ae27251276ba052d232cf2bb3388f628069717fade303ec91e8bfa345ad662b2'
PLATFORM = Path('/home/wangwy/llama/platforms/cva6-qemu')
CC = PLATFORM/'tools/bin/riscv64-linux-gcc'
CXX = CC.with_name('riscv64-linux-g++')
CPIO = PLATFORM/'sdk/buildroot/output/build/linux-6.19.6/usr/gen_init_cpio'
BIOS, KERNEL = (PLATFORM/'images'/n for n in ('fw_dynamic.bin', 'Image'))
OWN = ('run.py', 'check.py', 'provider.c', 'provider_test.c', 'init.c', 'test_execution.py', 'README.md')
ARCHIVES = ('libllama.a', 'libggml.a', 'libggml-cpu.a', 'libggml-base.a')
FLAGS = ['-march=rv64gcv_zfh_zvfh', '-mabi=lp64d', '-O2', '-fno-fast-math', '-ffp-contract=off',
         '-fno-tree-vectorize', '-fno-tree-slp-vectorize', '-fno-tree-loop-distribute-patterns', '-fno-builtin']
PROVIDER_FLAGS = [*FLAGS, '-fno-stack-protector']
SYMBOLS = ('qbs_native_execute_command', 'akv_experimental_resident_qk',
           'akv_experimental_resident_pv', 'akv_experimental_resident_pv_prepare')
GATES = ['directed-native-lifecycle-fault-flags', 'unchanged-stage4-perf02',
         'unchanged-stage4-functional01', 'native-qbs-successor-smoke']
SEALED = OUT/'stage5_models_execution_link_20261110_04'
SEALED_RECEIPT = 'de87021c08493de19f51c04fbca225b376467753eb7744b15e8d3e3315b2cefb'
S3_READER = ROOT/'verification/performance/next_mechanism/stage5/qemu/execution/run.py'


def require(ok, text):
    if not ok: raise ValueError(text)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for data in iter(lambda: f.read(1024*1024), b''): h.update(data)
    return h.hexdigest()


def read(path):
    def pairs(rows):
        r = {}
        for k, v in rows:
            require(k not in r, 'Duplicate JSON key'); r[k] = v
        return r
    def invalid(v): raise ValueError('Nonfinite JSON: '+v)
    return json.loads(Path(path).read_text(), object_pairs_hook=pairs, parse_constant=invalid)


def save(path, value):
    with Path(path).open('x') as f: json.dump(value, f, indent=2, sort_keys=True, allow_nan=False); f.write('\n')


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def verify(pins):
    require(bool(pins), 'Empty pins')
    for path, digest in pins.items(): require(sha(path) == digest, 'Pin drift: '+str(path))


def merge(pins, extra):
    for path, digest in extra.items():
        path = str(path)
        require(path not in pins or pins[path] == digest, 'Conflicting pin: '+path)
        pins[path] = digest


def sealed_inputs():
    require(sha(SEALED/'prepare.json') == SEALED_RECEIPT, 'Execution-v1 ancestry')
    pins = {str(SEALED/'prepare.json'): SEALED_RECEIPT}
    for name, digest in read(SEALED/'prepare.json')['own_files'].items():
        pins[str(SEALED/'inputs'/name)] = digest
    verify(pins)
    return pins


def identity():
    files = {n: sha(HERE/n) for n in OWN}
    return files, hashlib.sha256(canonical(files)).hexdigest()


def load(path, name):
    s = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(s)
    old = list(sys.path); sys.path.insert(0, str(Path(path).parent))
    try: s.loader.exec_module(m)
    finally: sys.path[:] = old
    return m


def checked_s3(reader, reader_sha, result_dir, result_sha):
    # Called before any other non-stdlib helper import in this fresh process.
    reader = Path(reader).resolve(); result_dir = Path(result_dir).resolve()
    require(re.fullmatch('[0-9a-f]{64}', reader_sha or '') and sha(reader) == reader_sha,
            'Four-gate reader is not reviewed')
    require(S3_READER.is_file() and sha(S3_READER) == reader_sha, 'Not the owned four-gate aggregate reader')
    old = list(sys.path); sys.path.insert(0, str(reader.parent))
    try: report, pins = load(reader, 'model_s3_reader').checked_result(result_dir, result_sha)
    finally: sys.path[:] = old
    require(pins.get(str(reader)) == reader_sha, 'Four-gate reader absent from returned closure')
    require(report.get('state') == 'NATIVE_QEMU_FOUR_GATES_CHECKED' and report.get('completed_gates') == GATES,
            'All four S3 gates on the same image are mandatory')
    require(report['executable_sha256'] == sha(report['executable']), 'S3 executable drift')
    verify(pins)
    return report, pins


def checked_library(prepared, built, digest):
    require(sha(built/'build.json') == digest, 'Unreviewed complete library')
    b = read(built/'build.json'); p = read(prepared/'prepare.json')
    require(b['schema'] == 'stage5-libraries-build-v1' and b['state'] == 'BUILT_NOT_EXECUTED' and
            b['post_pins_match'] is True and b['native_execution'] is False and b['provider_registered'] is False,
            'Incomplete library build')
    require(p['schema'] == 'stage5-libraries-prepare-v2' and p['state'] == 'PREPARED_NOT_BUILT' and
            sha(prepared/'prepare.json') == b['prepare_sha256'] and
            sha(prepared/'source-pins.json') == b['source_pins_sha256'] == p['source_pins_sha256'], 'Library ancestry')
    pins = read(prepared/'source-pins.json'); merge(pins, b['artifacts'])
    merge(pins, {str(built/'build.json'): digest, str(prepared/'prepare.json'): b['prepare_sha256'],
                 str(prepared/'source-pins.json'): b['source_pins_sha256']})
    require(set(b['static_libraries']) == set(ARCHIVES), 'Wrong static archive set')
    require(b['frontend_include_dirs'] == p['frontend_include_dirs'] and
            b['frontend_flags'] == p['frontend_flags'], 'Frontend contract changed')
    for row in b['static_libraries'].values():
        require(pins.get(row['path']) == row['sha256'], 'Archive outside checked artifacts')
    verify(pins)
    return b, pins


def sources(case):
    require(sha(BINDING/'result.json') == BINDING_SHA and sha(MODELS/'result.json') == MODELS_SHA,
            'Frozen model/binding receipt changed')
    pins = read(BINDING/'source-pins.json'); merge(pins, read(BINDING/'result.json')['artifacts'])
    merge(pins, {str(BINDING/'result.json'): BINDING_SHA, str(MODELS/'result.json'): MODELS_SHA})
    spec = read(BINDING/'inputs'/case/'spec.json')
    require(spec['id'] == case and spec['binding_id'] is None, 'Not an unresolved frozen case')
    model = read(MODELS/'model-inventory.json')[spec['model']]
    # One pilot consumes one model, not all four large disks in models04.
    oldpins=read(MODELS/'source-pins.json')
    for name in (model['path'],model['disk'],str(BIOS),str(KERNEL),str(CPIO)):
        require(name in oldpins,'Asset absent from models04');merge(pins,{name:oldpins[name]})
    require(pins[model['path']]==model['sha256'] and pins[model['disk']]==model['disk_sha256'],'Selected model identity')
    verify(pins)
    return spec, model, pins


def frontend(source):
    anchors = [('#include <unistd.h>\n', '#include <unistd.h>\n#include <termios.h>\nextern "C" int stage5_provider_setup_v2(void);\n'),
        ('        binding_snapshot(mode, step, "before");',
         '        binding_snapshot(mode, step, "before");\n        need(tcdrain(STDOUT_FILENO) == 0, "phase_drain_before");'),
        ('        binding_snapshot(mode, step, "after");',
         '        binding_snapshot(mode, step, "after");\n        need(tcdrain(STDOUT_FILENO) == 0, "phase_drain_after");')]
    anchors.append(('    env(STAGE5_REVIEWED_RESIDENT_ENV, mode ? "1" : "0");',
        '    env(STAGE5_REVIEWED_RESIDENT_ENV, mode ? "1" : "0");\n'
        '    need(stage5_provider_setup_v2() == 1, "provider_os_setup");'))
    for old, new in anchors:
        require(source.count(old) == 1, 'Frozen observer anchor drift'); source = source.replace(old, new)
    return source


def header(contract, granted, model_path):
    digest = hashlib.sha256(canonical(contract)).hexdigest()
    return digest, ('#define STAGE5_PROVIDER_ENABLED '+str(int(granted))+'\n'+
        '#define STAGE5_CONTRACT_BYTES {'+','.join('0x'+digest[i:i+2] for i in range(0,64,2))+'}\n'+
        '#define STAGE5_MODEL_PATH '+json.dumps(model_path)+'\n')


def symbols(text):
    result = {}
    for line in text.splitlines():
        m = re.fullmatch(r'([0-9a-f]+) ([0-9a-f]+) [Tt] (\S+)', line)
        if m and m[3] in SYMBOLS:
            require(m[3] not in result and int(m[2], 16) > 0, 'Ambiguous native symbol')
            result[m[3]] = [int(m[1],16), int(m[1],16)+int(m[2],16)]
    require(set(result) == set(SYMBOLS), 'Native kernel symbol missing')
    return result


def recipes(output, contract, ranges):
    qemu = contract['s3']['executable']
    selected = [ranges[n] for n in (SYMBOLS[0], SYMBOLS[3])]
    return [qemu, '-M', 'virt', '-cpu', 'rv64,v=true,vlen=1024,elen=64,zfh=true,zvfh=true,xaraqbs=true,xaraakv=true,xaraakv-resident=true',
        '-smp', '1', '-m', '4G', '-display', 'none', '-monitor', 'none', '-serial', 'stdio',
        '-bios', str(BIOS), '-kernel', str(KERNEL), '-initrd', str(output/'initramfs.cpio'),
        '-drive', 'file='+contract['model']['disk']+',if=virtio,format=raw,readonly=on',
        '-append', 'console=ttyS0 rdinit=/init', '-trace', 'enable=akv_arch_*',
        '-d', 'in_asm,exec,nochain', '-dfilter', ','.join(f'0x{a:x}..0x{b-1:x}' for a,b in selected)]


def prepare(args):
    ancestry = sealed_inputs()
    own, source_sha = identity(); require(source_sha == args.source_sha256, 'Unreviewed execution source')
    granted = args.action == 'prepare'
    s3 = None; extra = {}
    if granted:
        s3, extra = checked_s3(args.s3_reader, args.s3_reader_sha256, args.s3_result, args.s3_sha256)
    library, pins = checked_library(args.library_prepare.resolve(), args.library_build.resolve(), args.library_sha256)
    spec, model, inherited = sources(args.case); merge(pins, inherited); merge(pins, extra); merge(pins, ancestry)
    out = args.output.absolute()
    require(out == out.resolve() and out.parent == OUT and re.fullmatch('stage5_models_execution_[A-Za-z0-9_]+',out.name)
            and not out.exists(), 'Fresh independent execution output required')
    out.mkdir(); inputs = out/'inputs'; inputs.mkdir()
    rows = []; result = dict(state='FAIL', model_executed=False, provider_executed=False, execution_authorized=False)
    def pin(p): merge(pins, {str(Path(p).absolute()): sha(p)})
    def command(label, argv, timeout=120):
        argv = list(map(str, argv)); rows.append(dict(label=label,argv=argv,timeout_seconds=timeout))
        with (out/(label+'.log')).open('x') as log:
            done = subprocess.run(argv,cwd=out,env=dict(PATH=str(CC.parent)+':/usr/bin:/bin',HOME=str(out),
                LC_ALL='C',LANG='C',PYTHONDONTWRITEBYTECODE='1'),stdout=log,stderr=subprocess.STDOUT,timeout=timeout)
        require(done.returncode == 0, 'Failed '+label); return (out/(label+'.log')).read_text()
    try:
        for name in OWN:
            pin(HERE/name); shutil.copyfile(HERE/name, inputs/name)
            require(sha(inputs/name) == own[name], 'Source copy changed')
        for name in ('observe.h','check.py'):
            source = BINDING/'inputs'/name; dest = inputs/('binding_check.py' if name=='check.py' else name)
            shutil.copyfile(source,dest); require(sha(dest)==pins[str(source)],'Observer copy differs')
        shutil.copyfile(BINDING/'inputs'/args.case/'case_config.h',inputs/'case_config.h')
        (inputs/'model_pair.cpp').write_text(frontend((BINDING/'inputs/model_pair.cpp').read_text()))
        contract = dict(schema='stage5-model-execution-contract-v1',case=args.case,source_sha256=source_sha,
            binding_sha256=BINDING_SHA,model=model,case_header_sha256=sha(inputs/'case_config.h'),
            library_prepare=str(args.library_prepare.resolve()),library_build=str(args.library_build.resolve()),
            library_sha256=args.library_sha256,s3=s3,granted=granted,
            s3_reader=str(args.s3_reader.resolve()) if granted else None,
            s3_reader_sha256=args.s3_reader_sha256 if granted else None,
            s3_result=str(args.s3_result.resolve()) if granted else None,s3_sha256=args.s3_sha256 if granted else None,
            kernel_sha256=sha(KERNEL),bios_sha256=sha(BIOS),single_worker=True,guest_memory='4G',host_memory_max='8G',
            input_closure_sha256=hashlib.sha256(canonical(pins)).hexdigest(),automatic_retry=False)
        # Both link-only and final preparation compile the real positive provider.
        # Only the latter has a validated S3 contract and a launchable receipt.
        binding_id, text = header(contract,True,model['guest_path'])
        (inputs/'execution_contract.h').write_text(text); save(out/'contract.json',contract)
        spec['binding_id']=binding_id; spec['execution_authorized']=False; save(out/'spec.json',spec)
        include = ['-I'+str(inputs),*['-I'+p for p in library['frontend_include_dirs']]]
        for tool in (CC,CXX,CC.with_name('riscv64-linux-nm'),CC.with_name('riscv64-linux-readelf'),
                     CC.with_name('riscv64-linux-objdump'),CPIO):
            pin(tool); pin(tool.resolve())
        command('frontend',[CXX,'-std=c++17',*FLAGS,*include,'-DSTAGE5_REVIEWED_RESIDENT_ENV="GGML_RISCV_AKV_RESIDENT"',
            '-DSTAGE5_BINDING_ID="'+binding_id+'"','-MD','-MF',out/'frontend.d','-c',inputs/'model_pair.cpp','-o',out/'frontend.o'])
        command('provider',[CC,'-std=gnu11',*PROVIDER_FLAGS,*include,'-Wall','-Wextra','-Werror','-MD','-MF',out/'provider.d',
            '-c',inputs/'provider.c','-o',out/'provider.o'])
        undefined=command('provider-undefined',[CC.with_name('riscv64-linux-nm'),'-u',out/'provider.o'])
        require(undefined.split()==['U','akv_resident_platform_read_state_v1'],'Positive provider was elided or imports libc')
        command('link',[CXX,*FLAGS,'-static','-no-pie',out/'frontend.o',out/'provider.o','-Wl,--start-group',
            *[library['static_libraries'][n]['path'] for n in ARCHIVES],'-Wl,--end-group','-lm','-pthread','-ldl','-latomic',
            '-Wl,-Map='+str(out/'link.map'),'-o',out/'test'])
        elf = command('elf',[CC.with_name('riscv64-linux-readelf'),'-h','-l','-d',out/'test'])
        require('RISC-V' in elf and 'INTERP' not in elf and 'NEEDED' not in elf,'Not static RISC-V')
        names=command('symbols',[CC.with_name('riscv64-linux-nm'),'-S',out/'test'])
        for n in ('akv_resident_platform_current_v1','ggml_akv_legacy_current_v1'):
            require(re.search(r'\bT '+n+r'$',names,re.M),'Provider did not override weak default')
        ranges=symbols(names); save(out/'symbols.json',ranges)
        disassembly='\n'.join(command('disassemble-'+name,
            [CC.with_name('riscv64-linux-objdump'),'-d','--disassemble='+name,out/'test']) for name in SYMBOLS)
        pcs={'qk':[],'pv':[]}
        for m in re.finditer(r'(?m)^\s*([0-9a-f]+):\s+([0-9a-f]{8})\s',disassembly):
            pc,insn=int(m[1],16),int(m[2],16)
            for kind,f7 in (('qk',3),('pv',2)):
                if insn&127==0x5b and (insn>>12)&7==7 and insn>>25==f7: pcs[kind].append(pc)
        require(all(pcs.values()),'Resident custom instructions not linked'); save(out/'pcs.json',pcs)
        command('init',[CC,'-march=rv64gc','-mabi=lp64d','-O2','-static','-MD','-MF',out/'init.d',inputs/'init.c','-o',out/'init'])
        (out/'initramfs.list').write_text('dir /dev 755 0 0\nnod /dev/console 600 0 0 c 5 1\n'+
            'dir /proc 755 0 0\ndir /model 755 0 0\ndir /tmp 1777 0 0\n'+
            f'file /init {out/"init"} 755 0 0\nfile /test {out/"test"} 755 0 0\n')
        with (out/'initramfs.cpio').open('xb') as stream:
            subprocess.run([CPIO,out/'initramfs.list'],stdout=stream,check=True,timeout=60)
        if granted:
            save(out/'qemu-command.json',recipes(out,contract,ranges))
        for dep in out.glob('*.d'):
            for name in shlex.split(dep.read_text().replace('\\\n','').split(':',1)[1]):
                p=Path(name).resolve()
                require(p.is_relative_to(out) or pins.get(str(p))==sha(p),'Unpinned compiler dependency: '+str(p)); pin(p)
        for raw in re.findall(r'(?m)^LOAD (\S+)',(out/'link.map').read_text()):
            p=Path(raw).resolve()
            require(p.is_relative_to(out) or pins.get(str(p))==sha(p),'Unpinned static link input: '+str(p)); pin(p)
        save(out/'commands.json',rows)
        for p in out.rglob('*'):
            if p.is_file(): pin(p)
        verify(pins); save(out/'source-pins.json',pins)
        result.update(state='PREPARED_NOT_EXECUTED' if granted else 'LINKED_PROVIDER_NOT_AUTHORIZED',
            source_pins_sha256=sha(out/'source-pins.json'),source_sha256=source_sha,pins=len(pins),post_pins_match=True,
            case=args.case,elf=str(out/'test'),elf_sha256=sha(out/'test'),provider_linked=True,provider_enabled_in_elf=True,provider_granted=granted,
            initramfs_sha256=sha(out/'initramfs.cpio'),selected_model_assets_rechecked=True,all_other_models_rehashed=False,
            binding_id=binding_id,library_build_sha256=args.library_sha256,own_files=own)
    except BaseException as e:
        result['error']=repr(e)
        if not (out/'commands.json').exists(): save(out/'commands.json',rows)
        raise
    finally: save(out/'prepare.json',result)
    print(json.dumps(result,sort_keys=True))


def service_owner(out):
    unit='stage5-model-'+out.name+'.service'
    invocation=os.environ.get('INVOCATION_ID','')
    require(re.fullmatch('[0-9a-f]{32}',invocation) and '/'+unit in Path('/proc/self/cgroup').read_text(),'Direct systemd worker required')
    text=subprocess.check_output(['systemctl','--user','show',unit,
        '--property=MainPID,MemoryMax,CPUQuotaPerSecUSec,KillMode'],text=True)
    properties=dict(line.split('=',1) for line in text.splitlines())
    require(properties==dict(MainPID=str(os.getpid()),MemoryMax=str(8*1024**3),
        CPUQuotaPerSecUSec='1s',KillMode='control-group'),'Wrong service ownership/resources')
    return dict(unit=unit,pid=os.getpid(),invocation=invocation,cgroup=Path('/proc/self/cgroup').read_text(),properties=properties)


def service_command(out, review, prepared_sha):
    out=out.resolve()
    require(sha(out/'source-pins.json')==review and sha(out/'prepare.json')==prepared_sha,'Unreviewed prepared model')
    p=read(out/'prepare.json')
    require(p['state']=='PREPARED_NOT_EXECUTED' and p['provider_granted'] is True,'No runnable model preparation')
    return ['systemd-run','--user','--collect','--unit=stage5-model-'+out.name+'.service',
        '--property=Type=exec','--property=MemoryMax=8G','--property=CPUQuota=100%',
        '--property=RuntimeMaxSec=6300','--property=KillMode=control-group','--property=TimeoutStopSec=30',
        '--property=StandardOutput=append:'+str(out/'service.stdout.log'),
        '--property=StandardError=append:'+str(out/'service.stderr.log'),
        '--setenv=PYTHONPATH=','--setenv=PYTHONNOUSERSITE=1','--setenv=PYTHONDONTWRITEBYTECODE=1',
        '/usr/bin/python3','-B',str(out/'inputs/run.py'),'run','--output',str(out),
        '--review-sha256',review,'--review-prepare-sha256',prepared_sha]


def host(args):
    out=args.output.absolute()
    require(out==out.resolve() and out.parent==OUT and re.fullmatch('stage5_models_execution_host_[A-Za-z0-9_]+',out.name)
            and not out.exists(),'Fresh independent host output required')
    out.mkdir(); inputs=out/'inputs';inputs.mkdir()
    basepath=ROOT/'verification/performance/chain_profile/q6_decode/build.py'
    oldpins=read(BINDING/'source-pins.json')
    require(oldpins[str(basepath)]==sha(basepath),'Host command helper drift')
    base=load(basepath,'model_execution_host_builder');b=base.Builder(out);b.pin(basepath)
    for path in sealed_inputs(): b.pin(Path(path))
    result=dict(state='FAIL',model_executed=False,native_executed=False)
    try:
        for name in OWN:b.pin(HERE/name);shutil.copyfile(HERE/name,inputs/name)
        test_log=b.run('recipe-tests',[sys.executable,'-B','-m','unittest','test_execution','-v'],cwd=inputs).decode()
        test_count=re.search(r'Ran ([0-9]+) tests? in ',test_log)
        require(test_count is not None,'Missing host unittest count')
        inc=['-I'+str(BINDING/'inputs'),'-I'+str(MODELS/'inputs/sdk/software/akv/include'),
             '-I'+str(MODELS/'inputs/sdk/software/akv/experimental'),'-I'+str(inputs)]
        uapi=out/'uapi';(uapi/'asm').mkdir(parents=True);(uapi/'linux').mkdir()
        sysroot=PLATFORM/'tools/riscv64-buildroot-linux-gnu/sysroot/usr/include'
        for name in ('asm/hwprobe.h','linux/prctl.h'):
            b.pin(sysroot/name);shutil.copyfile(sysroot/name,uapi/name)
        for variant,grant,extra in (('off',False,[]),('on',True,[]),('ubsan',True,['-fsanitize=undefined','-fno-sanitize-recover=all'])):
            work=out/variant;work.mkdir();(work/'execution_contract.h').write_text(header({'host_fixture_only':variant},grant,'/model/test')[1])
            compiler='/usr/bin/clang' if variant=='ubsan' else '/usr/bin/gcc'
            scalar=['-fno-vectorize','-fno-slp-vectorize'] if variant=='ubsan' else ['-fno-tree-vectorize','-fno-tree-slp-vectorize']
            b.run(variant+'-build',[compiler,'-std=gnu11','-O2','-Wall','-Wextra','-Werror',*scalar,
                *extra,'-I'+str(work),'-I'+str(uapi),*inc,'-MD','-MF',work/'fixture.d',
                inputs/'provider_test.c','-o',work/'fixture'])
            b.run(variant+'-run',[work/'fixture'])
        target=out/'gnu';target.mkdir()
        (target/'execution_contract.h').write_text(header({'compile_only':True},True,'/model/test')[1])
        b.run('gnu-provider',[CC,'-std=gnu11',*PROVIDER_FLAGS,'-Wall','-Wextra','-Werror','-I'+str(target),*inc,
            '-MD','-MF',target/'provider.d','-c',inputs/'provider.c','-o',target/'provider.o'])
        listing=b.run('gnu-provider-disassembly',[CC.with_name('riscv64-linux-objdump'),'-dr',target/'provider.o']).decode()
        for mnemonic in re.findall(r'^\s*[0-9a-f]+:\s+[0-9a-f]+\s+(\S+)',listing,re.M):
            require(mnemonic in ('csrw','fscsr') or not mnemonic.startswith(('v','csr','fr','fs','fc','fm','fn','fe','fl','fd','fa')), 'Provider is not scalar: '+mnemonic)
        writes=re.findall(r'\b(?:csrw|fscsr)\s+([^\n]+)',listing)
        require(len(writes)==3 and sum(v.startswith('vcsr,') for v in writes)==1 and
            sum(v.startswith('vstart,') for v in writes)==1,'Only acquire snapshot restoration is permitted')
        require('.word' not in listing and '.insn' not in listing,'Unknown provider opcode')
        undefined=b.run('gnu-provider-undefined',[CC.with_name('riscv64-linux-nm'),'-u',target/'provider.o']).decode()
        require(undefined.split()==['U','akv_resident_platform_read_state_v1'],'Unexpected provider libc/SDK call')
        b.run('gnu-init',[CC,'-march=rv64gc','-mabi=lp64d','-O2','-Wall','-Wextra','-Werror',
            '-MD','-MF',target/'init.d','-c',inputs/'init.c','-o',target/'init.o'])
        for dep in out.rglob('*.d'):
            for name in shlex.split(dep.read_text().replace('\\\n','').split(':',1)[1]):b.pin(Path(name).resolve())
        for tool in (CC,CC.with_name('riscv64-linux-objdump'),CC.with_name('riscv64-linux-nm')):
            b.pin(tool);b.pin(tool.resolve())
        for p in out.rglob('*'):
            if p.is_file():b.pin(p)
        verify(b.pins);save(out/'source-pins.json',b.pins)
        result.update(state='HOST_POLICY_AND_GNU_PASS_NOT_NATIVE',recipe_tests=int(test_count[1]),host_policy_variants=3,
            gnu_compile_only_objects=2,source_pins_sha256=sha(out/'source-pins.json'),pins=len(b.pins),post_pins_match=True,
            own_files=identity()[0],source_sha256=identity()[1])
    except BaseException as e:result['error']=repr(e);raise
    finally:save(out/'result.json',result)
    print(json.dumps(result,sort_keys=True))


def execute(args):
    out=args.output.resolve(); require(HERE==out/'inputs','Use frozen execution worker')
    require(args.review_sha256==sha(out/'source-pins.json'),'Unreviewed launch pins')
    require(args.review_prepare_sha256==sha(out/'prepare.json'),'Unreviewed preparation receipt')
    require(not any((out/n).exists() for n in ('attempt.json','result.json','guest.log','qemu-process.json')),'No retry/stale execution output')
    p=read(out/'prepare.json'); require(p['state']=='PREPARED_NOT_EXECUTED' and p['provider_granted'] is True,
        'S3-unbound prelink is not authorized to run')
    owner=service_owner(out); save(out/'attempt.json',owner)
    report=dict(state='FAIL',model_executed=False,automatic_retry=False,performance_measured=False,owner=owner)
    child=None
    try:
        pins=read(out/'source-pins.json'); verify(pins)
        c=read(out/'contract.json')
        s3,_=checked_s3(c['s3_reader'],c['s3_reader_sha256'],c['s3_result'],c['s3_sha256'])
        require(canonical(c['s3'])==canonical(s3),'S3 receipt changed')
        require(sha(out/'test')==p['elf_sha256'],'Model ELF changed')
        command=read(out/'qemu-command.json'); require(command==recipes(out,c,read(out/'symbols.json')),'Launch recipe changed')
        with (out/'guest.log').open('xb') as log:
            child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,
                cwd=out,env=dict(PATH='/usr/bin:/bin',HOME=str(out),LANG='C',LC_ALL='C'))
            save(out/'qemu-process.json',dict(pid=child.pid,cgroup=Path(f'/proc/{child.pid}/cgroup').read_text(),command=command))
            require(Path(f'/proc/{child.pid}/cgroup').read_text()==owner['cgroup'],'QEMU escaped service')
            report['model_executed']=True; rc=child.wait(timeout=5400)
        require(rc==0,'Nonzero QEMU exit')
        proof=load(out/'inputs/check.py','execution_checker').check(out)
        verify(pins); require(service_owner(out)==owner,'Service ownership changed')
        save(out/'checked.json',proof)
        report.update(state='MODEL_PAIR_CHECKED',post_pins_match=True,proof=proof,log_sha256=sha(out/'guest.log'))
    except BaseException as e:
        if child is not None and child.poll() is None: child.kill(); child.wait()
        report['error']=repr(e)
    save(out/'result.json',report); print(json.dumps(report,sort_keys=True)); return report['state']=='MODEL_PAIR_CHECKED'


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False); sub=p.add_subparsers(dest='action',required=True)
    sub.add_parser('identity')
    a=sub.add_parser('host',allow_abbrev=False);a.add_argument('--output',type=Path,required=True)
    for action in ('link','prepare'):
        a=sub.add_parser(action,allow_abbrev=False)
        for name in ('output','library-prepare','library-build'): a.add_argument('--'+name,type=Path,required=True)
        for name in ('source-sha256','library-sha256','case'): a.add_argument('--'+name,required=True)
        if action=='prepare':
            for name in ('s3-reader','s3-result'): a.add_argument('--'+name,type=Path,required=True)
            for name in ('s3-reader-sha256','s3-sha256'): a.add_argument('--'+name,required=True)
    for action in ('run','service-command'):
        a=sub.add_parser(action,allow_abbrev=False); a.add_argument('--output',type=Path,required=True)
        a.add_argument('--review-sha256',required=True);a.add_argument('--review-prepare-sha256',required=True)
    args=p.parse_args()
    if args.action=='identity': print(json.dumps(dict(files=identity()[0],sha256=identity()[1]),indent=2))
    elif args.action=='host':host(args)
    elif args.action=='service-command':print(json.dumps(service_command(args.output,args.review_sha256,args.review_prepare_sha256),indent=2))
    elif args.action=='run': return 0 if execute(args) else 1
    else: prepare(args)
    return 0


if __name__=='__main__': sys.exit(main())
