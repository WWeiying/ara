"""Read-only quantKV ancestors and compact verification utilities."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
ORDER = (0,1,1,0)
ELF_READER = ROOT/'verification/performance/resident_rvv/qk_shared/qk_boundary/elf.py'


def require(ok, message):
    if not ok: raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''): h.update(b)
    return h.hexdigest()


def read(path): return json.loads(Path(path).read_text())


def save(path,value):
    with Path(path).open('x') as f:
        json.dump(value,f,indent=2,sort_keys=True); f.write('\n')


def verify(pins):
    require(bool(pins),'Empty pins')
    for p,h in pins.items(): require(sha(p)==h,'Input drift: '+p)


def module(path,name):
    s=importlib.util.spec_from_file_location(name,path)
    m=importlib.util.module_from_spec(s); s.loader.exec_module(m); return m


def ancestor(kind):
    return OUT/('operator_extensions_prepare_20261115_'+('q4' if kind=='q4_0' else 'q8')+'_03')


def elf_blob(raw,parsed,name,count):
    address=parsed['symbols'][name]['address']
    offset=struct.unpack_from('<Q',raw,32)[0]; size,n=struct.unpack_from('<HH',raw,54)
    require(size==56 and offset+n*size<=len(raw),'ELF program table')
    for i in range(n):
        p=struct.unpack_from('<IIQQQQQQ',raw,offset+i*size)
        if p[0]==1 and p[3]<=address and address+count<=p[3]+p[5]:
            return raw[p[2]+address-p[3]:p[2]+address-p[3]+count]
    raise ValueError('Uninitialized ELF constant: '+name)


def captured(kind,pin=lambda p:None):
    audit=OUT/'quant-prefill-capture-audit-20261028-01'
    require(read(audit/'result.json')['state']=='PASS','Real capture audit')
    recorded=read(audit/'manifest.json')
    for p in (audit/'manifest.json',audit/'result.json'): pin(p)
    block=OUT/'quant-prefill-capture-20261028-01'/kind/'prefill/block'
    data={}
    for role,name in zip(('query','key','value','mask','golden'),
                         ('attn_q_input-0','attn_k_input-0','attn_v_input-0','attn_mask_input-0','kqv_out-0')):
        for suffix in ('.bin','.json'):
            p=block/(name+suffix); require(recorded.get(str(p))==sha(p),'Captured identity: '+str(p)); pin(p)
        m=read(block/(name+'.json')); raw=(block/(name+'.bin')).read_bytes()
        require(len(raw)==m['nbytes'],'Capture extent'); data[role]=raw
    expected=(163840,147456 if kind=='q4_0' else 278528,278528,10240,163840)
    require(tuple(map(len,data.values()))==expected,'Complete original fixture dimensions')
    mask=data['mask']
    for t in range(20):
        require(struct.unpack_from('<256H',mask,t*512)==tuple([0]*(t+1)+[0xfc00]*(255-t)),'Complete original causal mask')
    return data
