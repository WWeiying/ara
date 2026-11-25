#!/usr/bin/env python3
"""Build-only nine-format successor. Never launches a simulator or hardware build."""
import argparse
import ctypes
import hashlib
import json
from pathlib import Path
import re
import shlex
import shutil
import struct
import subprocess
import sys
import tarfile

sys.dont_write_bytecode = True
from contract import (HERE, ROOT, OUT, SDK_COMMIT, LLAMA_COMMIT, LLAMA, TOOLCHAIN,
                      ROWS, ROWS_PINS, ROWS_RECEIPT, PARENT, PROFILES, ATOL, RTOL,
                      POLICY, cases, fnv, repack)
from check import digest, require


def write_json(path,value):
    path.write_text(json.dumps(value,indent=2,sort_keys=True)+'\n')


class Builder:
    def __init__(self,out):
        self.out,self.pins,self.commands=out,{},[]

    def pin(self,path):
        p=Path(path).absolute(); sha=digest(p)
        require(str(p) not in self.pins or self.pins[str(p)] == sha,'Build input changed: '+str(p))
        self.pins[str(p)]=sha

    def run(self,label,argv,cwd=None):
        argv=list(map(str,argv))
        self.commands.append(dict(label=label,argv=argv,cwd=str(cwd or ROOT),timeout_seconds=120))
        write_json(self.out/'commands.json',self.commands)
        exe=shutil.which(argv[0])
        if exe:
            self.pin(exe)
        p=subprocess.run(argv,cwd=cwd or ROOT,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=120)
        (self.out/(label+'.log')).write_bytes(p.stdout)
        require(p.returncode == 0,'Failed '+label+': '+p.stdout.decode(errors='replace')[-4000:])
        return p.stdout

    def archive(self,repo,commit,paths,destination):
        archive=self.out/(destination.name+'.tar')
        self.run(destination.name+'-archive',['git','-C',repo,'archive','--format=tar','-o',archive,commit,*paths])
        destination.mkdir(parents=True)
        with tarfile.open(archive) as tar:
            for member in tar.getmembers():
                require(not Path(member.name).is_absolute() and '..' not in Path(member.name).parts
                    and (member.isdir() or member.isfile()),'Unsafe archive member')
            tar.extractall(destination)
        self.pin(archive)

    def compile(self,cc,flags,source,obj):
        dep=obj.with_suffix('.d')
        label='compile-'+str(obj.relative_to(self.out)).replace('/','_')
        self.run(label,[cc,*flags,'-MD','-MF',dep,'-c',source,'-o',obj])
        for path in shlex.split(dep.read_text().replace('\\\n','').split(':',1)[1]):
            self.pin(path)
        self.pin(obj)


