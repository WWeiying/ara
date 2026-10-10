"""One compact M8/N8 successor; independent integer gold, frozen checker reuse, no VCS."""
import argparse
import json
from pathlib import Path
import struct
import subprocess

import build_gap38_i8_f16_lane3 as common
from build_gap110_q3_r4 import MUTATIONS
import audit_gap110_q3_r4 as audit

ROOT=common.ROOT
APP=ROOT/'apps/qbs_gap113_payload_full8'
OLD=ROOT/'apps/qbs_gap110_q3_r4_tail'
PRE=ROOT/'verification/out/gap113-payload-toggle-preflight-740-agent-20261007-01/preflight-manifest.json'
PRE_SHA='a696ae21d758bdf55bd36a3c5a8cc1b5108235249668fe0ef18da9bc447a2790'


def replace_one(text, before, after):
    common.require(text.count(before)==1,'Frozen template substitution not unique: '+before)
    return text.replace(before,after)


def templates():
    body=(OLD/'main.c').read_text()
    body=replace_one(body,'c->m == 5 && c->n == (current == 0 ? 7u : 5u)',
                     'c->m == 8 && c->n == 8')
    body=replace_one(body,'{0x08b5045bu, 0x08b5045bu}','{0x0eb5045bu, 0x0eb5045bu}')
    oracle=(OLD/'native_oracle.h').read_text()
    oracle=replace_one(oracle,'bits[40]','bits[64]')
    oracle=replace_one(oracle,'m!=5 || (n!=5 && n!=7)','m!=8 || n!=8')
    assembly=(OLD/'execute.S').read_text()
    for p,n in enumerate((7,5)):
        assembly=replace_one(assembly,'MATRIX_EXEC %d, %d, 0x08b5045b'%(p,n),
                             'MATRIX_EXEC %d, 8, 0x0eb5045b'%p)
    return body,oracle,assembly


