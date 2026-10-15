#!/usr/bin/env python3
"""One software-only full original reduction port and conditional dual compile."""
import difflib
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
G = HERE.parents[1]
ARCHIVE = Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_verified_handoff03/rvv_small_redspecial02/rvv_small_fp_redspecial_e16_mf4')
SOURCE = Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/fp_reduction_oracle.c')
NAME = 'fp_redspecial_e16_mf4_full6720'

def load(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    module=importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    return module

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def save(path,value):
    with Path(path).open('x') as stream: json.dump(value,stream,indent=2); stream.write('\n')
def text(path,value):
    with Path(path).open('x') as stream: stream.write(value)
def require(value,message):
    if not value: raise ValueError(message)
def replace(source,old,new):
    require(source.count(old)==1,'Exact replacement: '+old[:70])
    return source.replace(old,new)

def main():
    out=HERE/'execution01'; out.mkdir()
    base=G/'fp_compare_unboxed_full17920_prepare01/compile01/execute.py'
    common=load('sealed_software_commands',base)
    adapter=G/'integration/prepare.py'
    integration=load('sealed_integration_adapter',adapter)
    case=json.loads((ARCHIVE/'case.json').read_text())['case']
    paths=[Path(__file__),HERE/'host.c',HERE/'packed.h',base,adapter,SOURCE,ARCHIVE/'case.json',
           ARCHIVE/'original.elf',ARCHIVE.parent/'original_report.json',
           G/'ordered_reduction/original_e16_mf4_prepare01/sourceproof.json',common.CC.resolve(),Path('/usr/bin/gcc').resolve()]
    paths += [ARCHIVE/n for n in case['scenario_sources']]
    paths += [G/'integration'/n for n in ('runtime.c','startup.S','replay.ld')]
    pins={str(p):sha(p) for p in paths}; save(out/'inputs_before.json',pins)
    try:
        require(sha(SOURCE)=='f92ffb3af070febf3dfebb85b0a25f6c5612b95044e2aa1262d600687926eb4f','Exact full C')
        require(sha(ARCHIVE/'original.elf')==case['original_elf_sha256']=='0e20bf3cf1449d2d4ce4b9dbf482d107154966554031bcd02cd35f9008e282ec','Original ELF')
        for n,h in case['scenario_sources'].items(): require(sha(ARCHIVE/n)==h,'Original header '+n)
        original=SOURCE.read_text()
        selector='                if(!(scenario==3 && l==4 && mode==3 && rm==0 && op==0 && sticky==0))continue;\n'
        require(replace((ARCHIVE/'scenario.c').read_text(),selector,'')==original,'Full parent vs reduced selector')
        sw=out/'software'; sw.mkdir(); orig=sw/'original'; orig.mkdir()
        shutil.copyfile(SOURCE,orig/'parent.c')
        for n in ('operations.S','operations.h','fixtures.h','input_bits.h','fp_reduction_inputs.h'):
            shutil.copyfile(ARCHIVE/n,orig/n)
        for n in ('runtime.c','startup.S','replay.ld'): shutil.copyfile(G/'integration'/n,sw/n)
        shutil.copyfile(HERE/'packed.h',sw/'packed.h')
        plain=integration.adapt(original,NAME)
        candidate=replace(plain,'static word input[512],seed[64];','static word input[512] __attribute__((aligned(8))),seed[64] __attribute__((aligned(8)));')
        candidate=replace(candidate,'static uint8_t output[144] __attribute__((aligned(8))),mask[64];','static uint8_t output[144] __attribute__((aligned(8))),mask[64] __attribute__((aligned(8)));\n#include "packed.h"')
        candidate=replace(candidate,'for(unsigned i=0;i<64;++i)seed[i]=reduction_seed(scenario);','seed_initialize(seed,(uint16_t)reduction_seed(scenario));')
        candidate=replace(candidate,'for(unsigned i=0;i<64;++i)mask[i]=mode==0 ? 255:mode==1 ? 0:mode==2 ? 0x55:0x24;','mask_initialize(mask,mode);')
        candidate=replace(candidate,'for(unsigned i=0;i<144;++i)output[i]=0x5b;','output_initialize(output);')
        begin=candidate.index('                for(unsigned i=0;i<144;++i){')
        end=candidate.index('                if(errors!=prior',begin)
        byte_oracle=candidate[begin:end]
        candidate=candidate[:begin]+'                if(packed_mismatch(output,wanted.bits,vl)) {\n'+byte_oracle+'                }\n'+candidate[end:]
        candidate='#if SEW != 16 || CAP512 != 8 || CAP1024 != 16\n#error Original shape required\n#endif\n'+candidate
        text(sw/'case.c',candidate)
        text(sw/'source.diff',''.join(difflib.unified_diff(original.splitlines(True),candidate.splitlines(True))))
        text(sw/'main.c','extern int '+NAME+'_main(void);\nextern void replay_text(const char *);\nint main(void) {\n replay_text("BOARD_CASE_BEGIN '+NAME+'\\n");\n int rc='+NAME+'_main();\n if(rc) { replay_text("BOARD_CASE_FAIL '+NAME+'\\n"); return rc; }\n replay_text("BOARD_CASE_PASS '+NAME+'\\nBOARD_REPLAY_PASS\\n"); return 0;\n}\n')
        save(out/'sourceproof.json',dict(original_name='rvv_fp_redspecial_e16_mf4',original_elf=case['original_elf_sha256'],source=sha(SOURCE),scope_calls=6720,
             counts=dict(result_bytes=967680,flags=6720,vstart=6720,mask_initializations=3360,scenario_input_initializations=8,seed_words_per_scenario=64),
             original_helpers='three unchanged21-instruction bodies plus capacity3',oracle='All144 bytes; combined status error; original errors<20 diagnostics',Linux=False))
        host=out/'host'; host.mkdir()
        csr='unsigned long vlenb;__asm__ volatile("csrr %0,vlenb":"=r"(vlenb));'
        text(host/'original_case.c',replace(plain,csr,'unsigned long vlenb=128;'))
        text(host/'case.c',replace(candidate,csr,'unsigned long vlenb=128;'))
        flags=['-DSEW=16','-DCAP512=8','-DCAP1024=16']
        hostflags=['-O2','-std=c11','-Wall','-Wextra','-Werror','-Wno-unused-function','-fsanitize=undefined','-fsanitize-undefined-trap-on-error']
        save(out/'FIXED_CONFIGURATION.json',dict(compiler=str(common.CC),flags=common.FLAGS,defines=flags,Host_flags=hostflags,
             backends=['soc','spike'],reference=False,DUT=False,retries=0,Host_timeout_s=120,compiler_timeout_s=120))
        for variant in ('original','packed'):
            common.command(['/usr/bin/gcc',*hostflags,*flags,'-DHOST_CHECK=1','-DORIGINAL_RUN='+str(int(variant=='original')),
                 '-I'+str(host),'-I'+str(sw),'-I'+str(orig),HERE/'host.c','-o',host/variant],host/('compile_'+variant),timeout=120)
        tests={}
        for mode in ('positive','each_byte','status','flags','mixed','boundary','VL0','wrong_bank','wrong_nan'):
            logs=[]
            for variant in ('original','packed'):
                key=variant+'_'+mode
                tests[key]=common.command([host/variant,mode],host/key,timeout=120)
                lines=(host/(key+'.log')).read_text().splitlines()
                require(any(l.startswith('HOST_PASS ') for l in lines),'Full Host receipt')
                logs.append([l for l in lines if not l.startswith('HOST_PASS ')])
            require(logs[0]==logs[1],'Full original/packed error transcript '+mode)
        for mode,reason in [('drop_output','output_stores == 18'),('drop_mask','mask_stores == 8'),('drop_seed','seed_stores == 16'),('drop_read','loads == 18')]:
            tests[mode]=common.command([host/'packed',mode],host/mode,timeout=120,expected=90)
            require(reason in (host/(mode+'.log')).read_text(),'Exact negative rejection '+mode)
        save(host/'RESULT.json',dict(status='HOST_ORIGINAL_C_FULL6720_PASS_NOT_REFERENCE',tests=tests,full_modes=9,full_calls_per_mode=6720,
             original_byte_oracle_per_positive=967680,local_corruptions_positive_only=967680,full_original_transcript_pairs=True))
        for n in ('as','ld','cc1'):
            tool=Path(subprocess.check_output([str(common.CC),'-print-prog-name='+n],text=True).strip()).resolve()
            pins[str(tool)]=sha(tool)
        binaries={}
        for backend in ('soc','spike'):
            dest=out/backend; dest.mkdir(); elf=dest/'program.elf'
            common.command([common.CC,*common.FLAGS,*flags,*(['-DSPIKE_REFERENCE=1'] if backend=='spike' else []),
                 '-T',sw/'replay.ld','-Wl,-Map='+str(dest/'program.map'),'-I'+str(orig),sw/'case.c',orig/'operations.S',
                 sw/'main.c',sw/'startup.S',sw/'runtime.c','-lgcc','-o',elf],dest/'compile',timeout=120)
            for tool,args,label in [('objdump',['-d'],'disassemble'),('nm',['-S','-n'],'symbols'),('readelf',['-l','-A'],'layout')]:
                common.command([common.CC.with_name('riscv64-unknown-elf-'+tool),*args,elf],dest/label)
            binaries[backend]=dict(path=str(elf),sha256=sha(elf))
        require(all(sha(p)==h for p,h in pins.items()),'Source/tool drift')
        save(out/'inputs_after.json',pins)
        save(out/'RESULT.json',dict(status='HOST_PASS_DUAL_COMPILE_COMPLETE_CFG_PENDING',binaries=binaries,reference=False,DUT=False))
        print(json.dumps(binaries),flush=True)
    except BaseException as error:
        save(out/'FIRST_FAILURE.json',dict(type=type(error).__name__,message=str(error),retries=0))
        raise

if __name__=='__main__': main()
