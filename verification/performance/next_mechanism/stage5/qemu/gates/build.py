#!/usr/bin/env python3
"""GNU-only directed guest build. No QEMU launch or model modifications."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import shlex
import struct
import subprocess
import sys

sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[5]
OUT=ROOT.parent/'ara_dsa_signoff_integration/verification/out'
REVISION='5ed375a25'
CC=Path('/home/wangwy/openproject/ara/install/riscv-gcc/bin/riscv64-unknown-elf-gcc')
OWN=('cases.py','build.py','check.py','test_gates.py','main.c','start.S','issue.S','link.ld','README.md')


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def save(path,value):
    with Path(path).open('x') as f:json.dump(value,f,indent=2,sort_keys=True);f.write('\n')
def require(condition,message):
    if not condition:raise ValueError(message)
def load(path,name):
    s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m


def elf_contract(path):
    data=Path(path).read_bytes();h=struct.unpack_from('<16sHHIQQQIHHHHHH',data)
    require(h[0][:6]==b'\x7fELF\x02\x01' and h[2]==243 and h[4]==0x80000000,'RV64 little-endian entry contract')
    sections=[struct.unpack_from('<IIQQQQIIQQ',data,h[6]+i*h[11]) for i in range(h[12])]
    symbols={}
    for section in sections:
        if section[1]!=2:continue
        strings=sections[section[6]];names=data[strings[4]:strings[4]+strings[5]]
        for offset in range(section[4],section[4]+section[5],section[9]):
            name,info,other,index,address,size=struct.unpack_from('<IBBHQQ',data,offset)
            if index and name:
                end=names.index(0,name);text=names[name:end].decode()
                symbols[text]=dict(address=address,size=size)
    def word(pc):
        for section in sections:
            if section[1]==1 and section[3]<=pc and pc+4<=section[3]+section[5]:
                return struct.unpack_from('<I',data,section[4]+pc-section[3])[0]
        raise ValueError('Entry PC not in ELF contents')
    return symbols,word


def build(output):
    output=Path(output).absolute()
    require(output.parent==OUT and output==output.resolve() and not output.exists(),'Fresh direct signoff output required')
    output.mkdir();inputs=output/'inputs';inputs.mkdir()
    pins={};commands=[];report=dict(state='FAIL',qemu_built=False,qemu_executed=False,rtl_executed=False)
    env=dict(PATH='/usr/bin:/bin',LC_ALL='C',HOME='/home/wangwy',PYTHONDONTWRITEBYTECODE='1')
    def pin(path):pins[str(Path(path).resolve())]=sha(path)
    def verify():
        for path,digest in pins.items():require(sha(path)==digest,'Source/tool drift: '+path)
    def run(label,argv):
        verify();argv=list(map(str,argv));commands.append(dict(label=label,argv=argv,cwd=str(output),timeout_seconds=120))
        with (output/(label+'.log')).open('x') as log:
            r=subprocess.run(argv,cwd=output,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=120)
        require(r.returncode==0,'Command failed: '+label)
        return (output/(label+'.log')).read_text()
    try:
        for n in OWN:
            pin(HERE/n);shutil.copyfile(HERE/n,inputs/n)
        abi=subprocess.check_output(['/usr/bin/git','-C',str(ROOT),'show',REVISION+':software/akv/include/akv/akv_abi.h'],timeout=30)
        (inputs/'akv_abi.h').write_bytes(abi)
        for path in inputs.iterdir():pin(path)
        pin(CC);pin(Path(sys.executable).resolve())
        c=load(inputs/'cases.py','directed_gate_cases')
        for name in ('cc1','as','ld'):
            p=run('locate-'+name,[CC,'-print-prog-name='+name]).strip()
            pin(Path(shutil.which(p,path=env['PATH']) or p).resolve(strict=True))
        objdump=CC.with_name('riscv64-unknown-elf-objdump');pin(objdump)
        run('host-tests',[sys.executable,'-B',inputs/'test_gates.py','-v'])
        flags=['-march=rv64gcv_zfh_zvfh','-mabi=lp64d','-mcmodel=medany','-mno-relax','-O2',
            '-ffreestanding','-fno-builtin','-fno-stack-protector','-fno-tree-vectorize',
            '-fno-tree-slp-vectorize','-fno-tree-loop-distribute-patterns','-fno-fast-math',
            '-ffunction-sections','-fdata-sections','-std=gnu11','-Wall','-Wextra','-Werror']
        variants=[]
        for mode in range(3):
            directory=output/('mode'+str(mode));directory.mkdir();manifest=c.emit(directory,mode)
            pin(directory/'fixture.h');pin(directory/'expected.json')
            objects=[]
            for source in ('start.S','issue.S','main.c'):
                obj=directory/(Path(source).stem+'.o');objects.append(obj)
                dependency=obj.with_suffix('.d')
                run(str(mode)+'-'+Path(source).stem,[CC,*flags,'-I'+str(inputs),'-I'+str(directory),
                    '-MD','-MF',dependency,'-c',inputs/source,'-o',obj])
                dependency_text=dependency.read_text().replace('\\\n',' ')
                for name in shlex.split(dependency_text.split(':',1)[1]):pin(Path(name))
            elf=directory/'directed.elf'
            run(str(mode)+'-link',[CC,*flags[:4],'-nostdlib','-nostartfiles','-static',
                *objects,'-T',inputs/'link.ld','-Wl,--gc-sections','-Wl,-Map='+str(directory/'link.map'),'-o',elf])
            run(str(mode)+'-disassembly',[objdump,'-d','-M','no-aliases,numeric',elf])
            symbols,word=elf_contract(elf);pcs={}
            for op in c.OP_NAMES:
                pc=symbols['gate_'+op+'_pc']['address'];require(word(pc)==c.instruction(op),'Wrong native instruction: '+op)
                pcs[op]=dict(pc=pc,insn=word(pc))
            addresses={n:symbols[n]['address'] for n in ('descriptor','queries','keys','values')}
            require(all(a%64==0 for a in addresses.values()),'Unaligned guest data')
            variants.append(dict(mode=mode,elf=str(elf),elf_sha256=sha(elf),cases=len(manifest['cases']),
                expected=str(directory/'expected.json'),expected_sha256=sha(directory/'expected.json'),
                pcs=pcs,addresses=addresses))
        verify();save(output/'commands.json',commands);save(output/'source-pins.json',pins)
        report.update(state='DIRECTED_GUESTS_BUILT_NOT_EXECUTED',variants=variants,
            sdk_abi_revision=REVISION,post_pins_match=True,source_pins_sha256=sha(output/'source-pins.json'),
            oracle='Exact dyadics, IEEE midpoint and canonical NaN constants; no model import',
            runtime='M-mode RV64, 16MiB RAM, private real trap handler, Stage4 UART/EOC transport')
    except BaseException as exc:report['error']=repr(exc)
    if not (output/'commands.json').exists():save(output/'commands.json',commands)
    report['artifacts']={str(p):sha(p) for p in output.rglob('*') if p.is_file()}
    save(output/'build.json',report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__,allow_abbrev=False);parser.add_argument('--output',type=Path,required=True)
    r=build(parser.parse_args().output);print(json.dumps({k:v for k,v in r.items() if k!='artifacts'},indent=2))
    raise SystemExit(int(r['state']=='FAIL'))