def fixture(phase):
    common.require(type(phase) is int and phase in (0,1),'Exact phase')
    w=bytearray([0xa5]*1024); a=bytearray([0x5a]*2496); off=64+12*phase
    for r in range(8):
        b=bytearray(110)
        for g in range(16):
            s=(16*r+g)&63
            if phase: s=63-s
            section,slot=divmod(g,4)
            b[96+(section%2)*4+slot]|=(s&15)<<(4*(section//2))
            b[104+slot]|=(s>>4)<<(2*section)
        for i in range(256):
            packet,lane=divmod(i,32)
            q=((i+3*r+packet)&3)+4*(((lane+32*r)>>packet)&1)
            if phase:q=7-q
            b[lane]|=(q>=4)<<packet
            b[32+32*(packet//4)+lane]|=(q&3)<<(2*(packet%4))
        struct.pack_into('<H',b,108,0x3c00)
        w[off+110*r:off+110*(r+1)]=b
    values=[]
    for c in range(8):
        struct.pack_into('<I',a,68+4*c,0x3f800000)
        v=[(((i+17*c)&255)^(((i+17*c)&255)>>2))^(255*phase) for i in range(256)]
        signed=[x if x<128 else x-256 for x in v];values.append(signed)
        for i,x in enumerate(v):a[68+32+8*i+c]=x
        for g in range(16):struct.pack_into('<h',a,68+2080+16*g+2*c,sum(signed[16*g:16*g+16]))
    gold=[]
    for c in range(8):
        for r in range(8):
            dot=0
            for i in range(256):
                scale=(16*r+i//16)&63;packet,lane=divmod(i,32)
                quant=((i+3*r+packet)&3)+4*(((lane+32*r)>>packet)&1)
                if phase:scale,quant=63-scale,7-quant
                dot+=(scale-32)*(quant-4)*values[c][i]
            common.require(abs(dot)<2**23,'Bounded exact FP32 integer')
            gold.append(struct.unpack('<I',struct.pack('<f',dot))[0])
    return bytes(w),bytes(a),gold


def build(out):
    common.require(not out.exists() and out.parent==ROOT/'verification/out','Fresh output')
    common.require(common.sha(PRE)==PRE_SHA,'Frozen reference preflight drift')
    prior=json.loads(PRE.read_bytes());protected=prior['input_pins'];common.verify(protected)
    out.mkdir();b=common.Build(out)
    b.bind_sources([Path(__file__),Path(__file__).with_name('test_gap113_payload_full8.py'),
                    APP/'main.c',OLD/'main.c',OLD/'native_oracle.h',OLD/'execute.S',OLD/'contract.h',
                    Path(audit.__file__),Path(common.__file__)])
    for name,text in zip(('checked_body.inc','native_oracle.h','execute.S'),templates()):
        (out/name).write_text(text)
    lines=[];expected=b''
    for p in (0,1):
        w,a,gold=fixture(p);expected+=w+a
        lines.append('static const uint32_t full8_gold%d[64]={%s};'%(p,','.join(hex(v) for v in gold)))
        common.save(out/('gold%d.json'%p),dict(bits=gold,flags=0))
    (out/'full8_gold.h').write_text('\n'.join(lines)+'\n')
    inc=['-I'+str(out),'-I'+str(OLD)]
    host_obj=b.compile(APP/'main.c','host-main',[*inc,'-DGAP110_HOST=1'],host=True)
    host=out/'host';b.link([b.host,host_obj,'-o',host],'host.link')
    common.require(b.run([host,'--dump'],'templates').stdout==expected,'C/Python packed source differs')
    log=b.run([host],'host-checks').stdout.decode()
    common.require('PASSED: qbs_gap113_payload_full8 inherited_checks=44 errors=0' in log and
                   'vrf_words=2048 initial_words=2048 source_bytes=7328 csr_words=24' in log and
                   'FAIL' not in log,'Full host oracle/checks failed')
    for p in (0,1):
        for mutation in MUTATIONS:
            r=subprocess.run([host,mutation,str(p)],capture_output=True,timeout=10)
            common.require(r.returncode==1 and b'FAILED: qbs_gap113_payload_full8' in r.stdout,
                           'Corruption escaped: '+mutation)
            (out/('negative-%d-%s.log'%(p,mutation))).write_bytes(r.stdout+r.stderr)
    objects=[b.compile(b.common/n,'dut-'+n) for n in
             ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    objects += [b.compile(APP/'main.c','dut-main',inc),b.compile(out/'execute.S','dut-execute')]
    elf=out/(APP.name+'.elf');b.bind_sources([b.common/'link.ld'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections',
            '-T'+str(b.common/'link.ld'),*objects,'-lm','-L'+str(b.llvm/'lib/generic'),
            '-lclang_rt.builtins-riscv64','-o',elf],'dut.link')
    meta=json.loads(b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols',elf],
                         'dut.metadata').stdout)[0]
    symbols={r['Symbol']['Name']['Name']:r['Symbol'] for r in meta['Symbols']};blob=elf.read_bytes();sites=[]
    for p in (0,1):
        f=symbols['gap110_exec%d'%p];pc=symbols['gap110_qbexec_site%d'%p]['Value']
        sec=[r['Section'] for r in meta['Sections'] if r['Section']['Type']['Name']!='SHT_NOBITS' and
             r['Section']['Address']<=f['Value'] and f['Value']+f['Size']<=r['Section']['Address']+r['Section']['Size']]
        common.require(len(sec)==1,'Ambiguous execution section')
        start=sec[0]['Offset']+f['Value']-sec[0]['Address'];code=blob[start:start+f['Size']]
        words=[];pcs=[];i=0
        while i<len(code):
            length=4 if int.from_bytes(code[i:i+2],'little')&3==3 else 2
            common.require(i+length<=len(code),'Truncated instruction')
            words.append(int.from_bytes(code[i:i+length],'little'));pcs.append(f['Value']+i);i+=length
        common.require(words[pcs.index(pc)]==0x0eb5045b and any(
            words[j] in (0x42a1,0x00800293) and words[j+1]==0x0102f057 for j in range(len(words)-1)),
            'Actual M8 word/VL8 setup differs')
        normalized=list(words);normalized[pcs.index(pc)]=0x08b5045b
        audit.audit_execution(normalized,pcs,pc)
        sites.append(dict(pc=pc,word=0x0eb5045b))
    fit=ROOT/'verification/coverage/check_elf_fit.py';b.bind_sources([fit])
    b.run([ROOT/'verification/tools/soc-venv/bin/python',fit,'--elf',elf,'--ram-bytes','0x200000',
           '--output',out/'elf-fit.json'],'elf-fit')
    ledger=ROOT/'verification/out/raw741-post-export-audit-20261007-01.json'
    book=json.loads(ledger.read_bytes())
    common.require(book['status']=='RAW741_POST_EXPORT_IDENTITY_WAIVER_AUDIT_PASS' and
                   book['selected_count']==741 and
                   book['admission_seal']=='ad53b488eb12de7c8fe1a470d72c5a36dbea5cb349383dcf9c3c8068cebfb0f1',
                   'Not exact formal741 dedup ledger')
    common.require(common.sha(elf) not in book['source_pins'].values(),'Duplicate formal741 ELF')
    inputs={**protected,**b.sources,**b.tools,**b.link_inputs,str(PRE):PRE_SHA,str(ledger):common.sha(ledger)}
    common.verify(inputs)
    record=dict(status='FULL8_HOST_NATIVE_ELF_PREFLIGHT_NOT_DUT_PASS',binary=str(elf),binary_sha256=common.sha(elf),
        input_pins=inputs,output_pins=common.pins(p for p in out.iterdir() if p.is_file()),
        m=8,n=8,k_blocks=1,commands=2,sites=sites,host_checks=44,host_negative_tests=42,dut_checks=41,
        full_vrf_words=2048,initial_words=2048,source_guard_bytes=7328,csr_words=24,budget_s=600,
        weight_scale_encodings=64,weight_quant_encodings=8,weight_high_mask_byte_encodings=256,
        activation_distinct_bytes_per_context=256,
        activation_groups_per_command=128,spike='NOT_EXECUTED_CUSTOM_QBS_UNSUPPORTED',
        full_scalar_isa_verified=False,rtl_modified=False,vcs_launched=False,coverage_admitted=False)
    common.save(out/'preflight-manifest.json',record)
    return dict(manifest=str(out/'preflight-manifest.json'),seal=common.sha(out/'preflight-manifest.json'),
                elf_sha256=common.sha(elf))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(p.parse_args().output.absolute())))