def requirements(args):
    cc=args.toolchain/'riscv64-unknown-elf-gcc'
    capture=ROWS/'attn_q'
    require(cc.is_file() and shutil.which(args.host_cc),'Host and RVV compilers required')
    require(digest(ROWS/'result.json') == ROWS_RECEIPT and digest(ROWS/'source-pins.json') == ROWS_PINS,
            'Reviewed capture receipt/inventory identity changed')
    receipt=json.loads((ROWS/'result.json').read_text())
    meta=json.loads((capture/'operator.json').read_text())
    require(receipt['state'] == 'CAPTURED_NOT_BENCHMARKED' and receipt['source_pins_match'] and
            receipt['rows'] == 8 and receipt['k'] == 2048 and meta in receipt['views'] and
            meta['activation_shape'] == [2048,8] and meta['distinct_rows'] == 8 and
            meta['captured_weight_shape'] == [2048,128] and meta['profile'] == 'Q4_K',
            'Capture scope/geometry changed')
    a,w=capture/'activation_f32.bin',capture/'weight_q4_K.bin'
    require(digest(a) == meta['activation_sha256'] and digest(w) == meta['weight_sha256'] and
            a.stat().st_size == 8*2048*4 and w.stat().st_size == 128*8*144,'Capture bytes changed')
    raw=a.read_bytes()
    require(len({raw[i*8192:(i+1)*8192] for i in range(8)}) == 8 and
            all(abs(v) < float('inf') for v, in struct.iter_unpack('<f',raw)), 'Nonfinite/non-distinct activations')
    for repo,commit in ((ROOT,SDK_COMMIT),(args.llama,LLAMA_COMMIT)):
        subprocess.run(['git','-C',str(repo),'cat-file','-e',commit+'^{commit}'],check=True,timeout=30)
    parent=json.loads((PARENT/'build.json').read_text())
    require(parent['state'] == 'CURRENT_OPERATOR_SOC_BUILT_NOT_EXECUTED' and parent['post_pins_match'],
            'Parent image receipt is not the requested current build')
    inventories=[]
    for path in sorted(OUT.glob('operator_campaign_20261115_*/source-pins.json')):
        pins=json.loads(path.read_text())
        inventories.append(dict(path=str(path),sha256=digest(path),pins=len(pins),
            owned_inputs=[name for name in pins if name.startswith(str(HERE)+'/')],
            documentation_pins=[name for name in pins if name.endswith('.md')]))
    return dict(state='REQUIREMENTS_AVAILABLE',sdk_commit=SDK_COMMIT,llama_commit=LLAMA_COMMIT,
        toolchain=str(cc),compiler_version=subprocess.check_output([cc,'--version'],timeout=30).decode().splitlines()[0],
        host_cc=str(shutil.which(args.host_cc)),capture=str(capture),metadata=meta,
        activation_selection='Same first M distinct rows, no synthesized/repeated activation rows',
        weight_selection='Same first 64 full-K actual Q4_K rows, then common dequantized F32 derivative',
        derivation='actual Q4_K -> upstream dequantize -> F32 (not original F16) -> upstream reference quantizers',
        native_format_model_captures=False,original_f16_weights=False,
        parent_image=str(PARENT),parent_receipt_sha256=digest(PARENT/'build.json'),
        worker_pin_inventories=inventories,max_vcs_workers=4,simulators_authorized=False)


def host_candidate_audit(b,lib,case,directory):
    if case['x32_symbol']:
        return dict(state='NOT_HOST_EXECUTABLE',reason='Established RVV instructions; firmware/disassembly only in this task')
    symbols={7:'formats_q2k_x32',3:'formats_q4_0_x32',8:'formats_q5_0_x32',9:'formats_iq4nl_x32'}
    function=getattr(lib,symbols[case['profile']])
    function.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.POINTER(ctypes.c_float),ctypes.c_uint]
    function.restype=None
    w=ctypes.create_string_buffer((directory/'weights_x32.bin').read_bytes())
    a=ctypes.create_string_buffer((directory/'expected_q8.bin').read_bytes())
    expected=[v for v, in struct.iter_unpack('<f',(directory/'expected.bin').read_bytes())]
    ab=case['k_blocks']*case['activation_block_bytes']
    wb=case['k_blocks']*case['weight_block_bytes']
    max_error=0.0
    for row in range(case['m']):
        for col in range(0,64,32):
            output=(ctypes.c_float*32)()
            function(ctypes.byref(w,col*wb),ctypes.byref(a,row*ab),output,2048)
            for i,value in enumerate(output):
                gold=expected[row*64+col+i]
                error=abs(value-gold); max_error=max(max_error,error)
                require(abs(value) < float('inf') and error <= ATOL+RTOL*abs(gold),
                        'Candidate scalar layout/arithmetical audit failed: '+case['id'])
    return dict(state='PASS',scope='Scalar port of new x32 candidate; not execution of RVV instructions',
                outputs_checked=len(expected),maximum_absolute_error=max_error)


