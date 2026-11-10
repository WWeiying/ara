"""Three SDK calls; independent ordered tile64 arithmetic, never a cycle model."""
import ctypes as C
from fractions import Fraction
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

ROOT = Path('/home/wangwy/openproject/ara_dsa')
OUT = Path('/home/wangwy/openproject/ara_dsa_signoff_integration/verification/out')
DATA = OUT/'e2e_qwen3_f16_native_data_20261106_02'
CASES = (
    dict(name='off_original', requested=0, dimension=128, heads=2, kv_heads=1,
         tokens=137, capacity=256, initial_flags=0),
    dict(name='on_original', requested=1, dimension=128, heads=2, kv_heads=1,
         tokens=137, capacity=256, initial_flags=8),
    dict(name='on_derived', requested=1, dimension=96, heads=6, kv_heads=2,
         tokens=65, capacity=65, initial_flags=0),
)
NATIVE_SHA = '0be0c9b07fdbd8773ec85ef2b738bbcc65f657f322d65e77610609c968ee9316'
LIBM = Path('/usr/lib64/libm.so.6').resolve()


def load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def require(ok, message):
    if not ok:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def fnv(raw):
    value = 14695981039346656037
    for byte in raw:
        value = ((value ^ byte)*1099511628211) & ((1 << 64)-1)
    return value


def raw32(value):
    return struct.unpack('<I', struct.pack('<f', value))[0]


def float32(bits):
    return struct.unpack('<f', struct.pack('<I', bits))[0]


