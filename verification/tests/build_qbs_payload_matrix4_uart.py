"""Software-only UART successor: identical sealed matrix oracle and workload."""
import argparse
import json
from pathlib import Path
from types import FunctionType
import build_qbs_payload_matrix4 as base

ROOT = base.ROOT
APP = ROOT/'apps/qbs_payload_matrix4_uart'
BASE_SHA = '77444a234bcd294f0000fe27aa77c3424c1ccc17da9c294436457ccb6c00f48a'
APP_SHA = '5da6e013bed8f0000d916e52789d422a86eb9c3b7b9a0339e3b498933f7d8105'


def signed(value, width):
    return value-(1<<width) if value>>(width-1) else value


def printf_gate(metadata, blob):
    symbols = {r['Symbol']['Name']['Name']:r['Symbol'] for r in metadata['Symbols']}
    forbidden = ('printf','_printf_r','_vfprintf_r','vfprintf','__smakebuf_r',
                 '__swsetup_r','_fstat','_fstat_r','_write','_write_r')
    base.common.require(not any(n in symbols for n in forbidden), 'Linked newlib print/syscall path')
    base.common.require('printf_' in symbols, 'Missing UART printf_')
    main = symbols['main']
    sections = [r['Section'] for r in metadata['Sections'] if
        r['Section']['Type']['Name']!='SHT_NOBITS' and
        r['Section']['Address']<=main['Value'] and
        main['Value']+main['Size']<=r['Section']['Address']+r['Section']['Size']]
    base.common.require(len(sections)==1, 'Unique main ELF bytes')
    section = sections[0];start = section['Offset']+main['Value']-section['Address']
    code = blob[start:start+main['Size']];instructions=[];pos=0
    while pos<len(code):
        n=4 if int.from_bytes(code[pos:pos+2],'little')&3==3 else 2
        base.common.require(pos+n<=len(code), 'Complete main instruction')
        instructions.append((main['Value']+pos,int.from_bytes(code[pos:pos+n],'little'),n));pos+=n
    calls=[]
    for (pc,a,n),(_,b,m) in zip(instructions,instructions[1:]):
        if n==m==4 and a&0x7f==0x17 and (a>>7)&31==1 and b&0x707f==0x67 and (b>>15)&31==1 and (b>>7)&31==1:
            target=(pc+signed(a&0xfffff000,32)+signed(b>>20,12))&~1
            if target==symbols['printf_']['Value']:calls.append(dict(pc=hex(pc),target=hex(target)))
    base.common.require(len(calls)==2, 'Both actual main printing sites must call UART printf_')
    base.common.require(all(word!=0x73 for _,word,_ in instructions), 'Unexpected main syscall')
    return dict(status='ACTUAL_ELF_TWO_UART_PRINTF_CALLS_NO_NEWLIB_PRINT_SYSCALL',
                calls=calls,forbidden_symbols_absent=list(forbidden),host_stdio_unchanged=True)


def build(out):
    base.common.require(base.common.sha(Path(base.__file__))==BASE_SHA and
        base.common.sha(ROOT/'apps/qbs_payload_matrix4/main.c')==APP_SHA, 'Sealed predecessor changed')
    ns=dict(vars(base),APP=APP,__file__=__file__)
    FunctionType(base.build.__code__,ns)(out)
    path=out/'preflight-manifest.json';record=base.common.read(path)
    elf=out/(APP.name+'.elf');meta=json.loads((out/'dut.metadata.log').read_bytes())[0]
    gate=printf_gate(meta,elf.read_bytes())
    tool=base.common.Build(out)
    tool.run([tool.llvm/'bin/llvm-objdump','-d',elf],'uart.disassembly')
    base.common.save(out/'uart-binding-proof.json',gate)
    extra=[Path(__file__),Path(__file__).with_name('test_qbs_payload_matrix4_uart.py'),
           Path(base.__file__),ROOT/'apps/qbs_payload_matrix4/main.c',ROOT/'apps/common/printf.h']
    for p in extra:
        key=str(p.resolve());value=base.common.sha(p)
        base.common.require(key not in record['input_pins'] or record['input_pins'][key]==value,'Conflicting source pin')
        record['input_pins'][key]=value
    record['output_pins']=base.common.pins(p for p in out.iterdir() if p.is_file() and p!=path)
    record.update(software_successor='UART binding only; workload/oracle/600s unchanged',
                  uart_binding_proof_sha256=base.common.sha(out/'uart-binding-proof.json'))
    base.common.verify(record['input_pins']);base.common.verify(record['output_pins'])
    base.common.save(path,record)
    return dict(manifest=str(path),seal=base.common.sha(path),elf_sha256=base.common.sha(elf))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    print(json.dumps(build(a.output.resolve())),flush=True)
