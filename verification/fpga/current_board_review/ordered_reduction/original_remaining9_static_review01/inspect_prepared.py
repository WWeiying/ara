"""Offline source/ELF inspection only: never import batch helpers or run tests."""
import hashlib
import json
from pathlib import Path
import re
import struct

OUT = Path(__file__).resolve().parent
ROOT = OUT.parent / 'original_remaining9_prepare01'
SHAPES = ['e16_mf2','e16_m1','e16_m2','e16_m4','e16_m8','e32_mf2','e32_m2','e32_m4','e32_m8']


def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda:f.read(1048576),b''):
            h.update(block)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def elf(path):
    data=Path(path).read_bytes()
    assert data[:6]==b'\x7fELF\x02\x01'
    off=struct.unpack_from('<Q',data,32)[0]
    size,n=struct.unpack_from('<HH',data,54)
    segments=[]
    for i in range(n):
        typ,flags,offset,va,pa,filesz,memsz,align=struct.unpack_from('<IIQQQQQQ',data,off+i*size)
        if typ==1:
            segments.append((va,va+filesz,offset))
    def get(addr,size):
        for lo,hi,offset in segments:
            if lo<=addr and addr+size<=hi:
                return data[offset+addr-lo:offset+addr-lo+size]
        raise ValueError(hex(addr))
    return get


def main():
    manifest=read(ROOT/'manifest.json')
    assert [x['shape'] for x in manifest['shapes']]==SHAPES
    assert manifest['profile']=='rv64gcv_zfh_zvfh_zvl1024b'
    assert manifest['limits_per_elf']=={'steps':3000000,'raw_bytes':268435456,'seconds':120}
    rows=[]
    pins={str(ROOT/'manifest.json'):sha(ROOT/'manifest.json')}
    selector='                if(!(scenario==3 && l==4 && mode==3 && rm==0 && op==0 && sticky==0))continue;\n'
    for shape in SHAPES:
        d=ROOT/shape
        proof=read(d/'sourceproof.json'); c=proof['config']; w=c['word_bytes']
        cost=read(d/'static_cost.json')
        assert c['shape']==shape and c['cap']*w<=1024 and c['vl']==c['cap']//2
        for p,h in {**proof['external_pins'],**proof['prepared_pins']}.items():
            if p in pins:
                assert pins[p]==h
            else:
                assert sha(p)==h,p
                pins[p]=h
        for p in (d/'sourceproof.json',d/'static_cost.json',d/'host.json'):
            pins[str(p)]=sha(p)
        original=Path('/home/wangwy/openproject/ara_dsa/hardware/fpga/ara_dsa_vcu118/linux/diagnostics/rvv_matrix/fp_reduction_oracle.c').read_text()
        scenario=(d/'prepared/scenario.c').read_text()
        assert scenario.count(selector)==1 and scenario.replace(selector,'',1)==original
        body=scenario[scenario.index('    unsigned long vlenb;'):].split('__asm__(".global _start')[0]
        body=body.replace('syscall3(94,2,0,0);for(;;){}','return 2;').replace('syscall3(94,errors ? 1:0,0,0);for(;;){}','return errors ? 1 : 0;')
        adapted=(d/'prepared/case.c').read_text()
        assert adapted[adapted.index('    unsigned long vlenb;'):].strip()==body.strip()
        fixtures=[[int(a,16),int(b)] for a,b in re.findall(r'\{UINT64_C\(0x([0-9a-fA-F]+)\),\s*(\d+)\}',(d/'prepared/fixtures.h').read_text())]
        jf=Path('/home/wangwy/fpga_runs/ara_hw_campaign_20261007_01/rvv_small_redspecial02')/('rvv_small_fp_redspecial_'+shape)/'fixtures.json'
        assert [r for bank in read(jf) for r in bank]==fixtures
        pins[str(jf)]=sha(jf)
        assert len(fixtures)==6720 and fixtures[4905]==[c['nan'],16]
        old=elf(d/'prepared/scenario.elf')
        for kind in ('spike','soc'):
            get=elf(d/kind/'program.elf')
            for name,window in proof['helper_windows'][kind].items():
                assert len(window['original'])==len(window['new'])==21
                for a,b in zip(window['original'],window['new']):
                    assert a[1]==b[1]
                    n=len(a[1])//2
                    assert old(a[0],n)==get(b[0],n)==bytes.fromhex(a[1])[::-1]
            for p in (d/kind/'program.elf',d/kind/'program.dis',d/kind/'symbols.json'):
                pins[str(p)]=sha(p)
            ins=[(int(a,16),b,t) for a,b,t in re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)',(d/kind/'program.dis').read_text(),re.M)]
            for pc,code,text in ins:
                assert get(pc,len(code)//2)==bytes.fromhex(code)[::-1]
        sy=read(d/'spike/symbols.json')
        ins=[(int(a,16),b,t) for a,b,t in re.findall(r'^\s*([0-9a-f]+):\s+([0-9a-f]{4,8})\s+([^\n]+)',(d/'spike/program.dis').read_text(),re.M)]
        main=[r for r in ins if sy[c['identity']+'_main']<=r[0]<sy['capacity']]
        callsites=[r for r in main if '<memcpy>' in r[2]]
        assert len(callsites)==1
        for field in ('mask_instructions','seed_instructions','memcpy_instructions'):
            assert all(tuple(r) in ins for r in cost[field])
        assert sum(cost['terms'].values())==cost['upper_instructions']<3000000
        assert cost['elf_sha256']==sha(d/'spike/program.elf')
        assert cost['disassembly_sha256']==sha(d/'spike/program.dis')
        assert cost['sourceproof_sha256']==sha(d/'sourceproof.json')
        host=read(d/'host.json')
        assert host['status']=='PASS_13_HOST_ONLY' and len(host['tests'])==13
        for item in host['tests']:
            positive=item['mode']=='positive'
            assert item['passed'] and item['returncode']==(0 if positive else 1)
            p=d/'host'/(item['mode']+'.log');log=p.read_text();pins[str(p)]=sha(p)
            assert 'HOST_SETUP_FULL_PASS' in log
            assert ('RVV_FP_REDSPECIAL_PASS' in log)==positive
            assert ('RVV_FP_REDSPECIAL_FAIL' in log)!=positive
        rows.append(dict(shape=shape,cap=c['cap'],vl=c['vl'],sew=c['sew'],input_bytes=c['cap']*w,seed_bytes=64*w,mask_load_bytes=(c['cap']+7)//8,bank0=fixtures[1545],bank1=fixtures[4905],static_upper=cost['upper_instructions'],spike_elf_sha256=sha(d/'spike/program.elf'),soc_elf_sha256=sha(d/'soc/program.elf'),source_and_full_body_equal=True,helper_windows_actual_bytes_equal=True,host13_evidence_consistent=True,memcpy_callsites_in_main=callsites))
    result=dict(status='STATIC_SOURCE_ELF_EVIDENCE_INSPECTED_NOT_REFERENCE_ACCEPTANCE',cases=rows,pins=pins,script_sha256=sha(__file__),tests_or_reference_executed=False)
    with (OUT/'prepared_inspection01.json').open('x') as f:
        json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps(dict(cases=rows,pins=len(pins)),indent=2))


if __name__=='__main__':
    main()
