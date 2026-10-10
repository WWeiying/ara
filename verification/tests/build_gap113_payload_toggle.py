"""Compact GAP110 checker reuse with independent data gold; never launches VCS."""
import argparse
import json
from pathlib import Path
import struct
import xml.etree.ElementTree as ET
import build_gap38_i8_f16_lane3 as common
import audit_gap110_q3_r4 as audit
import gap110_q3_r4_contract as native

ROOT=common.ROOT
APP=ROOT/'apps/qbs_gap113_payload_toggle'
OLD=ROOT/'apps/qbs_gap110_q3_r4_tail'
EVIDENCE=ROOT/'verification/out/targeted-toggle740-gap113-20261007-01.json'
PRE=ROOT/'verification/out/gap110-q3-r4-preflight-732-20261006-01/preflight-manifest.json'
PRE_SHA='dcaaf03b88d1cbf516e2bbe1466e1790ff52098646d585ae81af17bba2bb37eb'
SCOPE=native.SCOPE


def fixtures(phase):
    common.require(type(phase) is int and phase in (0,1),'Exact two phases')
    w=bytearray([0xa5]*1024);a=bytearray([0x5a]*2496);offset=64+12*phase
    for r in range(8):
        block=bytes([0 if r&2 else 255]*96+[0 if r&1 else 255]*12)+struct.pack('<H',0x3c00)
        w[offset+110*r:offset+110*(r+1)]=block
    for c in range(8):
        struct.pack_into('<I',a,68+4*c,0x3f800000)
        values=[(((i+17*c)&255)^(((i+17*c)&255)>>2))^(255*phase) for i in range(256)]
        signed=[v if v<128 else v-256 for v in values]
        common.require(len(set(values))==256 and sum(signed)==-128,'Permutation closed-form sum')
        for i,v in enumerate(values):a[68+32+8*i+c]=v
        for g in range(16):struct.pack_into('<h',a,68+2080+16*g+2*c,sum(signed[16*g:16*g+16]))
    n=5 if phase else 7
    dots=[-128*(-32 if r&1 else 31)*(-4 if r&2 else 3) for r in range(n)]*5
    gold=[struct.unpack('<I',struct.pack('<f',d))[0] for d in dots]
    common.require(native.unpack_oracle(w[offset:offset+880],a[68:68+2336],n)['bits']==gold,
                   'Independent unpack disagrees with closed-form gold')
    return bytes(w),bytes(a),gold


def target(evidence):
    common.require(evidence['schema']=='TARGETED_RAW740_TOGGLE_DIAGNOSTIC_V2' and
        len(evidence['tests'])==len(set(evidence['tests']))==740,'Exact raw740 Toggle evidence')
    row=evidence['metrics'][SCOPE];shape=ET.fromstring(evidence['compiled_definitions'][SCOPE]['shape'])
    offset=0;found=None
    for node in shape.find('tglshape'):
        common.require(node.tag in ('node','vectornode'),'Array before target')
        width=1 if node.tag=='node' else abs(int(node.get('left'))-int(node.get('right')))+1
        if node.get('name')=='activation_data_i':found=(offset,width,dict(node.attrib));break
        offset+=2*width
    common.require(found and found[:2]==(1948,256) and str(row['checksum'])=='3657545390' and
        row['width']==66340,'Exact payload Toggle target shape')
    bits=format(int(row['bits'],16),'0%db'%row['width'])
    zeros=[i for i in range(offset,offset+512) if bits[i]=='0']
    common.require(len(zeros)==83,'Raw740 target differs')
    return dict(scope=SCOPE,checksum=row['checksum'],signal='activation_data_i',source=found[2],
        serialized_zero_coordinates=zeros,direction_binding_verified=False,
        hypothesis='Q8 byte permutation/complement and canonical signed bsums switch legal bank1 activation data',
        expected_gain='unmeasured; serialize actual candidate Toggle then OR with this exact raw740 population')


