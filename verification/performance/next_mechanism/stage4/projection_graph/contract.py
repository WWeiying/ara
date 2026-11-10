"""Frozen source/data contracts. No active candidate is read at import time."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT=Path('/home/wangwy/openproject/ara_dsa')
OUT=Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
LLAMA=Path('/home/wangwy/llama/llama.cpp')
LLAMA_COMMIT='da56aa750559c180d631b466de983ff2bb5d54d9'
SDK_COMMIT='d3d92ad72a3cabb91e8c333186160ae422f0866b'
BASE=OUT/'m4-prepared-qkv-build-20261027-02'
ACCEPTED=OUT/'m4-sums-qkv-vcs-20261029-01/result.json'
GENERIC=OUT.parent/'qbs/combined_zvfh_m4/projection/build-03/generic.cpp'
ORDER=(0,1,1,0)
WIDTHS=(1536,256,256)
FILES={'activation_f32.bin':24576,'activation_q8k_m4.bin':7008,
       'q_r4.bin':1327104,'v_r4.bin':322560,'k_r4.bin':221184,
       'q_oracle.bin':24576,'v_oracle.bin':4096,'k_oracle.bin':4096}
HASHES={
    'accepted':'7e91adb371f8e126b7d978ae240534c4ac838c3ee634b1ae700e7623007d902f',
    'build':'2c296bb6094484c540eeeeec7a534fff1cb1eb907bae5c7cc041469d216987c8',
    'manifest':'36df01d337cbeb31d77fcb64a3cdc3152a3f5d521a2ec0dbb231cc3bb75b775b',
    'generic':'68759c175dfe2306af79c112c57f362c306b0bb2ed58c4669680aec4b09a5fa9'}
SCOPE='Production-helper complete SDK Q/V/K chain; excludes GGML graph allocation/planning, model loading and offline weight repacking'
ROI_INCLUDED=('fresh SDK plan/admission','cache lookup/comparison/flag replay',
              'cold producer','dynamic cache allocation/copy/free',
              'native commands/result stores/final fence')
ROI_EXCLUDED=('one-time device_query','cache object constructor','buffer initialization',
              'caller CSR setup','input/output/oracle checks and printing',
              'GGML graph allocation/planning/threadpool','model load/offline weight repack')
ELF_READER=ROOT/'verification/performance/resident_rvv/qk_shared/qk_boundary/elf.py'
ELF_READER_SHA='3317b30d500bef0cbeff9299001310ebe464ad4d1e53383aff0288f39af6dbb3'
ENTRIES=('stage4_baseline_produce','stage4_candidate_produce','qbs_native_execute_command')


def require(ok,message):
    if not ok: raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fnv(raw):
    value=14695981039346656037
    for byte in raw: value=((value^byte)*1099511628211)&((1<<64)-1)
    return value


def verify(pins):
    for path,digest in pins.items(): require(sha(path)==digest,'Identity drift: '+str(path))


def entry_contract(elf,reader):
    require(sha(reader)==ELF_READER_SHA,'Frozen ELF reader changed')
    spec=importlib.util.spec_from_file_location('stage4_chain_elf_reader',reader)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    parsed=module.contract(Path(elf).read_bytes())
    result={}
    for name in ENTRIES:
        begin,end=module.extent(parsed,name)
        word=parsed['words'][begin]
        result[name]=dict(pc=begin,end=end,insn=word if word&3==3 else word&0xffff)
    require(len({x['pc'] for x in result.values()})==3,'Aliased producer/native entry')
    return result


def data_contract():
    require(sha(ACCEPTED)==HASHES['accepted'],'Historical parallel-sums acceptance changed')
    accepted=json.loads(ACCEPTED.read_text())
    require(accepted['state']=='PASS' and accepted['post_pins_match'] and
            accepted['measured']['traffic']==dict(commands=256,result_bytes=131072),
            'Not the accepted complete parallel/cache chain')
    require(sha(BASE/'build.json')==HASHES['build'] and sha(BASE/'manifest.json')==HASHES['manifest'],
            'Historical data-build receipt changed')
    manifest=json.loads((BASE/'manifest.json').read_text())
    # Consume immutable payloads only, never historical live SDK/RTL inventories.
    pins={str(ACCEPTED):HASHES['accepted'],str(BASE/'build.json'):HASHES['build'],
          str(BASE/'manifest.json'):HASHES['manifest']}
    for name,size in FILES.items():
        path=BASE/name
        require(path.stat().st_size==size and sha(path)==manifest[str(path)],'Captured payload changed: '+name)
        pins[str(path)]=sha(path)
    require(sha(GENERIC)==HASHES['generic'],'Accepted generic source changed')
    pins[str(GENERIC)]=HASHES['generic']
    return pins


def check_prepared_bytes(raw):
    require(len(raw)==7008,'Wrong complete M4 preparation length')
    # Natural layout oracle: each captured Q8_Kx4 has scales4, interleaved
    # quants1024 and interleaved sixteen INT16 sums per row.
    for block in range(6):
        base=block*1168
        scales=struct.unpack_from('<4f',raw,base)
        require(all(abs(x)<float('inf') for x in scales),'Nonfinite packed scale')
        for row in range(4):
            for group in range(16):
                q=[struct.unpack_from('<b',raw,base+16+4*(group*16+i)+row)[0] for i in range(16)]
                require(sum(q)==struct.unpack_from('<h',raw,base+1040+2*(group*4+row))[0],
                        'Packed subgroup sum differs from raw quant bytes')
    return dict(blocks=6,rows=4,bytes=7008,hash=fnv(raw))