def unpack(raw, width):
    return list(struct.unpack('<' + {16:'H', 32:'I'}[width]*(len(raw)//(width//8)), raw))


def pack(values, width):
    return struct.pack('<' + {16:'H', 32:'I'}[width]*len(values), *values)


def inputs():
    old = load(ROOT/'verification/performance/akv_pair_eval/build.py', 'sdk_capture_contract')
    pins = old.validate_data()
    q = (DATA/'decode_query.bin').read_bytes()
    k = (DATA/'decode_key.bin').read_bytes()
    v = (DATA/'decode_value.bin').read_bytes()
    mask = (DATA/'decode_mask.bin').read_bytes()
    # Rotate dimensions within captured rows, not their numerical representation.
    bits = unpack(q, 32)
    derived_q = pack([bits[(h % 2)*128 + (d+7*h) % 128]
                      for h in range(6) for d in range(128)], 32)
    derived = dict(query=derived_q,
        key=k[:65*256] + k[64*256:129*256],
        value=v[:65*256] + v[64*256:129*256], mask=mask[:130])
    original = dict(query=q, key=k, value=v, mask=mask)
    return (original, original, derived), pins


class Arithmetic:
    def __init__(self):
        path = ROOT/'verification/fpnew_upstream_20261009/oracle.py'
        self.oracle = load(path, 'sdk_independent_softfloat')
        self.sf = self.oracle.SoftFloat()
        self.flags = 0
        self.phase, self.phase_flags = None, {}
        self.libm = C.CDLL(str(LIBM))
        self.libm.expf.argtypes, self.libm.expf.restype = [C.c_float], C.c_float
        for name in ('fegetround', 'fesetround', 'feclearexcept', 'fetestexcept'):
            fn = getattr(self.libm, name)
            fn.argtypes = [] if name == 'fegetround' else [C.c_int]
            fn.restype = C.c_int
        self.pins = {str(p):sha(p) for p in (path, self.oracle.LIB, LIBM)}
        self.exp_samples, self.reduction_checks = [], 0

    def op(self, op, width, a, b=0, c=0, dst=None):
        value, flags = self.sf.evaluate(op, width, dst or width, 0, a, b, c)
        self.flags |= flags
        if self.phase is not None:
            self.phase_flags[self.phase] = self.phase_flags.get(self.phase,0) | flags
        return value

    def cast(self, source, target, value):
        return self.op('cast', source, value, dst=target)

    def add(self, width, a, b):
        one = {32:0x3f800000, 64:0x3ff0000000000000}[width]
        return self.op('fma', width, one, a, b)

    def sub(self, a, b):
        return self.add(32, a, b ^ 0x80000000)

    def expf(self, bits):
        # Same scalar C libm contract as the accepted tile64 reference. Preserve
        # the host caller's environment; SoftFloat supplies all other rounding.
        env = C.create_string_buffer(256)
        self.libm.fegetenv.argtypes = [C.c_void_p]
        self.libm.fesetenv.argtypes = [C.c_void_p]
        require(self.libm.fegetenv(env) == 0, 'Cannot save host fenv')
        try:
            require(self.libm.fesetround(0) == 0 and
                    self.libm.feclearexcept(0x3d) == 0, 'Cannot set host RNE')
            result = raw32(self.libm.expf(float32(bits)))
            flags = self.libm.fetestexcept(0x3d)
            require(flags >= 0 and flags & ~0x3d == 0, 'Unknown host FP exception')
            mapped = sum(target for source,target in ((1,16),(4,8),(8,4),(16,2),(32,1))
                         if flags & source)
            self.flags |= mapped
            self.exp_samples.append(dict(input=bits, output=result, fflags=mapped))
            return result
        finally:
            require(self.libm.fesetenv(env) == 0, 'Cannot restore host fenv')

    def vector_exp(self, x):
        c = lambda text: raw32(float.fromhex(text))
        minimum = c('-0x1.5d58ap+6')
        underflow = float32(x) < float32(minimum)
        if underflow:
            x = minimum
        z = self.op('fma', 32, c('0x1.715476p+0'), x, c('0x1.8p23'))
        n = self.sub(z, c('0x1.8p23'))
        b = self.op('fma', 32, c('-0x1.62e4p-1'), n, x)
        b = self.op('fma', 32, c('-0x1.7f7d1cp-20'), n, b)
        k = ((z << 23) + 0x3f800000) & 0xffffffff
        u = self.op('mul', 32, b, b)
        j = self.op('fma', 32,
            self.op('fma', 32, c('0x1.0e4020p-7'), b, c('0x1.573e2ep-5')), u,
            self.op('fma', 32, c('0x1.555e66p-3'), b, c('0x1.fffdb6p-2')))
        j = self.op('fma', 32, j, u, self.op('mul', 32, b, c('0x1.ffffecp-1')))
        result = self.op('fma', 32, j, k, k)
        return 0 if underflow else result

    def sum_scores(self, scores, scaled_sum):
        # vfwredusum may choose another F64 tree. Bound *all* positive-sum
        # trees, then require one final F32 result; never mirror the lane tree.
        values = [Fraction.from_float(float32(x)) for x in scores]
        total = sum(values, Fraction()) + Fraction.from_float(float32(scaled_sum))
        require(all(x >= 0 for x in values) and total > 0, 'Invalid softmax sum')
        error = total*Fraction(2*(len(values)+1), 1 << 52)

        def rounded(value):
            bits = struct.unpack('<Q', struct.pack('<d', float(value)))[0]
            return self.sf.evaluate('cast', 64, 32, 0, bits)[0]

        require(rounded(total-error) == rounded(total+error), 'F64 reduction order affects F32 result')
        value = 0
        for score in scores:
            value = self.add(64, value, self.cast(32, 64, score))
        value = self.add(64, value, self.cast(32, 64, scaled_sum))
        result = self.cast(64, 32, value)
        require(result == rounded(total), 'Sequential/tree sum disagreement')
        # Only NX can vary with this positive, normal F64 reduction. Independent
        # preceding arithmetic already raises NX in these frozen real fixtures.
        require(self.flags & 1, 'Reduction flags require a separate tree analysis')
        self.reduction_checks += 1
        return result


def reference(case, data):
    a = Arithmetic()
    d,h,t = (case[k] for k in ('dimension','heads','tokens'))
    rows = h//case['kv_heads']
    q32, k16, v16, mask = (unpack(data[name], width) for name,width in
                           (('query',32),('key',16),('value',16),('mask',16)))
    q16 = [a.cast(32,16,q32[head*128+dim]) for head in range(h) for dim in range(d)]
    q = [a.cast(16,32,x) for x in q16]
    output = []
    for head in range(h):
        group = head//rows
        acc, maximum, total = [0]*d, 0xff800000, 0
        for start in range(0,t,64):
            count, scores = min(64,t-start), []
            for token in range(start,start+count):
                a.phase = (head,start,'QK')
                dot = 0
                for dim in range(d):
                    key = a.cast(16,32,k16[(group*case['capacity']+token)*128+dim])
                    dot = a.op('fma',32,q[head*d+dim],key,dot)
                a.phase = None
                scores.append(a.add(32,a.op('mul',32,dot,raw32(float.fromhex('0x1.6a09e6p-4'))),
                                    a.cast(16,32,mask[token])))
            next_max = max([maximum,*scores],key=float32)
            alpha = 0 if maximum == 0xff800000 else a.expf(a.sub(maximum,next_max))
            scores = [a.vector_exp(a.sub(x,next_max)) for x in scores]
            total = a.sum_scores(scores,a.op('mul',32,total,alpha))
            maximum = next_max
            a.phase = (head,start,'PV')
            half_alpha = a.cast(32,16,alpha)
            acc = [a.op('mul',16,x,half_alpha) for x in acc]
            coefficients = [a.cast(32,16,x) for x in scores]
            for token, coefficient in enumerate(coefficients,start):
                for dim in range(d):
                    acc[dim] = a.op('fma',16,coefficient,
                        v16[(group*case['capacity']+token)*128+dim],acc[dim])
            a.phase = None
        inv = a.op('div',32,0x3f800000,total)
        output += [a.op('mul',32,a.cast(16,32,x),inv) for x in acc]
    result = dict(bits=output, natural_flags=a.flags,
        expected_fcsr=a.flags | case['initial_flags'],
        expf_samples=a.exp_samples, reduction_order_checks=a.reduction_checks,
        oracle_pins=a.pins, query_half=pack(q16,16).hex())
    result['stages'] = [dict(head=h,tile=start,mode=mode,fflags=flags)
                        for (h,start,mode),flags in a.phase_flags.items()]
    if d == 128 and h == 2 and t == 137:
        require(hashlib.sha256(pack(output,32)).hexdigest() == NATIVE_SHA,
                'Independent oracle does not reproduce accepted original tile64 golden')
    return result


def commands():
    result = []
    for trial,case in enumerate(CASES):
        if not case['requested']:
            continue
        rows = case['heads']//case['kv_heads']
        for group in range(case['kv_heads']):
            for start in range(0,case['tokens'],64):
                for mode in ('QK','PV'):
                    for base in range(0,rows,2):
                        result.append(dict(trial=trial,group=group,mode=mode,base=base,
                            tile=start,
                            heads=min(2,rows-base),dimension=case['dimension'],
                            tokens=min(64,case['tokens']-start)))
    return result


def guard_bytes(case):
    d,h = case['dimension'],case['heads']
    rows = h//case['kv_heads']
    return (8*64 + (6*128-h*d)*2 + (6*128-h*d)*4 +
            rows*(256-d)*2 + (8-rows)*(256*2+64*4+12) + 32)


def generate(output):
    output = Path(output)
    source, pins = inputs()
    results = [reference(CASES[0],source[0])]
    results.append(dict(results[0],expected_fcsr=results[0]['natural_flags'] | 8))
    results.append(reference(CASES[2],source[2]))
    labels, payload, assembly = [], bytearray(), [
        '.section .rodata.sdk_fixture,"a",@progbits', '.balign 64',
        '.global data_guard_before', 'data_guard_before:', '.fill 64,1,0xa5',
        '.global data_begin', 'data_begin:']
    declarations = []
    for index in (0,2):
        for role,width in (('query',32),('key',16),('value',16),('mask',16)):
            label = 'fixture_%d_%s' % (index,role)
            raw = source[index][role]
            padding = -len(payload) % 64
            payload += bytes(padding)+raw
            path = output/(label+'.bin')
            path.write_bytes(raw)
            labels.append(path)
            assembly += ['.balign 64','.global '+label,label+':','.incbin '+json.dumps(str(path))]
            declarations.append('extern const %s %s[%d];' %
                                ('float' if width==32 else 'uint16_t',label,len(raw)//(width//8)))
    assembly += ['.global data_end','data_end:','.global data_guard_after','data_guard_after:',
                 '.fill 64,1,0xa5','.section .note.GNU-stack,"",@progbits']
    (output/'data.S').write_text('\n'.join(assembly)+'\n')
    fields = 'requested dimension heads kv_heads tokens capacity initial_flags expected_fcsr guard_bytes query_hash guard_hash'.split()
    header = ['#ifndef SDK_FIXTURE_H','#define SDK_FIXTURE_H',*declarations,
        'typedef struct {', '  const float *query; const uint16_t *key, *value, *mask;',
        *['  uint64_t '+x+';' for x in fields], '} sdk_case_t;',
        'static const sdk_case_t sdk_cases[3] = {']
    memory = []
    for i,case in enumerate(CASES):
        qraw = bytearray(b'\xa5'*(6*128*2))
        active = bytes.fromhex(results[i]['query_half'])
        for h in range(case['heads']):
            qraw[h*256:h*256+case['dimension']*2] = active[h*case['dimension']*2:(h+1)*case['dimension']*2]
        mem = dict(query_hash=fnv(qraw),guard_bytes=guard_bytes(case),
                   guard_hash=fnv(b'\xa5'*guard_bytes(case)))
        memory.append(mem)
        values = case | mem | dict(expected_fcsr=results[i]['expected_fcsr'])
        label = 0 if i<2 else 2
        header += ['  { '+', '.join(['fixture_%d_%s' % (label,r) for r in
                     ('query','key','value','mask')] +
                     ['UINT64_C(0x%x)' % values[x] for x in fields])+' },']
        (output/('golden_%d.bin' % i)).write_bytes(pack(results[i]['bits'],32))
        pins.update(results[i]['oracle_pins'])
    header += ['};','#define SDK_DATA_BYTES UINT64_C(%d)' % len(payload),
               '#define SDK_DATA_HASH UINT64_C(0x%x)' % fnv(payload),'#endif']
    (output/'fixture.h').write_text('\n'.join(header)+'\n')
    receipt = dict(cases=list(CASES), results=results, memory=memory,
        data_bytes=len(payload),data_hash=fnv(payload),resident_commands=commands(),
        derived_provenance='Q[h,d]=captured_Q[h%2,(d+7*h)%128]; active d<96; '
            'KV group0=tokens0..64, group1=tokens64..128; physical row128 F16; '
            'mask first65, captured scale unchanged. Derived head rows, not a new captured model layer.',
        scope='Functional selection/bitwise arithmetic/flags/guards/work only; no speedup acceptance')
    (output/'fixture.json').write_text(json.dumps(receipt,indent=2)+'\n')
    return receipt,pins