def prepare(args):
    req=requirements(args)
    out=args.output.resolve()
    require(out.parent == OUT.resolve() and re.fullmatch(r'operator_formats_prepare_20261115_[A-Za-z0-9_]+',out.name)
            and not out.exists(),'Fresh owned signoff/out/operator_formats_prepare_20261115_* output required')
    selected=[c for c in cases() if (not args.case or c['id'] == args.case) and
              (args.suite == 'all' or c['backend'] == args.suite)]
    require(selected,'No selected cases')
    out.mkdir()
    b=Builder(out)
    write_json(out/'requirements.json',req)
    for path in sorted(HERE.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            b.pin(path)
    b.run('python-tests',[sys.executable,'-B','-m','unittest','discover','-s',HERE,'-p','test_formats.py','-v'])
    b.pin(out/'python-tests.log')
    b.pin(ROOT/'AGENTS.md')
    b.pin(PARENT/'build.json'); b.pin(PARENT/'source-pins.json')
    for p in (ROWS/'result.json',ROWS/'source-pins.json',ROWS/'attn_q/operator.json',
              ROWS/'attn_q/activation_f32.bin',ROWS/'attn_q/weight_q4_K.bin'):
        b.pin(p)
    sdk,llama=out/'inputs/sdk',out/'inputs/llama'
    b.archive(ROOT,SDK_COMMIT,['software/qbs','apps/common','apps/llama_q4k_repack_bench',
        'apps/llama_q4km_micro','apps/llama_qwen25_real/common/generate_case.py',
        'verification/qbs/qbs_ref.c','verification/qbs/qbs_ref.h'],sdk)
    b.archive(args.llama,LLAMA_COMMIT,['ggml/include','ggml/src'],llama)
    patch=sdk/'software/qbs/integrations/llama-decode-sums.patch'
    patch_present=(llama/'ggml/src/ggml-cpu/arch/riscv/q8_K-decode-sums.h').exists()
    if patch_present:
        b.run('llama-patch-reverse-check',['git','apply','--no-index','--reverse','--check',patch],llama)
    else:
        b.run('llama-patch-check',['git','apply','--no-index','--check',patch],llama)
        b.run('llama-patch-apply',['git','apply','--no-index',patch],llama)
    ggml=llama/'ggml'
    includes=['-I'+str(p) for p in (sdk/'software/qbs/include',sdk/'verification/qbs',HERE)]
    quant_includes=['-I'+str(ggml/p) for p in ('include','src','src/ggml-cpu','src/ggml-cpu/arch/riscv')]
    host_flags=['-std=c11','-O2','-fno-fast-math','-ffp-contract=off','-frounding-math',
        '-ffunction-sections','-fdata-sections',*includes]
    host=out/'host'; host.mkdir()
    strict=['-Wall','-Wextra','-Werror']
    for tool in ('cc1','as','ld'):
        name=b.run('host-locate-'+tool,[args.host_cc,'-print-prog-name='+tool]).decode().strip()
        b.pin(Path(name) if Path(name).is_file() else shutil.which(name))
    b.compile(args.host_cc,host_flags+strict,HERE/'compare_test.c',host/'compare_test.o')
    b.run('comparator-link',[args.host_cc,host/'compare_test.o','-lm','-o',host/'compare_test'])
    b.run('comparator-mutations',[host/'compare_test'])
    b.pin(host/'compare_test'); b.pin(out/'comparator-mutations.log')
    mutation=dict(state='PASS',test=str(host/'compare_test'),log=str(out/'comparator-mutations.log'),
                  log_sha256=digest(out/'comparator-mutations.log'),byte_mutations=9344,output_mutations=256)
    b.compile(args.host_cc,host_flags+quant_includes,ggml/'src/ggml-quants.c',host/'upstream_quant.o')
    b.compile(args.host_cc,host_flags+quant_includes+strict,HERE/'requantize.c',host/'requantize.o')
    b.run('requantizer-link',[args.host_cc,'-Wl,--gc-sections',host/'requantize.o',host/'upstream_quant.o',
                             '-lm','-o',host/'requantize'])
    oracle_objects=[]
    for source,name in ((HERE/'oracle.c','oracle'),(sdk/'verification/qbs/qbs_ref.c','ref'),
                        (sdk/'software/qbs/src/qbs_runtime.c','runtime')):
        obj=host/(name+'.o'); b.compile(args.host_cc,host_flags+strict,source,obj); oracle_objects.append(obj)
    b.run('oracle-link',[args.host_cc,*oracle_objects,'-lm','-o',host/'oracle'])
    b.run('candidate-host-library',[args.host_cc,*host_flags, '-shared','-fPIC',HERE/'x32_candidate.c',
                                   '-lm','-o',host/'candidate.so'])
    lib=ctypes.CDLL(str(host/'candidate.so'))
    for name in ('requantize','oracle','candidate.so'):
        b.pin(host/name)
    libraries=b.run('host-runtime-libraries',['ldd',host/'requantize',host/'oracle',host/'candidate.so']).decode()
    for name in re.findall(r'(/\S+)\s+\(',libraries):
        if Path(name).is_file():
            b.pin(name)
    data=out/'data'; data.mkdir()
    b.run('controlled-requantization',[host/'requantize',ROWS/'attn_q/weight_q4_K.bin',data])
    activation=(ROWS/'attn_q/activation_f32.bin').read_bytes()
    write_json(data/'provenance.json',dict(derivation=req['derivation'],source=req['capture'],metadata=req['metadata'],
        native_format_model_captures=False,original_f16_weights=False,same_source_for_all_profiles=True,
        source_weight_sha256=digest(ROWS/'attn_q/weight_q4_K.bin'),
        source_activation_sha256=digest(ROWS/'attn_q/activation_f32.bin'),
        upstream_commit=LLAMA_COMMIT,quantizers='quantize_row_<format>_ref',
        weight_quantization_and_cold_repack='offline, excluded equally from both ROIs',
        activation_quantization='real F32 to Q8_K/Q8_0 at runtime, included in ROI'))
    builds=[]
    case_root=out/'cases'; case_root.mkdir()
    for case in selected:
        directory=case_root/case['id']; directory.mkdir()
        m,fmt=case['m'],case['format']
        (directory/'input_f32.bin').write_bytes(activation[:m*2048*4])
        (directory/'weights_row.bin').write_bytes((data/('weight_'+fmt+'.bin')).read_bytes())
        plan=json.loads(b.run('oracle-'+case['id'],[host/'oracle',case['profile'],m,
            directory/'input_f32.bin',directory/'weights_row.bin',directory]))
        require(plan['k_blocks'] == case['k_blocks'] and plan['activation_profile'] == case['activation_profile'] and
                len(plan['commands']) == 2 and all(c['m'] == m and c['n'] == 32 for c in plan['commands']),
                'Profile-specific full-K plan changed')
        write_json(directory/'plan.json',plan)
        (directory/'weights_x32.bin').write_bytes(repack((directory/'weights_row.bin').read_bytes(),fmt))
        audit=host_candidate_audit(b,lib,case,directory)
        native=case['backend'] == 'native'
        pack=directory/('expected_packed.bin' if native or (fmt == 'q4_K' and m == 4) else 'expected_q8.bin')
        weight=directory/('weights_r4.bin' if native else 'weights_x32.bin')
        (directory/'guard_golden.bin').write_bytes(bytes([0xa5])*640)
        comparisons={}
        for kind,path in (('Q8',directory/'expected_q8.bin'),('PACK',pack),('OUT',directory/'expected.bin'),
                          ('GUARD',directory/'guard_golden.bin')):
            raw=path.read_bytes()
            comparisons[kind]=dict(path=str(path),count=len(raw)//(4 if kind == 'OUT' else 1),expected_hash=fnv(raw))
        build_id=hashlib.sha256(json.dumps(dict(case=case,source_pins=b.pins,comparisons=comparisons),sort_keys=True).encode()).hexdigest()
        build=dict(state='HOST_PREPARED_NOT_EXECUTED',case=case,build_id=build_id,plan=plan,
            plan_path=str(directory/'plan.json'),comparisons=comparisons,candidate_host_audit=audit,
            weights_path=str(weight),
            comparator_tests=mutation,output_policy=POLICY,diagnostic=args.diagnostic,
            numeric_contract=dict(native='bit_exact_ordered_qbs_ref',rvv_atol=ATOL,rvv_rtol=RTOL),
            flag_seeds=[0,8],sdk_commit=SDK_COMMIT,llama_commit=LLAMA_COMMIT,
            provenance=str(data/'provenance.json'),native_format_model_captures=False,original_f16_weights=False,
            baseline_kind=case['baseline_kind'],primary_eligible=case['primary_eligible'],
            rtl_executed=False,performance_measured=False,whole_model=False,full_output_width=False,reused_objects=0,
            parent_image=str(PARENT),max_vcs_workers=4,
            timing_contract='rdcycle phases: quant/pack/admit/execute/drain; one final fence; one commit marker pair; all checks/UART outside ROI',
            memory_contract='Single blocking worker; flat parent simulation RAM only; no FPGA NORMAL_MEMORY claim',
            registered_llama_patch='already_present_reverse_checked' if patch_present else 'applied_in_archive')
        builds.append((directory,build))
    archive=out/'goldens.tar'
    with tarfile.open(archive,'w') as tar:
        for path in sorted(data.iterdir()):
            tar.add(path,arcname=str(path.relative_to(out)),recursive=False)
        for directory,_ in builds:
            for path in sorted(directory.iterdir()):
                tar.add(path,arcname=str(path.relative_to(out)),recursive=False)
    b.pin(archive)
    if not args.host_only:
        firmware(args,b,sdk,ggml,includes,quant_includes,builds)
    b.pin(out/'commands.json')
    for path in out.glob('*.log'):
        b.pin(path)
    for path in sorted(data.iterdir()):
        b.pin(path)
    for directory,_ in builds:
        for path in sorted(directory.iterdir()):
            if path.is_file():
                b.pin(path)
    b.pin(out/'requirements.json')
    for name,sha in b.pins.items():
        require(digest(name) == sha,'Build-time drift: '+name)
    write_json(out/'source-pins.json',b.pins)
    manifest=[]
    for directory,build in builds:
        build.update(source_pins=str(out/'source-pins.json'),source_pins_sha256=digest(out/'source-pins.json'),
            post_pins_match=True,golden_archive=str(archive),golden_archive_sha256=digest(archive))
        if not args.host_only:
            checker=[sys.executable,'-B',str(HERE/'check.py'),'--build',str(directory),'--log','{log}','--output','{result}']
            build['checker']=checker
            manifest.append(dict(id=build['case']['id'],category='qbs',elf=build['elf'],elf_sha256=build['elf_sha256'],
                checker=checker,source_pins=str(out/'runner-source-pins.json'),timeout_seconds=10800,
                baseline_kind=build['baseline_kind'],primary_eligible=build['primary_eligible'],
                plusargs=['+QBS_PERF'] if build['case']['backend'] == 'native' else []))
        write_json(directory/'build.json',build)
    if manifest:
        write_json(out/'manifest.json',dict(cases=manifest))
        for backend in ('native','rvv_x32'):
            for m in (1,4):
                ids={c['id'] for c in selected if c['backend'] == backend and c['m'] == m}
                subset=[c for c in manifest if c['id'] in ids]
                if subset:
                    write_json(out/f'manifest_{backend}_m{m}.json',dict(cases=subset))
    summary=dict(state='HOST_PREPARED_NOT_EXECUTED' if args.host_only else 'BUILT_NOT_EXECUTED',
        cases=len(builds),case_ids=[build['case']['id'] for _,build in builds],
        rtl_executed=False,performance_measured=False,requirements=str(out/'requirements.json'),
        comparator_tests=mutation,source_pins_sha256=digest(out/'source-pins.json'),
        manifest=str(out/'manifest.json') if manifest else None,
        parent_image=str(PARENT),max_vcs_workers=4,output_policy=POLICY)
    write_json(out/'build.json',summary)
    runner_pins=dict(b.pins)
    for path in [out/'source-pins.json',out/'build.json',*(d/'build.json' for d,_ in builds),*out.glob('manifest*.json')]:
        runner_pins[str(path)]=digest(path)
    write_json(out/'runner-source-pins.json',runner_pins)
    print(json.dumps(summary,indent=2))


def firmware(args,b,sdk,ggml,includes,quant_includes,builds):
    cc=args.toolchain/'riscv64-unknown-elf-gcc'
    objdump=args.toolchain/'riscv64-unknown-elf-objdump'
    readelf=args.toolchain/'riscv64-unknown-elf-readelf'
    for tool in ('cc1','as','ld'):
        name=b.run('locate-'+tool,[cc,'-print-prog-name='+tool]).decode().strip()
        b.pin(Path(name) if Path(name).is_file() else shutil.which(name))
    arch=['-march=rv64gcv_zfh_zvfh','-mabi=lp64d']
    for lib in ('libc.a','libm.a','libgcc.a','libnosys.a'):
        b.pin(b.run('locate-'+lib,[cc,*arch,'-print-file-name='+lib]).decode().strip())
    common=sdk/'apps/common'
    flags=[*arch,'-mcmodel=medany','-mno-relax','-O3','-DNDEBUG','-fno-fast-math','-ffp-contract=off',
        '-fno-tree-vectorize','-ffunction-sections','-fdata-sections','-DNR_LANES=4','-DVLEN=1024',
        *includes,'-I'+str(common),'-I'+str(sdk/'apps/llama_q4k_repack_bench')]
    objdir=b.out/'firmware'; objdir.mkdir()
    shared=[]
    for filename in ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c'):
        obj=objdir/(Path(filename).stem+'.o')
        b.compile(cc,flags+(['-fno-builtin'] if filename == 'string.c' else []),common/filename,obj)
        shared.append(obj)
    for name,source,extra in (
        ('quant',ggml/'src/ggml-cpu/arch/riscv/quants.c',quant_includes),
        ('runtime',sdk/'software/qbs/src/qbs_runtime.c',[]),
        ('native',sdk/'software/qbs/src/qbs_native_riscv.c',[]),
        ('established_x32',sdk/'apps/llama_q4k_repack_bench/repack_kernels.c',[]),
        ('candidate_x32',HERE/'x32_candidate.c',[])):
        b.compile(cc,flags+extra,source,objdir/(name+'.o'))
    link=b.out/'link.ld'
    b.run('linker-script',[cc,'-E','-P','-x','c','-DALIGNMENT=16',common/'arch.link.ld','-o',link]); b.pin(link)
    for directory,build in builds:
        c=build['case']; native=c['backend'] == 'native'
        candidate=not c['x32_symbol']
        symbol=c['kernel_symbol']
        defines=dict(EVAL_M=c['m'],EVAL_PROFILE=c['profile'],EVAL_BE=c['block_elements'],
            EVAL_AP=c['activation_profile'],EVAL_AB=c['activation_block_bytes'],EVAL_WB=c['weight_block_bytes'],
            EVAL_RVV=int(not native),EVAL_CANDIDATE=int(not native and candidate),EVAL_QUANT=c['quantizer'],
            EVAL_X32=symbol,EVAL_DIAGNOSTIC=int(args.diagnostic),EVAL_ID='"'+build['build_id']+'"')
        (directory/'config.h').write_text(''.join(f'#define {key} {value}\n' for key,value in defines.items()))
        assembly=directory/'data.S'
        blobs=(('eval_input',directory/'input_f32.bin'),('eval_weights',Path(build['weights_path'])),
            ('eval_expected',directory/'expected.bin'),('eval_q8',directory/'expected_q8.bin'),
            ('eval_packed',Path(build['comparisons']['PACK']['path'])))
        assembly.write_text('.section .rodata,"a",@progbits\n'+''.join(
            f'.balign 64\n.global {name}\n{name}:\n.incbin "{path}"\n' for name,path in blobs))
        b.compile(cc,flags+['-I'+str(directory),'-Wall','-Wextra','-Werror'],HERE/'main.c',directory/'main.o')
        b.compile(cc,flags,assembly,directory/'data.o')
        objects=[*shared,objdir/'quant.o',directory/'main.o',directory/'data.o']
        objects+=([objdir/'runtime.o',objdir/'native.o'] if native else
                  [objdir/('candidate_x32.o' if candidate else 'established_x32.o')])
        if not native and c['format'] == 'q4_K' and c['m'] == 4:
            objects.append(objdir/'runtime.o')
        elf=directory/'operator.elf'
        label=c['id']
        b.run('link-'+label,[cc,*flags,'-static','-nostartfiles','-nostdlib',*objects,
            '-Wl,--gc-sections','-Wl,-Map='+str(directory/'link.map'),'-T',link,
            '-Wl,--start-group','-lm','-lc','-lgcc','-lnosys','-Wl,--end-group','-o',elf])
        quant=b.run('quant-'+label,[objdump,'-d','--disassemble='+c['quantizer'],elf]).decode()
        require('vle32.v' in quant and 'vse8.v' in quant and ('vfcvt' in quant or 'vfncvt' in quant),
                'Actual RVV quantizer absent')
        require(('csrwi\tvxrm,1' in quant) == (c['quant_vcsr'] == 2),'Quantizer VXRM disassembly contract')
        trial=b.run('trial-'+label,[objdump,'-d','--disassemble=formats_trial',elf]).decode()
        require(c['quantizer'] in trial and len(re.findall(r'\bfence\b',trial)) == 1 and
            len(re.findall(r'rdcycle\s+zero',trial)) == 2 and
            ('qbs_execute_with_options' in trial) == native,'Timing/backend/commit-marker audit')
        if not native:
            dot=b.run('kernel-'+label,[objdump,'-d','--disassemble='+symbol,elf]).decode()
            require('vfmacc' in dot and ('vwmacc' in dot or 'vmacc' in dot) and 'vse32' in dot,
                    'Real multi-output RVV kernel absent')
        else:
            executor=b.run('executor-'+label,[objdump,'-d','--disassemble=qbs_native_execute_command',elf]).decode()
            require('00b5045b' in executor and '06b5045b' in executor and 'vse32' in executor,
                    'Archived native custom commands/result stores absent')
        sections=b.run('sections-'+label,[readelf,'-SW',elf]).decode()
        # The archived linker bounds the image to 1MiB; ld fails on overflow.
        require('.text' in sections and '.rodata' in sections,'Missing firmware sections')
        build.update(state='BUILT_NOT_EXECUTED',elf=str(elf),elf_sha256=digest(elf),
            rebuilt_runtime_objects=len(objects),within_suite_common_objects=True)
        print(json.dumps(dict(state=build['state'],case=label)),flush=True)


def main():
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--requirements',action='store_true')
    p.add_argument('--list',action='store_true')
    p.add_argument('--suite',choices=('all','native','rvv_x32'),default='all')
    p.add_argument('--case')
    p.add_argument('--host-only',action='store_true')
    p.add_argument('--diagnostic',action='store_true')
    p.add_argument('--output',type=Path)
    p.add_argument('--llama',type=Path,default=LLAMA)
    p.add_argument('--toolchain',type=Path,default=TOOLCHAIN)
    p.add_argument('--host-cc',default='/usr/bin/gcc')
    a=p.parse_args()
    if a.list:
        print(json.dumps(dict(schema_version=1,cases=cases()),indent=2)); return
    if a.requirements:
        print(json.dumps(requirements(a),indent=2)); return
    if not a.output:
        p.error('--output required')
    prepare(a)


if __name__ == '__main__':
    main()