def build(out):
    common.require(not out.exists() and out.parent==ROOT/'verification/out','Fresh output required')
    common.require(common.sha(PRE)==PRE_SHA,'Frozen GAP110 reference drift')
    evidence=json.loads(EVIDENCE.read_bytes());prediction=target(evidence)
    prior=json.loads(PRE.read_bytes())
    protected={p:h for p,h in prior['input_pins'].items() if '/hardware/' in p}
    protected.update(evidence['input_pins']);protected[str(EVIDENCE)]=common.sha(EVIDENCE)
    protected[str(PRE)]=PRE_SHA;common.verify(protected)
    out.mkdir();b=common.Build(out)
    b.sources=common.pins([Path(__file__).resolve(),Path(audit.__file__).resolve(),
        Path(native.__file__).resolve(),Path(common.__file__).resolve(),
        Path(__file__).with_name('test_gap113_payload_toggle.py'),APP/'main.c'])
    host_obj=b.compile(APP/'main.c','host',['-DGAP110_HOST=1'],host=True)
    host=out/'host';b.link([b.host,host_obj,'-o',host],'host.link')
    data=b.run([host,'--dump'],'templates').stdout
    expected=b''
    for phase in (0,1):
        w,a,gold=fixtures(phase);expected+=w+a+struct.pack('<%dI'%len(gold),*gold)
        common.save(out/('gold%d.json'%phase),dict(bits=gold,flags=0))
    common.require(data==expected,'Actual C input/gold differs from Python recipe')
    actual=b.run([host],'host-checks').stdout.decode()
    common.require('PASSED: qbs_gap113_payload_toggle inherited_checks=44 errors=0' in actual and
        'vrf_words=2048 initial_words=2048 source_bytes=7328 csr_words=24' in actual and 'FAIL' not in actual,
        'Complete reused native/VRF/CSR/guard host checks')
    from build_gap110_q3_r4 import MUTATIONS
    for phase in (0,1):
        for mutation in MUTATIONS:
            import subprocess
            r=subprocess.run([host,mutation,str(phase)],capture_output=True,timeout=10)
            common.require(r.returncode==1 and b'FAILED: qbs_gap113_payload_toggle' in r.stdout,
                           'Negative escaped: '+mutation)
            (out/('negative-%d-%s.log'%(phase,mutation))).write_bytes(r.stdout+r.stderr)
    objects=[b.compile(b.common/n,'dut-'+n) for n in
             ('crt0.S','printf.c','string.c','serial.c','util.c','print_trap_cause.c')]
    objects+=[b.compile(APP/'main.c','dut-main'),b.compile(OLD/'execute.S','dut-execute')]
    elf=out/(APP.name+'.elf');b.bind_sources([b.common/'link.ld'])
    b.link([b.cc,*b.flags,'-fuse-ld=lld','-static','-nostartfiles','-Wl,--gc-sections',
        '-T'+str(b.common/'link.ld'),*objects,'-lm','-L'+str(b.llvm/'lib/generic'),
        '-lclang_rt.builtins-riscv64','-o',elf],'dut.link')
    meta=json.loads(b.run([b.llvm/'bin/llvm-readobj','--elf-output-style=JSON','--sections','--symbols',elf],
                         'dut.metadata').stdout)[0]
    symbols={r['Symbol']['Name']['Name']:r['Symbol'] for r in meta['Symbols']};blob=elf.read_bytes();sites=[]
    for phase in (0,1):
        function=symbols['gap110_exec%d'%phase];pc=symbols['gap110_qbexec_site%d'%phase]['Value']
        sections=[r['Section'] for r in meta['Sections'] if r['Section']['Type']['Name']!='SHT_NOBITS' and
                  r['Section']['Address']<=function['Value'] and
                  function['Value']+function['Size']<=r['Section']['Address']+r['Section']['Size']]
        common.require(len(sections)==1,'Ambiguous execution bytes');sec=sections[0]
        start=sec['Offset']+function['Value']-sec['Address'];code=blob[start:start+function['Size']]
        words=[];pcs=[];i=0
        while i<len(code):
            length=4 if int.from_bytes(code[i:i+2],'little')&3==3 else 2
            common.require(i+length<=len(code),'Truncated execution');pcs.append(function['Value']+i)
            words.append(int.from_bytes(code[i:i+length],'little'));i+=length
        audit.audit_execution(words,pcs,pc);sites.append(dict(pc=pc,word=0x08b5045b))
    elf_hash=common.sha(elf)
    ledger_path=ROOT/'verification/out/queue-mask-offline-admitted-740-agent-20261007-01/evidence-pins.json'
    ledger=json.loads(ledger_path.read_bytes());protected[str(ledger_path)]=common.sha(ledger_path)
    common.require(elf_hash not in ledger.values(),'ELF already in formal740 evidence')
    fit=ROOT/'verification/coverage/check_elf_fit.py';b.bind_sources([fit])
    b.run([ROOT/'verification/tools/soc-venv/bin/python',fit,'--elf',elf,'--ram-bytes','0x200000',
           '--output',out/'elf-fit.json'],'elf-fit')
    inputs={**protected,**b.sources,**b.tools,**b.link_inputs};common.verify(inputs)
    common.save(out/'target-before.json',prediction)
    common.save(out/'artifact-hashes.json',common.pins(p for p in out.iterdir() if p.is_file()))
    record=dict(status='GAP113_HOST_NATIVE_ELF_PREPARED_NOT_DUT_PASS',binary=str(elf),binary_sha256=elf_hash,
        input_pins=inputs,output_pins=common.pins([out/'artifact-hashes.json']),target=prediction,
        host_checks=44,host_negative_tests=42,dut_checks=41,commands=2,sites=sites,budget_s=600,
        vrf_words=2048,source_bytes=7328,csr_words=24,source_recipe='256-value permutation then byte complement',
        spike='NOT_EXECUTED_CUSTOM_QBS_UNSUPPORTED',full_scalar_isa_verified=False,
        measured_gain=None,rtl_modified=False,vcs_launched=False,coverage_admitted=False,
        inherited_log_labels='GAP110 body labels preserved; GAP113 terminal label added')
    common.save(out/'preflight-manifest.json',record)
    return dict(manifest=str(out/'preflight-manifest.json'),seal=common.sha(out/'preflight-manifest.json'),elf_sha256=elf_hash)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    print(json.dumps(build(p.parse_args().output.absolute())))
