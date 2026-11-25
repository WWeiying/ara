"""Owned build-only support, derived from sealed formats builder."""
import json
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import tarfile
from contract import ROOT, HERE
from check import require, digest


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
        ('established_x32',sdk/'apps/llama_q4k_repack_bench/repack_kernels.c',[])):
        b.compile(cc,flags+extra,source,objdir/(name+'.o'))
    link=b.out/'link.ld'
    b.run('linker-script',[cc,'-E','-P','-x','c','-DALIGNMENT=16',common/'arch.link.ld','-o',link]); b.pin(link)
    for directory,build in builds:
        c=build['case']; native=c['backend'] == 'native'
        candidate=not c['x32_symbol']
        symbol=c['kernel_symbol']
        defines=dict(EVAL_M=c['m'],EVAL_N=c['n'],EVAL_K=c['k'],EVAL_PROFILE=c['profile'],EVAL_BE=c['block_elements'],
            EVAL_AP=c['activation_profile'],EVAL_AB=c['activation_block_bytes'],EVAL_WB=c['weight_block_bytes'],
            EVAL_RVV=int(not native),EVAL_CANDIDATE=int(not native and candidate),EVAL_QUANT=c['quantizer'],
            EVAL_X32=symbol,EVAL_DIAGNOSTIC=int(args.diagnostic),EVAL_ID='"'+build['build_id']+'"')
        (directory/'config.h').write_text(''.join(f'#define {key} {value}\n' for key,value in defines.items()))
        assembly=directory/'data.S'
        blobs=(('eval_input',directory/'input_f32.bin'),
            ('eval_expected',directory/'expected.bin'),('eval_q8',directory/'expected_q8.bin'),
            ('eval_packed',Path(build['comparisons']['PACK']['path'])))
        assembly.write_text('.section .rodata,"a",@progbits\n'+''.join(
            f'.balign 64\n.global {name}\n{name}:\n.incbin "{path}"\n' for name,path in blobs) +
            '.section .data,"aw",@progbits\n.balign 64\n.global weights\nweights:\n.fill 64,1,0xa5\n' +
            f'.global eval_weights\neval_weights:\n.incbin "{build["weights_path"]}"\n.fill 64,1,0xa5\n')
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
        trial=b.run('trial-'+label,[objdump,'-d','--disassemble=projection_trial',elf]).decode()
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
