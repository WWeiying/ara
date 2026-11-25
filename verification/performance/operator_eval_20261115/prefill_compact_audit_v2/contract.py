"""Compact Prefill successor contract. Ancestors are read-only inputs."""
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = ROOT.parent/'ara_dsa_signoff_integration/verification/out'
ANCESTOR = OUT/'operator_extensions_prepare_20261115_f16_q64_04'
CALIBRATION = OUT/'operator_campaign_20261115_calibration_01/runs/qwen3_d128_gqa2_t137'
CAPTURE = OUT/'e2e_qwen3_f16_attention_capture_20261106_01'
ELF_READER = ROOT/'verification/performance/resident_rvv/qk_shared/qk_boundary/elf.py'
ORDER = (0, 1, 1, 0)
REV = 'dbe2b78817ef45b912444afcb85ad6e01a2be135'
CONST_FIELDS = ('magic version first queries dimension heads kvheads capacity outputs printed '
                'scale_bits atol_bits rtol_bits input_bytes input_hash query_bytes key_bytes '
                'value_bytes mask_bytes golden_bytes guards order kvhead production_query_threshold').split()


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for data in iter(lambda:stream.read(1048576), b''):
            h.update(data)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    with Path(path).open('x') as stream:
        json.dump(value, stream, indent=2, sort_keys=True)
        stream.write('\n')


def verify(pins):
    require(bool(pins), 'Empty pins')
    for path, digest in pins.items():
        require(sha(path) == digest, 'Input drift: '+path)


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def hash64(raw):
    require(len(raw) % 8 == 0, 'Word hash extent')
    h = 14695981039346656037
    for (word,) in struct.iter_unpack('<Q', raw):
        h = ((h ^ word)*1099511628211) & ((1 << 64)-1)
    return h


def real_fixture(queries, pin=lambda p:None):
    require(queries in (16,64), 'Only real Q16/Q64 successors')
    report = read(CAPTURE/'result.json')
    require(report['state'] == 'REAL_QWEN3_F16_BOUNDARIES_CAPTURED_NOT_RTL_ACCEPTED', 'Capture producer')
    pin(CAPTURE/'result.json')
    block = CAPTURE/'capture/prefill/block'
    specs = {'query':('attn_q_input-0','f32',[128,136,16,1],[4,512,69632,1114112],1114112),
             'key':('attn_k_input-0','f16',[128,256,8,1],[2,256,65536,524288],524288),
             'value':('attn_v_input-0','f16',[128,256,8,1],[2,256,65536,524288],524288),
             'mask':('attn_mask_input-0','f16',[256,136,1,1],[2,512,69632,69632],69632),
             'golden':('kqv_out-0','f32',[2048,136,1,1],[4,8192,1114112,1114112],1114112)}
    full = {}
    for role,(name,kind,shape,strides,size) in specs.items():
        for suffix in ('.json','.bin'):
            p = block/(name+suffix)
            require(report['artifacts'].get(str(p)) == sha(p), 'Capture tensor identity: '+str(p))
            pin(p)
        m = read(block/(name+'.json'))
        require((m['type'],m['shape'],m['strides'],m['nbytes']) == (kind,shape,strides,size), 'Capture geometry')
        full[role] = (block/(name+'.bin')).read_bytes()
        require(len(full[role]) == size, 'Capture extent')
    p = block/'attention_params-0.json'
    require(report['artifacts'].get(str(p)) == sha(p), 'Capture parameter identity')
    pin(p)
    params = read(p)
    require(params['scale'] == .0883883 and params['max_bias'] == params['logit_softcap'] == 0, 'Score parameters')
    for t in range(136):
        row = struct.unpack_from('<256H',full['mask'],t*512)
        require(all(v == (0 if i <= t else 0xfc00) for i,v in enumerate(row)), 'Original complete causal mask')
    first = 72
    data = dict(query=b''.join(full['query'][(h*136+first)*512:(h*136+first+queries)*512] for h in range(2)),
        key=full['key'][:65536],value=full['value'][:65536],
        mask=full['mask'][first*512:(first+queries)*512],
        golden=b''.join(full['golden'][t*8192:t*8192+1024] for t in range(first,first+queries)))
    require(all(math.isfinite(x) for role,fmt in (('query','<f'),('key','<e'),('value','<e'),('golden','<f'))
                for (x,) in struct.iter_unpack(fmt,data[role])), 'Nonfinite capture')
    payload = b''.join(data.values())
    c = dict(zip(CONST_FIELDS,(0x50464331,1,72,queries,128,2,1,256,queries*256,64,
        0x3db504f3,0x3b83126f,0x3b03126f,len(payload),hash64(payload),
        len(data['query']),65536,65536,len(data['mask']),len(data['golden']),128,0x00010100,0,64)))
    return data,c


def constant_bytes(constants):
    require(set(constants) == set(CONST_FIELDS), 'ELF contract schema')
    return struct.pack('<'+'Q'*len(CONST_FIELDS),*[constants[k] for k in CONST_FIELDS])


def work(constants):
    prefixes = range(73,73+constants['queries'])
    seq = []
    for start in range(0,max(prefixes),64):
        resident = min(64,max(prefixes)-start)
        seq.append(dict(command=4 if start == 0 else 5,q_external_bytes=512 if start == 0 else 0,
                        kv_external_bytes=resident*512,replay_bytes=0))
        for prefix in prefixes:
            active = min(64,max(0,prefix-start))
            if active:
                seq += [dict(command=6,q_external_bytes=0,kv_external_bytes=0,replay_bytes=resident*8)]*32
                seq += [dict(command=2,q_external_bytes=0,kv_external_bytes=0,replay_bytes=256)]*active
    return seq+[dict(command=3,q_external_bytes=0,kv_external_bytes=0,replay_bytes=0)]


def elf_blob(raw, parsed, symbol, count):
    address = parsed['symbols'][symbol]['address']
    offset = struct.unpack_from('<Q',raw,32)[0]
    size, number = struct.unpack_from('<HH',raw,54)
    require(size == 56 and offset+size*number <= len(raw), 'ELF program table')
    for i in range(number):
        p = struct.unpack_from('<IIQQQQQQ',raw,offset+i*size)
        if p[0] == 1 and p[3] <= address and address+count <= p[3]+p[5]:
            return raw[p[2]+address-p[3]:p[2]+address-p[3]+count]
    raise ValueError('ELF constant outside initialized load segment: '+symbol)
